# brc-guard.ps1 - Blast Radius Containment (BRC) and Secret PreToolUse guard.
#
# Contract (Claude Code hooks): a JSON payload arrives on stdin with fields
# including tool_name and tool_input. Exit 0 allows the tool call.
# Exit 2 blocks it; stderr is fed back to the model as the reason.
#
# Conservative by design: a false positive on an ordinary dev command is worse
# than a miss. Routine cleanup of temp/scratch/worktree paths is exempt
# (Standard Build and Sandbox Exemptions, .claude/rules/blast-radius.md).
#
# PowerShell 5.1 compatible. ASCII only. Fails open on any parse error.

$ErrorActionPreference = 'Stop'

$script:PayloadObj = $null

function Get-TelemetryChainTag {
    param([string]$FilePath, [string]$EntryBody)
    $prevChain = '00000000'
    if (Test-Path -LiteralPath $FilePath) {
        $lines = @(Get-Content -LiteralPath $FilePath -Encoding UTF8 -ErrorAction SilentlyContinue | Where-Object { $_ -and $_.Trim() -ne '' })
        if ($lines.Count -gt 0) {
            $last = [string]$lines[$lines.Count - 1]
            if ($last -match '\[chain:([0-9a-fA-F]{8})\]') {
                $prevChain = $Matches[1].ToLowerInvariant()
            }
        }
    }
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes("$prevChain|$EntryBody")
        $hash = $sha.ComputeHash($bytes)
        return ([System.BitConverter]::ToString($hash).Replace('-', '').ToLowerInvariant()).Substring(0, 8)
    } finally {
        $sha.Dispose()
    }
}

function Test-SessionWebTainted {
    param($Payload)
    if ($null -eq $Payload) { return $false }
    if ($Payload.PSObject.Properties['artifactDirectoryPath'] -and $Payload.artifactDirectoryPath) {
        $p1 = Join-Path (Join-Path ([string]$Payload.artifactDirectoryPath) 'scratch') '.untrusted_web_taint.json'
        if (Test-Path -LiteralPath $p1) { return $true }
    }
    if ($Payload.PSObject.Properties['cwd'] -and $Payload.cwd) {
        $cwdStr = [string]$Payload.cwd
        $p2 = Join-Path (Join-Path (Join-Path $cwdStr '.claude') 'telemetry') '.untrusted_web_taint.json'
        if (Test-Path -LiteralPath $p2) { return $true }
        $p3 = Join-Path (Join-Path $cwdStr 'scratch') '.untrusted_web_taint.json'
        if (Test-Path -LiteralPath $p3) { return $true }
    }
    return $false
}

function Write-GuardTelemetry {
    param([string]$Decision, [string]$Rule, [string]$Excerpt)
    try {
        $telPath = $null
        if ($null -ne $script:PayloadObj -and $script:PayloadObj.PSObject.Properties['artifactDirectoryPath'] -and $script:PayloadObj.artifactDirectoryPath) {
            $artDir = [string]$script:PayloadObj.artifactDirectoryPath
            if (-not [string]::IsNullOrWhiteSpace($artDir) -and (Test-Path -LiteralPath $artDir)) {
                $telPath = Join-Path $artDir 'agentic_telemetry.md'
            }
        } else {
            $baseDir = $env:CLAUDE_PROJECT_DIR
            if (-not $baseDir -and $null -ne $script:PayloadObj -and $script:PayloadObj.PSObject.Properties['cwd'] -and $script:PayloadObj.cwd) {
                $baseDir = [string]$script:PayloadObj.cwd
            }
            if ($baseDir -and (Test-Path -LiteralPath (Join-Path $baseDir '.claude'))) {
                $telDir = Join-Path $baseDir '.claude\telemetry'
                if (-not (Test-Path -LiteralPath $telDir)) {
                    New-Item -ItemType Directory -Path $telDir -Force | Out-Null
                }
                $telPath = Join-Path $telDir 'agentic_telemetry.md'
            }
        }
        if ($telPath) {
            $sig = "| PreToolUse Guard ($Rule) | $Decision | $Excerpt"
            if (Test-Path -LiteralPath $telPath) {
                $existing = @(Get-Content -LiteralPath $telPath -Encoding UTF8 -ErrorAction SilentlyContinue | Where-Object { $_ -and $_.Trim() -ne '' })
                if ($existing.Count -gt 0) {
                    $last = [string]$existing[$existing.Count - 1]
                    if ($last.IndexOf($sig, [System.StringComparison]::Ordinal) -ge 0) {
                        return
                    }
                }
            }
            $stamp = [DateTime]::UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'")
            $entryBody = "- [$stamp] $sig"
            $chainTag = Get-TelemetryChainTag -FilePath $telPath -EntryBody $entryBody
            $line = "$entryBody [chain:$chainTag]`n"
            $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
            [System.IO.File]::AppendAllText($telPath, $line, $utf8NoBom)
        }
    } catch {
        # Never block guard execution on telemetry write failure.
    }
}

