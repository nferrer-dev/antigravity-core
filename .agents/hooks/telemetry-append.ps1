# telemetry-append.ps1 - Causal Telemetry appender (Stop hook for Antigravity).
#
# Contract (Antigravity Stop hooks): a JSON payload arrives on stdin with
# camelCase fields (conversationId, terminationReason, transcriptPath,
# artifactDirectoryPath). If the finishing turn contains a Critical Autonomous
# Decision marker - [VERDICT: REJECT] or <BLAST_RADIUS> - append one line to
# .agents/agentic_telemetry.md (UTF-8, no BOM).
#
# Emits {"decision":"allow"} on stdout when invoked under an Antigravity Stop
# payload. Always exits 0. PowerShell 5.1 compatible. Strict 7-bit ASCII only.

$isAntigravityStop = $false

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
                foreach ($f in @('content', 'last_assistant_message', 'lastAssistantMessage', 'last_message', 'message', 'text')) {
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
    if (-not [string]::IsNullOrWhiteSpace($raw)) {
        $payload = $raw | ConvertFrom-Json
        if ($null -ne $payload) {
            if ($payload.PSObject.Properties['conversationId'] -or $payload.PSObject.Properties['terminationReason']) {
                $isAntigravityStop = $true
            }

            $fullyIdle = $true
            $hasFullyIdle = $false
            if ($payload.PSObject.Properties['fullyIdle'] -and $null -ne $payload.fullyIdle) {
                $fullyIdle = [bool]$payload.fullyIdle
                $hasFullyIdle = $true
                $isAntigravityStop = $true
            }

            $text = ''
            foreach ($field in @('last_assistant_message', 'lastAssistantMessage', 'last_message', 'message')) {
                $prop = $payload.PSObject.Properties[$field]
                if ($prop -and $prop.Value) { $text = [string]$prop.Value; break }
            }

            $tPath = ''
            if ($payload.PSObject.Properties['transcriptPath'] -and $payload.transcriptPath) {
                $tPath = [string]$payload.transcriptPath
            } elseif ($payload.PSObject.Properties['transcript_path'] -and $payload.transcript_path) {
                $tPath = [string]$payload.transcript_path
            }

            if (-not $text -and $fullyIdle -and $tPath -and (Test-Path -LiteralPath $tPath)) {
                $text = Get-TranscriptAssistantText -TranscriptPath $tPath
            }

            $text = Remove-BacktickCodeSpans -InputText $text
            if ($text) {
                $markers = @(
                    '[VERDICT: REJECT]',
                    '[GLOBAL VERDICT: REJECT]',
                    '[GLOBAL VERDICT: PROCEED]',
                    '<BLAST_RADIUS>',
                    'BLOCKING:'
                )
                foreach ($marker in $markers) {
                    $idx = $text.IndexOf($marker, [System.StringComparison]::Ordinal)
                    if ($idx -lt 0) { continue }

                    $eventName = 'Stop'
                    if ($payload.PSObject.Properties['terminationReason'] -and $payload.terminationReason) {
                        $eventName = [string]$payload.terminationReason
                    } elseif ($payload.PSObject.Properties['hook_event_name'] -and $payload.hook_event_name) {
                        $eventName = [string]$payload.hook_event_name
                    }
                    if ($hasFullyIdle) {
                        $eventName = "$eventName,idle=$fullyIdle"
                    }

                    $summary = ($text.Substring($idx) -replace '\s+', ' ').Trim()
                    if ($summary.Length -gt 200) { $summary = $summary.Substring(0, 200) }
                    $summary = $summary.Replace('[VERDICT: REJECT]', 'VERDICT:REJECT').Replace('[GLOBAL VERDICT: REJECT]', 'GLOBAL_VERDICT:REJECT').Replace('[GLOBAL VERDICT: PROCEED]', 'GLOBAL_VERDICT:PROCEED').Replace('<BLAST_RADIUS>', 'BLAST_RADIUS').Replace('BLOCKING:', 'BLOCKING_STATE:')

                    $root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
                    $agentsSub = Join-Path $root '.agents'
                    if ($payload.PSObject.Properties['artifactDirectoryPath'] -and $payload.artifactDirectoryPath -and (Test-Path -LiteralPath ([string]$payload.artifactDirectoryPath))) {
                        $telemetryFile = Join-Path ([string]$payload.artifactDirectoryPath) 'agentic_telemetry.md'
                    } elseif (Test-Path -LiteralPath $agentsSub) {
                        $telemetryFile = Join-Path $agentsSub 'agentic_telemetry.md'
                    } else {
                        $parentDir = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
                        $telemetryFile = Join-Path $parentDir 'agentic_telemetry.md'
                    }

                    $alreadyAppended = $false
                    $prevChain = '00000000'
                    if (Test-Path -LiteralPath $telemetryFile) {
                        $existingLines = @(Get-Content -LiteralPath $telemetryFile -Encoding UTF8 | Where-Object { $_ -and $_.Trim() -ne '' })
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
        }
    }
} catch {
    # Swallow all exceptions so telemetry never blocks agent execution.
}

if ($isAntigravityStop) {
    [Console]::Out.WriteLine('{"decision":"allow"}')
}
exit 0
