# telemetry-append.ps1 - Causal Telemetry appender (OpenAI Codex Stop / SubagentStop hook).
#
# Contract (OpenAI Codex Stop / SubagentStop hooks):
#   - Stdin receives a JSON payload (cwd, hook_event_name, transcript_path, last_assistant_message).
#   - Must emit ZERO bytes on stdout when exiting 0 (codex-manual.md:28012, 28573).
#   - Deduplicates via $alreadyAppended so dual global (~/.codex/hooks.json) and
#     repo (.codex/hooks.json) firing never writes duplicate trace lines.
#   - Strict 7-bit ASCII only. Zero dynamic eval calls.

function Remove-BacktickCodeSpans {
    param([string]$InputText)
    if ([string]::IsNullOrWhiteSpace($InputText)) { return '' }
    $cleaned = [regex]::Replace($InputText, '(?s)```.*?```', ' ')
    $cleaned = [regex]::Replace($cleaned, '`[^`\r\n]+`', ' ')
    return $cleaned
}

function Get-TranscriptAssistantText {
    param([string]$TranscriptPath)
    if ([string]::IsNullOrWhiteSpace($TranscriptPath) -or -not (Test-Path -LiteralPath $TranscriptPath)) {
        return ''
    }
    $tail = @(Get-Content -LiteralPath $TranscriptPath -Tail 40 -Encoding UTF8 -ErrorAction Stop)
    $plainLines = New-Object System.Collections.Generic.List[string]
    for ($i = $tail.Count - 1; $i -ge 0; $i--) {
        $line = [string]$tail[$i]
        if ([string]::IsNullOrWhiteSpace($line)) { continue }
        $trimmed = $line.Trim()
        if ($trimmed.StartsWith('{')) {
            try {
                $obj = $trimmed | ConvertFrom-Json
                if ($null -eq $obj) { continue }
                if ($obj.PSObject.Properties['source'] -and ([string]$obj.source) -in @('USER_EXPLICIT', 'SYSTEM', 'TOOL')) { continue }
                if ($obj.PSObject.Properties['type'] -and ([string]$obj.type) -in @('USER_INPUT', 'TOOL_RESPONSE', 'tool_use', 'tool_result', 'function_call', 'function_call_output')) { continue }
                if ($obj.PSObject.Properties['role'] -and ([string]$obj.role) -in @('user', 'tool', 'system')) { continue }
                foreach ($f in @('content', 'last_assistant_message', 'last_message', 'message', 'text')) {
                    $p = $obj.PSObject.Properties[$f]
                    if ($p -and $null -ne $p.Value) {
                        if ($p.Value -is [string] -and -not [string]::IsNullOrWhiteSpace([string]$p.Value)) {
                            return [string]$p.Value
                        }
                        if ($p.Value -is [System.Collections.IEnumerable] -and -not ($p.Value -is [string])) {
                            $parts = @()
                            foreach ($item in $p.Value) {
                                if ($item -is [string]) { $parts += $item }
                                elseif ($null -ne $item -and $item.PSObject.Properties['text'] -and (-not $item.PSObject.Properties['type'] -or [string]$item.type -eq 'text')) {
                                    $parts += [string]$item.text
                                }
                            }
                            $joined = ($parts -join "`n").Trim()
                            if ($joined) { return $joined }
                        }
                    }
                }
            } catch {
                $plainLines.Insert(0, $line)
            }
        } else {
            $plainLines.Insert(0, $line)
        }
    }
    return ($plainLines -join "`n")
}