function Deny {
    param([string]$Rule, [string]$Cmd)
    $excerpt = $Cmd -replace '\s+', ' '
    if ($excerpt.Length -gt 160) { $excerpt = $excerpt.Substring(0, 160) + '...' }
    Write-GuardTelemetry -Decision 'deny' -Rule $Rule -Excerpt $excerpt
    $lines = @(
        "BLOCKED by BRC guard [$Rule]: $excerpt",
        "This command is high blast radius. Do NOT retry it or attempt a workaround.",
        "Per .claude/rules/blast-radius.md you MUST now emit a <BLAST_RADIUS> assessment",
        "(<TARGET>, <REVERSIBILITY>, <WORST_CASE_IMPACT>) and yield to the human for",
        "explicit authorization before any equivalent command is attempted."
    )
    [Console]::Error.WriteLine(($lines -join ' '))
    exit 2
}

# ---- Read and parse the hook payload; fail open if unparseable ----
try {
    $raw = [Console]::In.ReadToEnd()
    if ([string]::IsNullOrWhiteSpace($raw)) { exit 0 }
    $payload = $raw | ConvertFrom-Json
} catch {
    exit 0
}

if ($null -eq $payload) { exit 0 }
$script:PayloadObj = $payload

$toolName = ''
if ($payload.PSObject.Properties['tool_name'] -and $null -ne $payload.tool_name) {
    $toolName = [string]$payload.tool_name
}

$toolInput = $null
if ($payload.PSObject.Properties['tool_input'] -and $null -ne $payload.tool_input) {
    $toolInput = $payload.tool_input
} else {
    exit 0
}

function Get-WriteContentString {
    param($ArgsObj)
    if ($null -eq $ArgsObj) { return '' }
    $parts = New-Object System.Collections.Generic.List[string]
    foreach ($cf in @('CodeContent', 'ReplacementContent', 'Replacement', 'new_string', 'content')) {
        if ($ArgsObj.PSObject.Properties[$cf] -and $null -ne $ArgsObj.$cf) {
            $parts.Add([string]$ArgsObj.$cf)
        }
    }
    if ($ArgsObj.PSObject.Properties['edits'] -and $null -ne $ArgsObj.edits) {
        foreach ($ed in @($ArgsObj.edits)) {
            if ($null -ne $ed) {
                foreach ($ef in @('new_string', 'Replacement', 'ReplacementContent')) {
                    if ($ed.PSObject.Properties[$ef] -and $null -ne $ed.$ef) {
                        $parts.Add([string]$ed.$ef)
                    }
                }
            }
        }
    }
    if ($ArgsObj.PSObject.Properties['ReplacementChunks'] -and $null -ne $ArgsObj.ReplacementChunks) {
        foreach ($ch in @($ArgsObj.ReplacementChunks)) {
            if ($null -ne $ch) {
                foreach ($cf2 in @('ReplacementContent', 'Replacement', 'new_string')) {
                    if ($ch.PSObject.Properties[$cf2] -and $null -ne $ch.$cf2) {
                        $parts.Add([string]$ch.$cf2)
                    }
                }
            }
        }
    }
    return ($parts -join "`n")
}

# ---- Check file-access tools (Read, Edit, Write, MultiEdit) ----
$filePath = ''
foreach ($pf in @('file_path', 'path', 'Path', 'notebook_path', 'TargetFile', 'AbsolutePath', 'SearchPath', 'SearchDirectory', 'DirectoryPath', 'Directory', 'File')) {
    if ($toolInput.PSObject.Properties[$pf] -and $null -ne $toolInput.$pf) {
        $filePath = [string]$toolInput.$pf
        break
    }
}

function Test-UnsafeFetchUrl {
    param([string]$UrlStr)
    if ([string]::IsNullOrWhiteSpace($UrlStr)) { return $false }
    $uri = $null
    if (-not [System.Uri]::TryCreate($UrlStr.Trim(), [System.UriKind]::Absolute, [ref]$uri)) {
        return $true
    }
    if ($uri.Scheme -notin @('http', 'https')) {
        return $true
    }
    $hostStr = $uri.DnsSafeHost.ToLowerInvariant().Trim('[', ']')
    if ([string]::IsNullOrWhiteSpace($hostStr)) { return $true }
    if ($hostStr -in @('localhost', 'metadata.google.internal', 'instance-data', 'metadata') -or $hostStr.EndsWith('.localhost') -or $hostStr.EndsWith('.internal')) {
        return $true
    }
    $ip = $null
    if ([System.Net.IPAddress]::TryParse($hostStr, [ref]$ip)) {
        if ($ip.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetworkV6) {
            if ($ip.IsIPv6Loopback -or $ip.IsIPv6LinkLocal -or $ip.IsIPv6SiteLocal) { return $true }
            $b6 = $ip.GetAddressBytes()
            $allZero = $true
            for ($i = 0; $i -lt 16; $i++) { if ($b6[$i] -ne 0) { $allZero = $false; break } }
            if ($allZero) { return $true }
            if (($b6[0] -band 0xFE) -eq 0xFC) { return $true }
            $isV4Mapped = $true
            for ($i = 0; $i -lt 10; $i++) { if ($b6[$i] -ne 0) { $isV4Mapped = $false; break } }
            if ($isV4Mapped -and $b6[10] -eq 255 -and $b6[11] -eq 255) {
                $b4 = @($b6[12], $b6[13], $b6[14], $b6[15])
                if ($b4[0] -in @(0, 10, 127)) { return $true }
                if ($b4[0] -eq 169 -and $b4[1] -eq 254) { return $true }
                if ($b4[0] -eq 172 -and $b4[1] -ge 16 -and $b4[1] -le 31) { return $true }
                if ($b4[0] -eq 192 -and $b4[1] -eq 168) { return $true }
                if ($b4[0] -eq 100 -and $b4[1] -eq 100 -and $b4[2] -eq 100 -and $b4[3] -eq 200) { return $true }
            }
            return $false
        }
        if ($ip.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork) {
            $b4 = $ip.GetAddressBytes()
            if ($b4[0] -in @(0, 10, 127)) { return $true }
            if ($b4[0] -eq 169 -and $b4[1] -eq 254) { return $true }
            if ($b4[0] -eq 172 -and $b4[1] -ge 16 -and $b4[1] -le 31) { return $true }
            if ($b4[0] -eq 192 -and $b4[1] -eq 168) { return $true }
            if ($b4[0] -eq 100 -and $b4[1] -eq 100 -and $b4[2] -eq 100 -and $b4[3] -eq 200) { return $true }
        }
    }
    return $false
}

