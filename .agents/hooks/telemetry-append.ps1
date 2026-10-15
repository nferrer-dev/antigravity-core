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
                $tail = Get-Content -LiteralPath $tPath -Tail 40 -Encoding UTF8 -ErrorAction Stop
                $text = $tail -join "`n"
            }

            if ($text) {
                foreach ($marker in @('[VERDICT: REJECT]', '<BLAST_RADIUS>')) {
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
                    $summary = $summary.Replace('[VERDICT: REJECT]', 'VERDICT:REJECT').Replace('<BLAST_RADIUS>', 'BLAST_RADIUS')

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
                    if (Test-Path -LiteralPath $telemetryFile) {
                        $existingLines = @(Get-Content -LiteralPath $telemetryFile -Encoding UTF8 | Where-Object { $_ -and $_.Trim() -ne '' })
                        if ($existingLines.Count -gt 0) {
                            $lastLine = [string]$existingLines[$existingLines.Count - 1]
                            if ($lastLine.EndsWith("| $summary", [System.StringComparison]::Ordinal)) {
                                $alreadyAppended = $true
                            }
                        }
                    }

                    if (-not $alreadyAppended) {
                        $stamp = [DateTime]::UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'")
                        $line = "- [$stamp] | Hook Monitor ($eventName) | hook-detected marker | $summary`n"
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