try {
    $raw = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($raw)) { exit 0 }
    $payload = $raw | ConvertFrom-Json

    $text = ''
    foreach ($field in @('last_assistant_message', 'last_message', 'message')) {
        $prop = $payload.PSObject.Properties[$field]
        if ($prop -and $prop.Value) { $text = [string]$prop.Value; break }
    }
    if (-not $text -and $payload.PSObject.Properties['transcript_path'] -and $payload.transcript_path -and (Test-Path -LiteralPath $payload.transcript_path)) {
        $text = Get-TranscriptAssistantText -TranscriptPath ([string]$payload.transcript_path)
    }

    $text = Remove-BacktickCodeSpans -InputText $text
    if ($text) {
        $markers = @(
            '[VERDICT: REJECT]',
            '[VERDICT: PROCEED_FIX]',
            '[GLOBAL VERDICT: REJECT]',
            '[GLOBAL VERDICT: PROCEED]',
            '<BLAST_RADIUS>',
            'BLOCKING:'
        )
        foreach ($marker in $markers) {
            $idx = $text.IndexOf($marker, [System.StringComparison]::Ordinal)
            if ($idx -lt 0) { continue }

            $eventName = 'Stop'
            if ($payload.PSObject.Properties['hook_event_name'] -and $payload.hook_event_name) {
                $eventName = [string]$payload.hook_event_name
            }

            $summary = ($text.Substring($idx) -replace '\s+', ' ').Trim()
            if ($summary.Length -gt 200) { $summary = $summary.Substring(0, 200) }
            $summary = $summary.Replace('[VERDICT: REJECT]', 'VERDICT:REJECT').Replace('[VERDICT: PROCEED_FIX]', 'VERDICT:PROCEED_FIX').Replace('[GLOBAL VERDICT: REJECT]', 'GLOBAL_VERDICT:REJECT').Replace('[GLOBAL VERDICT: PROCEED]', 'GLOBAL_VERDICT:PROCEED').Replace('<BLAST_RADIUS> -->', 'BLAST_RADIUS').Replace('<BLAST_RADIUS>', 'BLAST_RADIUS').Replace('BLOCKING:', 'BLOCKING_STATE:')

            $root = $env:CODEX_PROJECT_DIR
            if (-not $root -and $payload.PSObject.Properties['cwd'] -and $payload.cwd) {
                $c = [string]$payload.cwd
                if ((Test-Path -LiteralPath (Join-Path $c '.codex')) -or (Test-Path -LiteralPath (Join-Path $c 'CODEX.md'))) {
                    $root = $c
                }
            }
            if (-not $root) {
                $root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
            }
            $telemetryDir = Join-Path $root '.codex\telemetry'
            if (-not (Test-Path -LiteralPath $telemetryDir)) {
                New-Item -ItemType Directory -Path $telemetryDir -Force | Out-Null
            }
            $telemetryFile = Join-Path $telemetryDir 'agentic_telemetry.md'

            $alreadyAppended = $false
            $prevChain = '00000000'
            if (Test-Path -LiteralPath $telemetryFile) {
                $existingLines = @(Get-Content -LiteralPath $telemetryFile -Encoding UTF8 -ErrorAction SilentlyContinue | Where-Object { $_ -and $_.Trim() -ne '' })
                if ($existingLines.Count -gt 0) {
                    $lastLine = [string]$existingLines[$existingLines.Count - 1]
                    if ($lastLine.IndexOf("| $summary", [System.StringComparison]::Ordinal) -ge 0) {
                        $alreadyAppended = $true
                    }
                    if ($lastLine -match '\[chain:([0-9a-fA-F]{8})\]') {
                        $prevChain = $Matches[1].ToLowerInvariant()
                    }
                }
            }

            if (-not $alreadyAppended) {
                $stamp = [DateTime]::UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'")
                $entryBody = "- [$stamp] | Hook Monitor ($eventName) | hook-detected marker | $summary"
                $sha = [System.Security.Cryptography.SHA256]::Create()
                try {
                    $hashBytes = $sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes("$prevChain|$entryBody"))
                    $chainTag = ([System.BitConverter]::ToString($hashBytes).Replace('-', '').ToLowerInvariant()).Substring(0, 8)
                } finally {
                    $sha.Dispose()
                }
                $line = "$entryBody [chain:$chainTag]`n"
                $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
                [System.IO.File]::AppendAllText($telemetryFile, $line, $utf8NoBom)
            }
            break
        }
    }
} catch {
    # Swallow everything: telemetry failures must not surface as hook errors.
}

exit 0
