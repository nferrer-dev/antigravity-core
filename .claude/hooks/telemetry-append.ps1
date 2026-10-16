# telemetry-append.ps1 - Causal Telemetry appender (Stop / SubagentStop hook).
#
# Contract (Claude Code hooks): a JSON payload arrives on stdin (fields include
# hook_event_name, transcript_path, and possibly a last-message field). If the
# finishing turn contains a Critical Autonomous Decision marker -
# [VERDICT: REJECT] or <BLAST_RADIUS> - append one line to
# .claude/telemetry/agentic_telemetry.md (UTF-8, no BOM) in the canonical
# single-line trace format of .claude/rules/telemetry.md:
#   - [<ISO-8601 UTC now>] | Hook Monitor (<event>) | hook-detected marker | <summary, first 200 chars>
#
# Telemetry must never block work: this script ALWAYS exits 0.
# PowerShell 5.1 compatible. ASCII only.

try {
    $raw = [Console]::In.ReadToEnd()
    $payload = $raw | ConvertFrom-Json

    # Text to scan: prefer an inline last-message field, else the transcript tail.
    $text = ''
    foreach ($field in @('last_assistant_message', 'last_message', 'message')) {
        $prop = $payload.PSObject.Properties[$field]
        if ($prop -and $prop.Value) { $text = [string]$prop.Value; break }
    }
    if (-not $text -and $payload.transcript_path -and (Test-Path -LiteralPath $payload.transcript_path)) {
        # Transcripts are UTF-8; without -Encoding UTF8, PS 5.1 reads ANSI and
        # mangles multi-byte chars (em-dash -> mojibake) in appended traces.
        $tail = Get-Content -LiteralPath $payload.transcript_path -Tail 40 -Encoding UTF8 -ErrorAction Stop
        $text = $tail -join "`n"
    }

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
            if ($payload.hook_event_name) { $eventName = [string]$payload.hook_event_name }

            # Summary: event name + text starting at the marker, whitespace
            # collapsed, capped at 200 chars. Markers are neutralized in the
            # summary (brackets stripped) so hook-written lines can never
            # re-trigger this hook when a later transcript quotes the log.
            $summary = ($text.Substring($idx) -replace '\s+', ' ').Trim()
            if ($summary.Length -gt 200) { $summary = $summary.Substring(0, 200) }
            $summary = $summary.Replace('[VERDICT: REJECT]', 'VERDICT:REJECT').Replace('[GLOBAL VERDICT: REJECT]', 'GLOBAL_VERDICT:REJECT').Replace('[GLOBAL VERDICT: PROCEED]', 'GLOBAL_VERDICT:PROCEED').Replace('<BLAST_RADIUS>', 'BLAST_RADIUS').Replace('BLOCKING:', 'BLOCKING_STATE:')

            $root = $env:CLAUDE_PROJECT_DIR
            if (-not $root) { $root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path }
            $telemetryDir = Join-Path $root '.claude\telemetry'
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
            break  # one telemetry line per stop event
        }
    }
} catch {
    # Swallow everything: telemetry failures must not surface as hook errors.
}

exit 0
