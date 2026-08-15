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
        foreach ($marker in @('[VERDICT: REJECT]', '<BLAST_RADIUS>')) {
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
            $summary = $summary.Replace('[VERDICT: REJECT]', 'VERDICT:REJECT').Replace('<BLAST_RADIUS>', 'BLAST_RADIUS')

            $root = $env:CLAUDE_PROJECT_DIR
            if (-not $root) { $root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path }
            $telemetryDir = Join-Path $root '.claude\telemetry'
            if (-not (Test-Path -LiteralPath $telemetryDir)) {
                New-Item -ItemType Directory -Path $telemetryDir -Force | Out-Null
            }
            $telemetryFile = Join-Path $telemetryDir 'agentic_telemetry.md'

            $stamp = [DateTime]::UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'")
            $line = "- [$stamp] | Hook Monitor ($eventName) | hook-detected marker | $summary`n"
            $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
            [System.IO.File]::AppendAllText($telemetryFile, $line, $utf8NoBom)
            break  # one telemetry line per stop event
        }
    }
} catch {
    # Swallow everything: telemetry failures must not surface as hook errors.
}

exit 0
