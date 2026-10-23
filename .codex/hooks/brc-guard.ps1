# brc-guard.ps1 - Blast Radius Containment & MAC PreToolUse guard for OpenAI Codex.
#
# Contract (OpenAI Codex PreToolUse hook):
#   - Stdin receives a JSON object with tool_name, tool_input, cwd, etc.
#   - Exit 0 (with zero stdout) allows the call.
#   - Exit 2 with a human-readable message on stderr blocks the call and feeds
#     stderr back to Codex so it emits a <BLAST_RADIUS> assessment and yields.
#   - Any unexpected parse/runtime error fails open (exit 0) so a broken hook
#     never bricks the session.
#
# Strict 7-bit ASCII only. Zero dynamic eval calls.

$ErrorActionPreference = 'Stop'
$script:PayloadObj = $null

function Get-TelemetryChainTag {
    param([string]$FilePath, [string]$EntryBody)
    $prevChain = '00000000'
    if (Test-Path -LiteralPath $FilePath) {
        $existing = @(Get-Content -LiteralPath $FilePath -Encoding UTF8 -ErrorAction SilentlyContinue | Where-Object { $_ -and $_.Trim() -ne '' })
        if ($existing.Count -gt 0) {
            $last = [string]$existing[$existing.Count - 1]
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

function Resolve-CodexRepoRoot {
    if ($env:CODEX_PROJECT_DIR -and (Test-Path -LiteralPath $env:CODEX_PROJECT_DIR)) {
        return $env:CODEX_PROJECT_DIR
    }
    if ($null -ne $script:PayloadObj -and $script:PayloadObj.PSObject.Properties['cwd'] -and $script:PayloadObj.cwd) {
        $c = [string]$script:PayloadObj.cwd
        if ((Test-Path -LiteralPath (Join-Path $c '.codex')) -or (Test-Path -LiteralPath (Join-Path $c 'CODEX.md'))) {
            return $c
        }
    }
    $candidate = (Resolve-Path (Join-Path $PSScriptRoot '..\..') -ErrorAction SilentlyContinue)
    if ($candidate) { return $candidate.Path }
    return $null
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
        $p2 = Join-Path (Join-Path (Join-Path $cwdStr '.codex') 'telemetry') '.untrusted_web_taint.json'
        if (Test-Path -LiteralPath $p2) { return $true }
        $p3 = Join-Path (Join-Path $cwdStr 'scratch') '.untrusted_web_taint.json'
        if (Test-Path -LiteralPath $p3) { return $true }
    }
    return $false
}

function Write-GuardTelemetry {
    param([string]$Decision, [string]$Rule, [string]$Excerpt)
    try {
        $root = Resolve-CodexRepoRoot
        if ($root) {
            $telDir = Join-Path $root '.codex\telemetry'
            if (-not (Test-Path -LiteralPath $telDir)) {
                New-Item -ItemType Directory -Path $telDir -Force | Out-Null
            }
            $telPath = Join-Path $telDir 'agentic_telemetry.md'
            $sig = "| PreToolUse Guard ($Decision) | $Rule | $Excerpt"
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
        "This operation is high blast radius. Do NOT retry it or attempt a workaround.",
        "Per CODEX.md and .codex/rules/blast-radius.md you MUST now emit a <BLAST_RADIUS> assessment",
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

function Test-SecretPath {
    param([string]$PathStr)
    if ([string]::IsNullOrWhiteSpace($PathStr)) { return $false }
    $norm = $PathStr.Replace('/', '\').Trim()
    $isExample = ($norm -match '\.env\.(example|sample|template|dist|schema)$') -or ($norm -match '\.deprecated-redacted$')
    if ($isExample) { return $false }
    if (($norm -match '(^|\\)\.env(\.[A-Za-z0-9_-]+)?$') -or
        ($norm -match '\.(pem|key|p12|pfx|p8|keystore|jks)$') -or
        ($norm -match '(^|\\)(id_rsa|id_ed25519|id_ecdsa|id_dsa|\.npmrc|\.pypirc|\.netrc|\.git-credentials)$') -or
        ($norm -match '(\.aws\\credentials|\.kube\\config|\.docker\\config\.json)$') -or
        ($norm -match 'antigravity\\mcp_config\.json$')) {
        return $true
    }
    return $false
}

function Test-TamperPath {
    param([string]$PathStr)
    if ([string]::IsNullOrWhiteSpace($PathStr)) { return $false }
    $norm = $PathStr.Replace('/', '\').Trim()
    if ($norm -match '(?i)(^|\\)(scratch|tmp|temp)(\\|$)') { return $false }
    if (($norm -match '(?i)(^|\\)(hooks\.json|settings\.json|config\.toml|antigravity\.rules|brc-guard\.ps1|telemetry-append\.ps1|\.pre-commit-config\.yaml|mcp_config\.json|\.mcp\.json|plugin\.json|CODEX\.md|CLAUDE\.md|AGENTS\.md|agentic_telemetry\.md)$') -or
        ($norm -match '(?i)(^|\\)\.codex\\agents\\[A-Za-z0-9_-]+\.toml$')) {
        return $true
    }
    return $false
}

function Test-GeneratedOutputPath {
    param([string]$PathStr)
    if ([string]::IsNullOrWhiteSpace($PathStr)) { return $false }
    $norm = $PathStr.Replace('/', '\').Trim()
    if ($norm -match '(?i)(^|\\)(scratch|tmp|temp)(\\|$)') { return $false }
    if ($norm -match '(?i)(^|\\)(dist|build)(\\|$)') { return $true }
    return $false
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
                if ($_.Extension -ieq '.json') {
                    $rawJson = Get-Content -LiteralPath $_.FullName -Raw -ErrorAction SilentlyContinue
                    if ($rawJson -match '"status"\s*:\s*"(UNSAT|REFUTED|VACUOUS)"') { return $false }
                }
                return $true
            })
            if ($hits.Count -gt 0) { return $false }
        }
        if (Test-Path -LiteralPath $dir) {
            $rootHits = @(Get-ChildItem -LiteralPath $dir -Filter 'stage0*' -File -ErrorAction SilentlyContinue | Where-Object {
                if ($_.Length -le 0) { return $false }
                if ($_.Extension -ieq '.json') {
                    $rawJson = Get-Content -LiteralPath $_.FullName -Raw -ErrorAction SilentlyContinue
                    if ($rawJson -match '"status"\s*:\s*"(UNSAT|REFUTED|VACUOUS)"') { return $false }
                }
                return $true
            })
            if ($rootHits.Count -gt 0) { return $false }
        }
    }
    return $true
}

function Test-Stage1CandidateSolutionsGate {
    param([string]$PathStr, [string]$BodyStr)
    if ([string]::IsNullOrWhiteSpace($PathStr)) { return $false }
    $norm = $PathStr.Replace('/', '\')
    if ($norm -notmatch '(?i)(^|\\)candidate_solutions\.md$') { return $false }
    if (($BodyStr -notmatch '(?i)Radical\s+Innovator') -or
        ($BodyStr -notmatch '(?i)Enterprise\s+Minimalist') -or
        ($BodyStr -notmatch '(?i)Security\s+Paranoiac')) {
        return $true
    }
    return $false
}

function Test-InvalidRubricScoreBlock {
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return $false }
    $blockMatches = [regex]::Matches($Text, '(?is)<RUBRIC_SCORE>\s*(\{[\s\S]*?\})\s*</RUBRIC_SCORE>')
    if ($blockMatches.Count -eq 0) { return $false }
    $validVerdicts = @('APPROVE', 'REJECT', 'PROCEED', 'HALT', 'TIER_0', 'TIER_1', 'TIER_2')
    $lastVerdict = ''
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
        if (-not $obj.PSObject.Properties['verdict'] -or [string]::IsNullOrWhiteSpace([string]$obj.verdict)) {
            return $true
        }
        $verdict = ([string]$obj.verdict).Trim().ToUpperInvariant()
        if ($verdict -notin $validVerdicts) { return $true }
        $lastVerdict = $verdict
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
        if ($verdict -in @('APPROVE', 'PROCEED')) {
            if ($actualMin -lt 2 -or $actualTotal -lt $effThr) { return $true }
        } elseif ($verdict -eq 'REJECT') {
            if ($actualMin -ge 2 -and $actualTotal -ge $effThr) { return $true }
        }
    }
    if ($blockMatches.Count -eq 1 -and ($Text -match '\[(?:GLOBAL\s+)?VERDICT:\s*([A-Za-z0-9_]+)\]')) {
        $proseVerdict = $Matches[1].Trim().ToUpperInvariant()
        if ($proseVerdict -ne $lastVerdict) { return $true }
    }
    return $false
}

# ---- 1. Multi-Header V4A apply_patch Guard ----
if ($toolName -eq 'apply_patch') {
    $patchText = ''
    foreach ($pf in @('command', 'patch', 'input', 'content')) {
        if ($toolInput.PSObject.Properties[$pf] -and $null -ne $toolInput.$pf) {
            $patchText = [string]$toolInput.$pf
            break
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($patchText)) {
        $headerMatches = [regex]::Matches($patchText, '(?m)^\*\*\* ((?:Add|Update|Delete) File|Move to):\s*(.+?)\s*$')
        $hasMdTarget = $false
        $addedLines = ([regex]::Matches($patchText, '(?m)^\+(?!\+\+)(.*)$') | ForEach-Object { $_.Groups[1].Value }) -join "`n"
        foreach ($m in $headerMatches) {
            $actionVerb = $m.Groups[1].Value.Trim()
            $targetPath = $m.Groups[2].Value.Trim()
            if (Test-SecretPath $targetPath) {
                Deny 'secret-file-access' $targetPath
            }
            if (Test-TamperPath $targetPath) {
                Deny 'harness-config-self-tampering' $targetPath
            }
            if (Test-GeneratedOutputPath $targetPath) {
                Deny 'generated-output-write-guard' $targetPath
            }
            if (($actionVerb -in @('Add File', 'Update File')) -and (Test-MissingStage0Artifact $targetPath $payload)) {
                Deny 'stage0-comprehend-problem-gate' 'Run comprehend-problem (.codex/skills/comprehend-problem/SKILL.md) and write non-empty scratch/stage0_<topic>.md or .json (with SAT status) before writing implementation_plan.md'
            }
            if (($actionVerb -eq 'Add File') -and (Test-Stage1CandidateSolutionsGate $targetPath $addedLines)) {
                Deny 'stage1-candidate-solutions-gate' 'candidate_solutions.md must include all 3 cognitive framing lenses (Radical Innovator, Enterprise Minimalist, Security Paranoiac)'
            }
            if (($actionVerb -in @('Add File', 'Update File')) -and (Test-InvalidRubricScoreBlock $addedLines)) {
                Deny 'rubric-score-threshold-gate' 'RUBRIC_SCORE block failed validation (require evidence before score, min_score >= 2, and total_score >= threshold for APPROVE/PROCEED)'
            }
            if ($targetPath -match '(?i)\.md$') {
                $hasMdTarget = $true
            }
        }
        if ($hasMdTarget -and (Test-SessionWebTainted $payload)) {
            if ($addedLines -match '!\[[^\]]*\]\(\s*https?://') {
                Deny 'untrusted-web-markdown-image-exfil' 'Writing external Markdown image URL while session is web-tainted'
            }
        }
    }
    exit 0
}

# ---- 2. Standard File-Access Tools (Read, Edit, Write, MultiEdit) ----
$filePath = ''
foreach ($pf in @('file_path', 'path', 'notebook_path', 'TargetFile', 'AbsolutePath')) {
    if ($toolInput.PSObject.Properties[$pf] -and $null -ne $toolInput.$pf) {
        $filePath = [string]$toolInput.$pf
        break
    }
}
if ($filePath -ne '') {
    if (Test-SecretPath $filePath) {
        Deny 'secret-file-access' $filePath
    }
    if ($toolName -match '^(Edit|Write|MultiEdit|write_to_file|replace_file_content)$') {
        if (Test-TamperPath $filePath) {
            Deny 'harness-config-self-tampering' $filePath
        }
        if (Test-GeneratedOutputPath $filePath) {
            Deny 'generated-output-write-guard' $filePath
        }
        if (Test-MissingStage0Artifact $filePath $payload) {
            Deny 'stage0-comprehend-problem-gate' 'Run comprehend-problem (.codex/skills/comprehend-problem/SKILL.md) and write non-empty scratch/stage0_<topic>.md or .json (with SAT status) before writing implementation_plan.md'
        }
        $writeBody = ''
        foreach ($cf in @('content', 'new_string', 'CodeContent', 'ReplacementContent')) {
            if ($toolInput.PSObject.Properties[$cf] -and $null -ne $toolInput.$cf) {
                $writeBody += "`n" + [string]$toolInput.$cf
            }
        }
        if (($toolName -match '^(Write|write_to_file)$') -and (Test-Stage1CandidateSolutionsGate $filePath $writeBody)) {
            Deny 'stage1-candidate-solutions-gate' 'candidate_solutions.md must include all 3 cognitive framing lenses (Radical Innovator, Enterprise Minimalist, Security Paranoiac)'
        }
        if (Test-InvalidRubricScoreBlock $writeBody) {
            Deny 'rubric-score-threshold-gate' 'RUBRIC_SCORE block failed validation (require evidence before score, min_score >= 2, and total_score >= threshold for APPROVE/PROCEED)'
        }
        if (($filePath -match '(?i)\.md$') -and (Test-SessionWebTainted $payload)) {
            if ($writeBody -match '!\[[^\]]*\]\(\s*https?://') {
                Deny 'untrusted-web-markdown-image-exfil' 'Writing external Markdown image URL while session is web-tainted'
            }
        }
    }
}

# ---- 3. Subagent MAC Guards (spawn_agent, send_input, Agent, Task) ----
if ($toolName -match '^(spawn_agent|Agent|Task)$') {
    $subPrompt = ''
    foreach ($mf in @('message', 'prompt', 'Prompt')) {
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
    $agentType = ''
    foreach ($af in @('agent_type', 'subagent_type', 'role', 'Role')) {
        if ($toolInput.PSObject.Properties[$af] -and $null -ne $toolInput.$af) {
            $agentType = [string]$toolInput.$af
            break
        }
    }
    if ($agentType -match '(?i)^(stage3-design-reviewer|stage4-code-auditor|cortex-librarian|explorer)$') {
        if ($subPrompt -match '(?i)\b(apply_patch|git\s+commit|git\s+push|rm\s+-rf|Remove-Item)\b') {
            Deny 'subagent-role-least-privilege' "Read-only subagent '$agentType' must not be instructed to mutate files or git state"
        }
    }
    if ((Test-SessionWebTainted $payload) -and ($agentType -notmatch '(?i)^(stage3-design-reviewer|stage4-code-auditor|cortex-librarian|explorer)$')) {
        Deny 'subagent-taint-delegation-guard' 'Spawning write-capable subagent while session is web-tainted is blocked'
    }
    exit 0
}

if ($toolName -match '^(send_input|send_message)$') {
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
            Deny 'subagent-mvc-prompt-cap' 'send_input payload exceeds 200-line MVC cap; write context to scratch/ and pass the file path'
        }
        if (($msgText -match '(sk-proj-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{50,}|AIzaSy[A-Za-z0-9_-]{33}|fc-[a-f0-9]{32}|tvly-[A-Za-z0-9_-]{20,}|GOCSPX-[A-Za-z0-9_-]{20,})') -or
            ($msgText -match '(?i)(ignore\s+(all\s+)?(previous|prior)\s+instructions|disregard\s+(all\s+)?(previous|prior)\s+(instructions|rules)|<\s*system\s*>)')) {
            Deny 'subagent-message-injection-guard' 'Blocked secret token or prompt-injection override directive in send_input'
        }
        if (Test-InvalidRubricScoreBlock $msgText) {
            Deny 'rubric-score-threshold-gate' 'RUBRIC_SCORE block in send_input failed validation (require evidence before score, min_score >= 2, and total_score >= threshold for APPROVE/PROCEED)'
        }
    }
    exit 0
}

# ---- 4. Cortex MCP Memory Poisoning & Taint Guard ----
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

# ---- 5. SSRF & Web Taint Marker Creation ----
if ($toolName -match '^(WebFetch|web_fetch)$') {
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
            $root = Resolve-CodexRepoRoot
            if ($root) {
                $telDir = Join-Path $root '.codex\telemetry'
                if (-not (Test-Path -LiteralPath $telDir)) {
                    New-Item -ItemType Directory -Path $telDir -Force | Out-Null
                }
                $taintFile = Join-Path $telDir '.untrusted_web_taint.json'
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

# ---- 6. Shell Command Guards (Bash / exec_command / PowerShell) ----
$cmd = ''
foreach ($cf in @('command', 'cmd', 'CommandLine')) {
    if ($toolInput.PSObject.Properties[$cf] -and $null -ne $toolInput.$cf) {
        $cmd = [string]$toolInput.$cf
        break
    }
}
if ([string]::IsNullOrWhiteSpace($cmd)) { exit 0 }

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
        ($evalCmd -match '(>|>>|\bOut-File\b|\bSet-Content\b|\bAdd-Content\b|\bCopy-Item\b|\bMove-Item\b|\bRemove-Item\b|\bcp\b|\bmv\b|\brm\b|\bdel\b|\btee\b|WriteAllText|WriteAllLines|AppendAllText)[^\r\n]*?(hooks\.json|settings\.json|config\.toml|antigravity\.rules|brc-guard\.ps1|telemetry-append\.ps1|\.pre-commit-config\.yaml|mcp_config\.json|\.mcp\.json|plugin\.json|CODEX\.md|CLAUDE\.md|AGENTS\.md|agentic_telemetry\.md)')) {
        Deny 'harness-config-self-tampering' $evalCmd
    }

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

    if ($evalCmd -match 'git\s+push\b') {
        $forceFlag = ($evalCmd -match '(^|\s)--force(?!-with-lease)\b') -or ($evalCmd -match '(^|\s)-f(\s|$)')
        if ($forceFlag -and ($evalCmd -match '(^|[\s:/])(master|main)(\s|$|:)')) {
            Deny 'git-push-force-protected-branch' $evalCmd
        }
    }

    if ($evalCmd -match 'git\s+reset\s+(--\S+\s+)*--hard\b') {
        Deny 'git-reset-hard-protected-branch' $evalCmd
    }

    $searchOnly = $evalCmd -match '^\s*(grep|rg|git\s+grep|findstr|Select-String|echo|cat|type|Get-Content|less|head|tail)\b'
    if (-not $searchOnly -and ($evalCmd -match '\b(DROP\s+(TABLE|DATABASE)|TRUNCATE\s+TABLE)\b')) {
        Deny 'sql-drop' $evalCmd
    }

    if (-not $searchOnly -and ($evalCmd -match '(^|[\s;|&(])git(\.exe)?\s+config\b') -and ($evalCmd -notmatch '\s(--get|--get-all|--get-regexp|--list|-l)(\s|$)')) {
        Deny 'git-config-mutation-guard' $evalCmd
    }

    if (-not $searchOnly) {
        $gitEval = $evalCmd -replace '(-[a-zA-Z]*m|--message)(?:=|\s*)(?:"[^"]*"|''[^'']*'')', '$1 ""'
        if (($gitEval -match '(^|[\s;|&(])git(\.exe)?\b[^;\r\n|&]*?\s--no-verify(\s|$|[;"''|&])') -or
            ($gitEval -match '(^|[\s;|&(])git(\.exe)?\s+(?:-\S+\s+)*commit\b[^;\r\n|&]*?\s-(?:[a-zA-Z]*n[a-zA-Z]*)\b')) {
            Deny 'git-no-verify-bypass' $evalCmd
        }
    }

    if ($evalCmd -match '(^|[\s;&|])mkfs(\.\S+)?\b') {
        Deny 'mkfs' $evalCmd
    }

    if ($evalCmd -match '(^|[\s;&|])kill\s+(-9|-KILL|-s\s+(9|KILL))\s+-1(\s|$)') {
        Deny 'kill-all-processes' $evalCmd
    }

    if (($evalCmd -match '(^|[\s;&|])format(\.com)?\s+[a-zA-Z]:') -or ($evalCmd -match '\bFormat-Volume\b')) {
        Deny 'disk-format' $evalCmd
    }
    if ($evalCmd -match '\b(git\s+clean\s+-[a-zA-Z]*f|docker\s+system\s+prune\s+-a|kubectl\s+delete\s+(namespace|node|--all)|terraform\s+destroy|diskpart|reg\s+delete)\b') {
        Deny 'destructive-infrastructure-command' $evalCmd
    }
}

exit 0