function Test-MissingStage0Artifact {
    param([string]$PathStr, $PayloadObj)
    if ([string]::IsNullOrWhiteSpace($PathStr)) { return $false }
    $norm = $PathStr.Replace('/', '\')
    if ($norm -notmatch '(?i)(^|\\)implementation_plan\.md$') { return $false }
    $searchDirs = New-Object System.Collections.Generic.List[string]
    if ($null -ne $PayloadObj -and $PayloadObj.PSObject.Properties['artifactDirectoryPath']) {
        $artDir = [string]$PayloadObj.artifactDirectoryPath
        if (-not [string]::IsNullOrWhiteSpace($artDir)) {
            $searchDirs.Add($artDir.Replace('/', '\'))
        }
    }
    $cwdDir = ''
    if ($null -ne $PayloadObj -and $PayloadObj.PSObject.Properties['cwd']) {
        $cwdDir = [string]$PayloadObj.cwd
        if (-not [string]::IsNullOrWhiteSpace($cwdDir)) {
            $cwdNorm = $cwdDir.Replace('/', '\')
            if (-not $searchDirs.Contains($cwdNorm)) {
                $searchDirs.Add($cwdNorm)
            }
        }
    }
    $parentDir = Split-Path -Parent $norm
    if (-not [string]::IsNullOrWhiteSpace($parentDir)) {
        $resolvedParent = $parentDir
        if (-not [System.IO.Path]::IsPathRooted($parentDir)) {
            if (-not [string]::IsNullOrWhiteSpace($cwdDir)) {
                $resolvedParent = Join-Path ($cwdDir.Replace('/', '\')) $parentDir
            } else {
                $resolvedParent = ''
            }
        }
        if (-not [string]::IsNullOrWhiteSpace($resolvedParent) -and -not $searchDirs.Contains($resolvedParent)) {
            $searchDirs.Add($resolvedParent)
        }
    }
    if ($searchDirs.Count -eq 0) { return $false }
    foreach ($dir in $searchDirs) {
        $scratchDir = Join-Path $dir 'scratch'
        if (Test-Path -LiteralPath $scratchDir) {
            $hits = @(Get-ChildItem -LiteralPath $scratchDir -Filter 'stage0*' -File -ErrorAction SilentlyContinue | Where-Object {
                if ($_.Length -le 0) { return $false }
                $rawBody = Get-Content -LiteralPath $_.FullName -Raw -ErrorAction SilentlyContinue
                if ($_.Extension -ieq '.json') {
                    if ($rawBody -match '"status"\s*:\s*"(UNSAT|REFUTED|VACUOUS|INVALID)"') { return $false }
                }
                if ($rawBody -match '(?i)<RUBRIC_SCORE>' -and (Test-InvalidRubricScoreBlock $rawBody)) { return $false }
                return $true
            })
            if ($hits.Count -gt 0) { return $false }
        }
        if (Test-Path -LiteralPath $dir) {
            $rootHits = @(Get-ChildItem -LiteralPath $dir -Filter 'stage0*' -File -ErrorAction SilentlyContinue | Where-Object {
                if ($_.Length -le 0) { return $false }
                $rawBody = Get-Content -LiteralPath $_.FullName -Raw -ErrorAction SilentlyContinue
                if ($_.Extension -ieq '.json') {
                    if ($rawBody -match '"status"\s*:\s*"(UNSAT|REFUTED|VACUOUS|INVALID)"') { return $false }
                }
                if ($rawBody -match '(?i)<RUBRIC_SCORE>' -and (Test-InvalidRubricScoreBlock $rawBody)) { return $false }
                return $true
            })
            if ($rootHits.Count -gt 0) { return $false }
        }
    }
    return $true
}

function Test-Stage1CandidateSolutionsGate {
    param([string]$PathStr, $ArgsObj)
    if ([string]::IsNullOrWhiteSpace($PathStr)) { return $false }
    $norm = $PathStr.Replace('/', '\')
    if ($norm -notmatch '(?i)(^|\\)candidate_solutions\.md$') { return $false }
    $body = Get-WriteContentString $ArgsObj
    if (($body -notmatch '(?i)Radical\s+Innovator') -or
        ($body -notmatch '(?i)Enterprise\s+Minimalist') -or
        ($body -notmatch '(?i)Security\s+Paranoiac')) {
        return $true
    }
    return $false
}

function Test-InvalidRubricScoreBlock {
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return $false }
    $blockMatches = [regex]::Matches($Text, '(?is)<RUBRIC_SCORE>\s*(\{[\s\S]*?\})\s*</RUBRIC_SCORE>')
    if ($blockMatches.Count -eq 0) { return $false }
    $validVerdicts = @('APPROVE', 'REJECT', 'PROCEED', 'HALT', 'TIER_0', 'TIER_1', 'TIER_2', 'AIRTIGHT_HALT', 'PROCEED_FIX')
    $lastVerdict = ''
    $hasReject = $false
    $hasHalt = $false
    $hasProceedFix = $false
    $seenPanelRoles = @{}
    foreach ($bm in $blockMatches) {
        $rawJson = $bm.Groups[1].Value
        $critMatches = [regex]::Matches($rawJson, '\{[^{}]*\}')
        foreach ($cm in $critMatches) {
            $chunk = $cm.Value
            $evIdx = $chunk.IndexOf('"evidence"')
            $scIdx = $chunk.IndexOf('"score"')
            if ($evIdx -ge 0 -or $scIdx -ge 0) {
                if ($evIdx -lt 0 -or $scIdx -lt 0 -or $scIdx -lt $evIdx) {
                    return $true
                }
            }
        }
        try {
            $obj = $rawJson | ConvertFrom-Json
        } catch {
            return $true
        }
        if ($null -eq $obj -or -not $obj.PSObject.Properties['criteria'] -or $null -eq $obj.criteria) {
            return $true
        }
        if (-not $obj.PSObject.Properties['stage'] -or $null -eq $obj.stage -or ($obj.stage -is [bool])) {
            return $true
        }
        $stageVal = [int]$obj.stage
        if ($stageVal -lt 0 -or $stageVal -gt 5) { return $true }
        if (-not $obj.PSObject.Properties['role'] -or [string]::IsNullOrWhiteSpace([string]$obj.role)) {
            return $true
        }
        $roleKey = "$stageVal|" + ([string]$obj.role).Trim().ToLowerInvariant()
        if ($blockMatches.Count -gt 1) {
            if ($seenPanelRoles.ContainsKey($roleKey)) { return $true }
            $seenPanelRoles[$roleKey] = $true
        }
        if (-not $obj.PSObject.Properties['verdict'] -or [string]::IsNullOrWhiteSpace([string]$obj.verdict)) {
            return $true
        }
        $verdict = ([string]$obj.verdict).Trim().ToUpperInvariant()
        if ($verdict -notin $validVerdicts) { return $true }
        $lastVerdict = $verdict
        if ($verdict -eq 'REJECT') { $hasReject = $true }
        if ($verdict -eq 'HALT') { $hasHalt = $true }
        if ($verdict -eq 'PROCEED_FIX') { $hasProceedFix = $true }
        $critList = @($obj.criteria)
        $minCrit = if ($stageVal -eq 0) { 1 } else { 3 }
        if ($critList.Count -lt $minCrit) { return $true }
        $actualMin = 99
        $actualTotal = 0
        $seenIds = @{}
        foreach ($c in $critList) {
            if ($null -eq $c -or -not $c.PSObject.Properties['id'] -or -not $c.PSObject.Properties['score'] -or -not $c.PSObject.Properties['evidence']) {
                return $true
            }
            $cId = ([string]$c.id).Trim()
            if ([string]::IsNullOrWhiteSpace($cId) -or $seenIds.ContainsKey($cId)) { return $true }
            $seenIds[$cId] = $true
            if ([string]::IsNullOrWhiteSpace([string]$c.evidence)) { return $true }
            if ($c.score -is [bool]) { return $true }
            $sVal = [int]$c.score
            if ($sVal -lt 0 -or $sVal -gt 3) { return $true }
            if ($sVal -lt $actualMin) { $actualMin = $sVal }
            $actualTotal += $sVal
        }
        $defThr = [int][Math]::Ceiling(0.75 * 3.0 * $critList.Count)
        if ($obj.PSObject.Properties['min_score'] -and $null -ne $obj.min_score) {
            if (($obj.min_score -is [bool]) -or ([int]$obj.min_score -ne $actualMin)) { return $true }
        }
        if ($obj.PSObject.Properties['total_score'] -and $null -ne $obj.total_score) {
            if (($obj.total_score -is [bool]) -or ([int]$obj.total_score -ne $actualTotal)) { return $true }
        }
        $effThr = $defThr
        if ($obj.PSObject.Properties['threshold'] -and $null -ne $obj.threshold) {
            if ($obj.threshold -is [bool]) { return $true }
            $effThr = [int]$obj.threshold
            if ($effThr -lt $defThr) { return $true }
        }
        if ($verdict -in @('APPROVE', 'PROCEED', 'AIRTIGHT_HALT')) {
            if ($actualMin -lt 2 -or $actualTotal -lt $effThr) { return $true }
        } elseif ($verdict -in @('REJECT', 'PROCEED_FIX')) {
            if ($actualMin -ge 2 -and $actualTotal -ge $effThr) { return $true }
        }
    }
    $panelVerdict = if ($hasHalt) { 'HALT' } elseif ($hasReject) { 'REJECT' } elseif ($hasProceedFix) { 'PROCEED_FIX' } else { $lastVerdict }
    $proseMatches = [regex]::Matches($Text, '\[(?:GLOBAL\s+)?VERDICT:\s*([A-Za-z0-9_]+)\]')
    if ($proseMatches.Count -gt 0) {
        $proseVerdict = $proseMatches[$proseMatches.Count - 1].Groups[1].Value.Trim().ToUpperInvariant()
        if ($proseVerdict -ne $panelVerdict) { return $true }
    }
    return $false
}

if ($filePath -ne '') {
    $norm = $filePath.Replace('/', '\')
    $isExample = ($norm -match '\.env\.(example|sample|template|dist|schema)$') -or ($norm -match '\.deprecated-redacted$')
    if (-not $isExample) {
        if (($norm -match '(^|\\)\.env(\.[A-Za-z0-9_-]+)?$') -or
            ($norm -match '\.(pem|key|p12|pfx|p8|keystore|jks)$') -or
            ($norm -match '(^|\\)(id_rsa|id_ed25519|id_ecdsa|id_dsa|\.npmrc|\.pypirc|\.netrc|\.git-credentials)$') -or
            ($norm -match '(\.aws\\credentials|\.kube\\config|\.docker\\config\.json)$') -or
            ($norm -match 'antigravity\\mcp_config\.json$')) {
            Deny 'secret-file-access' $filePath
        }
    }
    if ($toolName -match '^(Edit|Write|MultiEdit|write_to_file|write_file|(?:multi_)?replace_file_content|edit_file)$') {
        if (($norm -notmatch '(?i)(^|\\)(scratch|tmp|temp)(\\|$)') -and
            (($norm -match '(?i)(^|\\)(hooks\.json|settings\.json|brc-guard\.ps1|telemetry-append\.ps1|\.pre-commit-config\.yaml|mcp_config\.json|\.mcp\.json|plugin\.json|CLAUDE\.md|AGENTS\.md|CODEX\.md|config\.toml|antigravity\.rules|agentic_telemetry\.md)$') -or
             ($norm -match '(?i)(^|\\)(\.agents|\.claude|\.codex)\\agents\\[A-Za-z0-9_-]+\.(md|toml)$'))) {
            Deny 'harness-config-self-tampering' $filePath
        }
        if (($norm -notmatch '(?i)(^|\\)(scratch|tmp|temp)(\\|$)') -and
            ($norm -match '(?i)(^|\\)(dist|build)(\\|$)')) {
            Deny 'generated-output-write-guard' $filePath
        }
        if (Test-MissingStage0Artifact $filePath $payload) {
            Deny 'stage0-comprehend-problem-gate' 'Run comprehend-problem (.claude/skills/comprehend-problem/SKILL.md) and write non-empty scratch/stage0_<topic>.md or .json (with SAT status) before writing implementation_plan.md'
        }
        if (($toolName -match '^(Write|write_to_file|write_file)$') -and (Test-Stage1CandidateSolutionsGate $filePath $toolInput)) {
            Deny 'stage1-candidate-solutions-gate' 'candidate_solutions.md must include all 3 cognitive framing lenses (Radical Innovator, Enterprise Minimalist, Security Paranoiac)'
        }
        if (Test-InvalidRubricScoreBlock (Get-WriteContentString $toolInput)) {
            Deny 'rubric-score-threshold-gate' 'RUBRIC_SCORE block failed validation (require evidence before score, min_score >= 2, and total_score >= threshold for APPROVE/PROCEED)'
        }
        if (($filePath -match '(?i)\.md$') -and (Test-SessionWebTainted $payload)) {
            $mdBody = Get-WriteContentString $toolInput
            if ($mdBody -match '!\[[^\]]*\]\(\s*https?://') {
                Deny 'untrusted-web-markdown-image-exfil' 'Writing external Markdown image URL while session is web-tainted'
            }
        }
    }
}

if ($toolName -match '^(Agent|Task|spawn_agent)$') {
    $subPrompt = ''
    foreach ($mf in @('prompt', 'Prompt', 'message')) {
        if ($toolInput.PSObject.Properties[$mf] -and $null -ne $toolInput.$mf) {
            $subPrompt = [string]$toolInput.$mf
            break
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($subPrompt)) {
        $pLines = @($subPrompt -split "\r?\n")
        if ($pLines.Count -gt 200) {
            Deny 'subagent-mvc-prompt-cap' 'Subagent prompt exceeds 200-line MVC cap; write context to scratch/ and pass the file path'
        }
        if (($subPrompt -match '(sk-proj-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{50,}|AIzaSy[A-Za-z0-9_-]{33}|fc-[a-f0-9]{32}|tvly-[A-Za-z0-9_-]{20,}|GOCSPX-[A-Za-z0-9_-]{20,})') -or
            ($subPrompt -match '(?i)(ignore\s+(all\s+)?(previous|prior)\s+instructions|disregard\s+(all\s+)?(previous|prior)\s+(instructions|rules)|<\s*system\s*>)')) {
            Deny 'subagent-message-injection-guard' 'Blocked secret token or prompt-injection override directive in subagent prompt'
        }
    }
    $subType = ''
    foreach ($tf in @('subagent_type', 'agent_type', 'TypeName')) {
        if ($toolInput.PSObject.Properties[$tf] -and $null -ne $toolInput.$tf) {
            $subType = [string]$toolInput.$tf
            break
        }
    }
    $subRole = ''
    foreach ($rf in @('description', 'role', 'Role')) {
        if ($toolInput.PSObject.Properties[$rf] -and $null -ne $toolInput.$rf) {
            $subRole = [string]$toolInput.$rf
            break
        }
    }
    if ($subType -ieq 'self' -and $subRole -match '(?i)(Style Expert|Security Auditor|Code Health Agent|Idea Skeptic|System Architect|Requirements Engineer|Scope Reviewer|Cortex Librarian|Codebase Explorer)') {
        Deny 'subagent-role-least-privilege' "Read-only auditor/explorer role '$subRole' must not be spawned with write-capable subagent_type='self'"
    }
    if ($subType -match '(?i)^(stage3-design-reviewer|stage4-code-auditor|cortex-librarian|explorer|research)$') {
        if ($subPrompt -match '(?i)\b(apply_patch|git\s+commit|git\s+push|rm\s+-rf|Remove-Item)\b') {
            Deny 'subagent-role-least-privilege' "Read-only subagent '$subType' must not be instructed to mutate files or git state"
        }
    }
    if ((Test-SessionWebTainted $payload) -and ($subType -notmatch '(?i)^(stage3-design-reviewer|stage4-code-auditor|cortex-librarian|explorer|research)$')) {
        Deny 'subagent-taint-delegation-guard' 'Spawning write-capable subagent while session is web-tainted is blocked'
    }
    exit 0
}

if ($toolName -match '^(SendMessage|send_message)$') {
    $msgText = ''
    foreach ($mf in @('message', 'Message', 'content')) {
        if ($toolInput.PSObject.Properties[$mf] -and $null -ne $toolInput.$mf) {
            $msgText = [string]$toolInput.$mf
            break
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($msgText)) {
        $mLines = @($msgText -split "\r?\n")
        if ($mLines.Count -gt 200) {
            Deny 'subagent-mvc-prompt-cap' 'SendMessage payload exceeds 200-line MVC cap; write context to scratch/ and pass the file path'
        }
        if (($msgText -match '(sk-proj-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{50,}|AIzaSy[A-Za-z0-9_-]{33}|fc-[a-f0-9]{32}|tvly-[A-Za-z0-9_-]{20,}|GOCSPX-[A-Za-z0-9_-]{20,})') -or
            ($msgText -match '(?i)(ignore\s+(all\s+)?(previous|prior)\s+instructions|disregard\s+(all\s+)?(previous|prior)\s+(instructions|rules)|<\s*system\s*>)')) {
            Deny 'subagent-message-injection-guard' 'Blocked secret token or prompt-injection override directive in SendMessage'
        }
        if (Test-InvalidRubricScoreBlock $msgText) {
            Deny 'rubric-score-threshold-gate' 'RUBRIC_SCORE block in SendMessage failed validation (require evidence before score, min_score >= 2, and total_score >= threshold for APPROVE/PROCEED)'
        }
    }
    exit 0
}

if ($toolName -match '^mcp__cortex__(store_memory|upsert_entity|create_relation|store_procedure|import_memories)$') {
    $mcpPayloadStr = $toolInput | ConvertTo-Json -Depth 6 -Compress
    if (($mcpPayloadStr -match '(sk-proj-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{50,}|AIzaSy[A-Za-z0-9_-]{33}|fc-[a-f0-9]{32}|tvly-[A-Za-z0-9_-]{20,}|GOCSPX-[A-Za-z0-9_-]{20,})') -or
        ($mcpPayloadStr -match '(?i)(ignore\s+(all\s+)?(previous|prior)\s+instructions|disregard\s+(all\s+)?(previous|prior)\s+(instructions|rules)|<\s*system\s*>|\[VERDICT:\s*APPROVE\])')) {
        Deny 'cortex-memory-poisoning-guard' 'Blocked attempt to persist secret or prompt-injection directive into Cortex long-term memory'
    }
    if (Test-SessionWebTainted $payload) {
        Deny 'untrusted-web-memory-taint' 'Cortex write blocked while session is tainted by external web content'
    }
    exit 0
}

if ($toolName -eq 'WebFetch') {
    $targetUrl = ''
    foreach ($uf in @('url', 'Url')) {
        if ($toolInput.PSObject.Properties[$uf] -and $null -ne $toolInput.$uf) {
            $targetUrl = [string]$toolInput.$uf
            break
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($targetUrl)) {
        if (Test-UnsafeFetchUrl $targetUrl) {
            Deny 'ssrf-local-metadata-url' $targetUrl
        }
        try {
            $baseDir = $null
            if ($payload.PSObject.Properties['artifactDirectoryPath'] -and $payload.artifactDirectoryPath) {
                $baseDir = [string]$payload.artifactDirectoryPath
            } elseif ($payload.PSObject.Properties['cwd'] -and $payload.cwd) {
                $baseDir = [string]$payload.cwd
            }
            if ($baseDir -and (Test-Path -LiteralPath $baseDir)) {
                $scratchDir = Join-Path $baseDir 'scratch'
                if (-not (Test-Path -LiteralPath $scratchDir)) {
                    New-Item -ItemType Directory -Path $scratchDir -Force | Out-Null
                }
                $taintFile = Join-Path $scratchDir '.untrusted_web_taint.json'
                $taintObj = @{
                    url = $targetUrl
                    timestamp = [DateTime]::UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'")
                } | ConvertTo-Json -Compress
                $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
                [System.IO.File]::WriteAllText($taintFile, $taintObj, $utf8NoBom)
            }
        } catch {
            # Ignore taint write failure on read-only paths.
        }
    }
    exit 0
}

$cmd = ''
if ($toolInput.PSObject.Properties['command'] -and $null -ne $toolInput.command) {
    $cmd = [string]$toolInput.command
}
if ([string]::IsNullOrWhiteSpace($cmd)) { exit 0 }

# ---- Anti-Obfuscation Canonicalization ----
function Get-CanonicalCommand {
    param([string]$RawCmd)
    $deobf = $RawCmd -replace '`', '' -replace '\^', ''
    $deobf = $deobf -replace '(?<=[A-Za-z0-9_-])(?:''''|"")|(?:''''|"")(?=[A-Za-z0-9_-])', ''
    $deobf = $deobf -replace '(?<=[A-Za-z0-9_-])["'']([A-Za-z0-9_-]+)["'']|["'']([A-Za-z0-9_-]+)["''](?=[A-Za-z0-9_-])', '$1$2'
    return $deobf
}

$candidates = New-Object System.Collections.Generic.List[string]
$candidates.Add($cmd)
$canon = Get-CanonicalCommand $cmd
if ($canon -ne $cmd) { $candidates.Add($canon) }

foreach ($checkStr in @($cmd, $canon)) {
    if ($checkStr -match '(^|\s)-(?:e|en|enc|enco|encoded|encodedcommand)\s+([A-Za-z0-9+/=]{8,})') {
        $b64 = $Matches[2]
        try {
            $bytes = [System.Convert]::FromBase64String($b64)
            $decUtf16 = [System.Text.Encoding]::Unicode.GetString($bytes)
            $decUtf8  = [System.Text.Encoding]::UTF8.GetString($bytes)
            if ($decUtf16) {
                $candidates.Add($decUtf16)
                $candidates.Add((Get-CanonicalCommand $decUtf16))
            }
            if ($decUtf8) {
                $candidates.Add($decUtf8)
                $candidates.Add((Get-CanonicalCommand $decUtf8))
            }
        } catch {
            Deny 'obfuscated-encoded-command' $checkStr
        }
    }
}

# Exemption pattern: safe ephemeral targets (Standard Build and Sandbox Exemptions).
$exempt = '(^|[\s"'';=/\\])(scratch|tmp|temp|node_modules|dist|build|target|\.venv|__pycache__|\.pytest_cache|\.mypy_cache|\.ruff_cache|\.tox|coverage|htmlcov)([\s"'';/\\]|$)'

foreach ($evalCmd in $candidates) {
    if ((Test-SessionWebTainted $payload) -and
        ($evalCmd -match '(^|[\s;|&(])(curl(\.exe)?|wget(\.exe)?|Invoke-WebRequest|Invoke-RestMethod|iwr|irm|Start-BitsTransfer|scp(\.exe)?|ftp(\.exe)?)\b')) {
        Deny 'untrusted-web-egress-taint' $evalCmd
    }

    if ($evalCmd -match '(^|[\s;|&(])(Invoke-[E]xpression|iex|\[ScriptBlock\]::Create)\b') {
        Deny 'dynamic-code-evaluation' $evalCmd
    }

    if ($evalCmd -match '(sk-proj-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{50,}|AIzaSy[A-Za-z0-9_-]{33}|fc-[a-f0-9]{32}|tvly-[A-Za-z0-9_-]{20,}|GOCSPX-[A-Za-z0-9_-]{20,})') {
        Deny 'inline-secret-token' 'Inline API token detected in command'
    }

    if (($evalCmd -match 'antigravity[/\\]mcp_config\.json(?!\.deprecated-redacted)') -or
        ($evalCmd -match '(^|\s)(cat|type|Get-Content|more|less|head|tail)\s+[^\r\n]*?(^|[/\\"\s])(\.env(?!\.(example|sample|template|dist|schema))|\.aws[/\\]credentials|\.kube[/\\]config|\.docker[/\\]config\.json|\.git-credentials|id_rsa|id_ed25519|id_ecdsa|id_dsa)(["\s]|$)') -or
        ($evalCmd -match '(^|[\s;|&(])(python[0-9.]*|py|node|ruby|perl|php|powershell|pwsh)\b[^\r\n]*?(\.env(?!\.(example|sample|template|dist|schema))|\.aws[/\\]credentials|\.kube[/\\]config|\.docker[/\\]config\.json|\.git-credentials|id_rsa|id_ed25519|id_ecdsa|id_dsa)')) {
        Deny 'secret-file-shell-read' $evalCmd
    }

    if (($evalCmd -notmatch '(?i)[/\\](scratch|tmp|temp)[/\\]') -and
        ($evalCmd -match '(>|>>|\bOut-File\b|\bSet-Content\b|\bAdd-Content\b|\bCopy-Item\b|\bMove-Item\b|\bRemove-Item\b|\bcp\b|\bmv\b|\brm\b|\bdel\b|\btee\b|WriteAllText|WriteAllLines|AppendAllText)[^\r\n]*?(hooks\.json|settings\.json|brc-guard\.ps1|telemetry-append\.ps1|\.pre-commit-config\.yaml|mcp_config\.json|\.mcp\.json|plugin\.json|AGENTS\.md|CLAUDE\.md|CODEX\.md|config\.toml|antigravity\.rules|agentic_telemetry\.md)')) {
        Deny 'harness-config-self-tampering' $evalCmd
    }

    # ---- Rule 1: recursive force delete outside temp/scratch ----
    $segments = [regex]::Split($evalCmd, '&&|\|\||[;|&]')
    foreach ($seg in $segments) {
        $s = $seg.Trim()
        if ($s -eq '') { continue }
        $isRecursiveForceDelete = $false
        if ($s -match '(^|\s)rm(\.exe)?\s+-') {
            $recurse = ($s -match '(^|\s)-[a-zA-Z]*[rR][a-zA-Z]*\b') -or ($s -match '(^|\s)--recursive\b')
            $force   = ($s -match '(^|\s)-[a-zA-Z]*[fF][a-zA-Z]*\b') -or ($s -match '(^|\s)--force\b')
            if ($recurse -and $force) { $isRecursiveForceDelete = $true }
        }
        if (-not $isRecursiveForceDelete -and $s -match '(^|\s)Remove-Item\s') {
            if (($s -match '\s-Recurse\b') -and ($s -match '\s-Force\b')) {
                $isRecursiveForceDelete = $true
            }
        }
        if ($isRecursiveForceDelete -and ($s -notmatch $exempt)) {
            Deny 'recursive-force-delete' $s
        }
    }

    # ---- Rule 2: git push --force / -f to master or main ----
    if ($evalCmd -match 'git\s+push\b') {
        $forceFlag = ($evalCmd -match '(^|\s)--force(?!-with-lease)\b') -or ($evalCmd -match '(^|\s)-f(\s|$)')
        if ($forceFlag -and ($evalCmd -match '(^|[\s:/])(master|main)(\s|$|:)')) {
            Deny 'git-push-force-protected-branch' $evalCmd
        }
    }

    # ---- Rule 3: git reset --hard on master or main ----
    if ($evalCmd -match 'git\s+reset\s+(--\S+\s+)*--hard\b') {
        if ($evalCmd -match '(^|[\s:/])(master|main)(\s|$|:)') {
            Deny 'git-reset-hard-protected-branch' $evalCmd
        }
    }

    # ---- Rule 4: SQL DROP TABLE / DROP DATABASE / TRUNCATE TABLE ----
    $searchOnly = $evalCmd -match '^\s*(grep|rg|git\s+grep|findstr|Select-String|echo|cat|type|Get-Content|less|head|tail)\b'
    if (-not $searchOnly -and ($evalCmd -match '\b(DROP\s+(TABLE|DATABASE)|TRUNCATE\s+TABLE)\b')) {
        Deny 'sql-drop' $evalCmd
    }

    # ---- Rule 4b: git config mutation guard (allow read-only --get / --list / -l) ----
    if (-not $searchOnly -and ($evalCmd -match '(^|[\s;|&(])git(\.exe)?\s+config\b') -and ($evalCmd -notmatch '\s(--get|--get-all|--get-regexp|--list|-l)(\s|$)')) {
        Deny 'git-config-mutation-guard' $evalCmd
    }

    # ---- Rule 4c: git hook-bypass guard (--no-verify and git commit -n / -nm) ----
    if (-not $searchOnly) {
        $gitEval = $evalCmd -replace '(-[a-zA-Z]*m|--message)(?:=|\s*)(?:"[^"]*"|''[^'']*'')', '$1 ""'
        if (($gitEval -match '(^|[\s;|&(])git(\.exe)?\b[^;\r\n|&]*?\s--no-verify(\s|$|[;"''|&])') -or
            ($gitEval -match '(^|[\s;|&(])git(\.exe)?\s+(?:-\S+\s+)*commit\b[^;\r\n|&]*?\s-(?:[a-zA-Z]*n[a-zA-Z]*)\b')) {
            Deny 'git-no-verify-bypass' $evalCmd
        }
    }

    # ---- Rule 5: filesystem creation (mkfs) ----
    if ($evalCmd -match '(^|[\s;&|])mkfs(\.\S+)?\b') {
        Deny 'mkfs' $evalCmd
    }

    # ---- Rule 6: kill every process (kill -9 -1) ----
    if ($evalCmd -match '(^|[\s;&|])kill\s+(-9|-KILL|-s\s+(9|KILL))\s+-1(\s|$)') {
        Deny 'kill-all-processes' $evalCmd
    }

    # ---- Rule 7: disk-wide format and extended destructive infra commands ----
    if (($evalCmd -match '(^|[\s;&|])format(\.com)?\s+[a-zA-Z]:') -or ($evalCmd -match '\bFormat-Volume\b')) {
        Deny 'disk-format' $evalCmd
    }
    if ($evalCmd -match '\b(git\s+clean\s+-[a-zA-Z]*f|docker\s+system\s+prune\s+-a|kubectl\s+delete\s+(namespace|node|--all)|terraform\s+destroy|diskpart|reg\s+delete)\b') {
        Deny 'destructive-infrastructure-command' $evalCmd
    }
}

exit 0
