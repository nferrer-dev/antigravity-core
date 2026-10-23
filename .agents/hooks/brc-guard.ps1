# brc-guard.ps1 - Blast Radius Containment (BRC) and Secret PreToolUse guard.
#
# Supports Antigravity PreToolUse payloads (toolCall.name, toolCall.args)
# as well as tool_name / tool_input envelopes.
# Antigravity output contract: JSON on stdout {"decision": "allow"|"deny"|"force_ask", "reason": "..."} + exit 0.
# PowerShell 5.1 compatible. Strict 7-bit ASCII only. Parse-level fail-open, rule-level fail-closed.

$ErrorActionPreference = 'Stop'

$script:IsAntigravity = $false
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

function Write-GuardTelemetry {
    param([string]$Decision, [string]$Rule, [string]$Excerpt)
    try {
        if ($null -ne $script:PayloadObj -and $script:PayloadObj.PSObject.Properties['artifactDirectoryPath']) {
            $artDir = [string]$script:PayloadObj.artifactDirectoryPath
            if (-not [string]::IsNullOrWhiteSpace($artDir) -and (Test-Path -LiteralPath $artDir)) {
                $telPath = Join-Path $artDir 'agentic_telemetry.md'
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
        }
    } catch {
        # Never block guard execution on telemetry write failure.
    }
}

function Emit-Allow {
    if ($script:IsAntigravity) {
        [Console]::Out.WriteLine('{"decision":"allow"}')
    }
    exit 0
}

function Emit-Deny {
    param([string]$Rule, [string]$Detail)
    $excerpt = $Detail -replace '\s+', ' '
    if ($excerpt.Length -gt 160) { $excerpt = $excerpt.Substring(0, 160) + '...' }
    Write-GuardTelemetry -Decision 'deny' -Rule $Rule -Excerpt $excerpt
    $reason = "BLOCKED by BRC/Secret guard [$Rule]: $excerpt. Emit a <BLAST_RADIUS> assessment and request human approval before proceeding."
    if ($script:IsAntigravity) {
        $out = @{ decision = 'deny'; reason = $reason } | ConvertTo-Json -Compress
        [Console]::Out.WriteLine($out)
        exit 0
    } else {
        [Console]::Error.WriteLine($reason)
        exit 2
    }
}

function Emit-ForceAsk {
    param([string]$Rule, [string]$Detail)
    $excerpt = $Detail -replace '\s+', ' '
    if ($excerpt.Length -gt 160) { $excerpt = $excerpt.Substring(0, 160) + '...' }
    Write-GuardTelemetry -Decision 'force_ask' -Rule $Rule -Excerpt $excerpt
    $reason = "PROTECTED HARNESS CONFIG [$Rule]: $excerpt requires explicit user confirmation."
    if ($script:IsAntigravity) {
        $out = @{ decision = 'force_ask'; reason = $reason } | ConvertTo-Json -Compress
        [Console]::Out.WriteLine($out)
        exit 0
    } else {
        [Console]::Error.WriteLine($reason)
        exit 2
    }
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
$argsObj = $null

if ($payload.PSObject.Properties['toolCall'] -and $null -ne $payload.toolCall) {
    $script:IsAntigravity = $true
    if ($payload.toolCall.PSObject.Properties['name']) {
        $toolName = [string]$payload.toolCall.name
    }
    if ($payload.toolCall.PSObject.Properties['args']) {
        $argsObj = $payload.toolCall.args
    }
} elseif ($payload.PSObject.Properties['tool_input'] -or $payload.PSObject.Properties['tool_name']) {
    if ($payload.PSObject.Properties['tool_name']) {
        $toolName = [string]$payload.tool_name
    }
    if ($payload.PSObject.Properties['tool_input']) {
        $argsObj = $payload.tool_input
    }
} else {
    exit 0
}

# ---- Extract command string and/or target file path ----
$cmd = ''
$filePath = ''

if ($null -ne $argsObj) {
    foreach ($cmdField in @('CommandLine', 'command', 'cmd')) {
        if ($argsObj.PSObject.Properties[$cmdField] -and $null -ne $argsObj.$cmdField) {
            $cmd = [string]$argsObj.$cmdField
            break
        }
    }
    foreach ($pathField in @('AbsolutePath', 'TargetFile', 'file_path', 'path', 'Path')) {
        if ($argsObj.PSObject.Properties[$pathField] -and $null -ne $argsObj.$pathField) {
            $filePath = [string]$argsObj.$pathField
            break
        }
    }
}

# ---- File-Access Secret & Self-Tampering Guards ----
function Test-SecretFilePath {
    param([string]$PathStr)
    if ([string]::IsNullOrWhiteSpace($PathStr)) { return $false }
    $norm = $PathStr.Replace('/', '\')
    # Allow .env.example, .env.sample, .env.template, and .deprecated-redacted
    if ($norm -match '\.env\.(example|sample|template|dist|schema)$') { return $false }
    if ($norm -match '\.deprecated-redacted$') { return $false }
    if ($norm -match '(^|\\)\.env(\.[A-Za-z0-9_-]+)?$') { return $true }
    if ($norm -match '\.(pem|key|p12|pfx|p8|keystore|jks)$') { return $true }
    if ($norm -match '(^|\\)(id_rsa|id_ed25519|id_ecdsa|id_dsa|\.npmrc|\.pypirc|\.netrc|\.git-credentials)$') { return $true }
    if ($norm -match '(\.aws\\credentials|\.kube\\config|\.docker\\config\.json)$') { return $true }
    if ($norm -match 'antigravity\\mcp_config\.json$') { return $true }
    return $false
}

function Test-TamperFilePath {
    param([string]$PathStr)
    if ([string]::IsNullOrWhiteSpace($PathStr)) { return $false }
    $norm = $PathStr.Replace('/', '\')
    if ($norm -match '(?i)(^|\\)(scratch|tmp|temp)(\\|$)') { return $false }
    if ($norm -match '(?i)(^|\\)(hooks\.json|settings\.json|brc-guard\.ps1|telemetry-append\.ps1|\.pre-commit-config\.yaml|mcp_config\.json|\.mcp\.json|plugin\.json|AGENTS\.md|CLAUDE\.md|CODEX\.md|config\.toml|antigravity\.rules|agentic_telemetry\.md)$') {
        return $true
    }
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

function Test-MissingStageArtifact {
    param([string]$PathStr, $PayloadObj, [string]$StageFilter)
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
    $parentDir = Split-Path -Parent $norm
    if (-not [string]::IsNullOrWhiteSpace($parentDir) -and -not $searchDirs.Contains($parentDir)) {
        $searchDirs.Add($parentDir)
    }
    if ($searchDirs.Count -eq 0) { return $false }
    foreach ($dir in $searchDirs) {
        $scratchDir = Join-Path $dir 'scratch'
        if (Test-Path -LiteralPath $scratchDir) {
            $hits = @(Get-ChildItem -LiteralPath $scratchDir -Filter $StageFilter -File -ErrorAction SilentlyContinue | Where-Object {
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
            $rootHits = @(Get-ChildItem -LiteralPath $dir -Filter $StageFilter -File -ErrorAction SilentlyContinue | Where-Object {
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

function Test-MissingStage0Artifact {
    param([string]$PathStr, $PayloadObj)
    return (Test-MissingStageArtifact -PathStr $PathStr -PayloadObj $PayloadObj -StageFilter 'stage0*')
}

function Test-PrematureExecutionLock {
    param([string]$PathStr, $ArgsObj, $PayloadObj)
    if ($null -eq $ArgsObj) { return $false }
    if (-not $ArgsObj.PSObject.Properties['ArtifactMetadata'] -or $null -eq $ArgsObj.ArtifactMetadata) { return $false }
    $meta = $ArgsObj.ArtifactMetadata
    if (-not $meta.PSObject.Properties['RequestFeedback'] -or $meta.RequestFeedback -ne $true) { return $false }
    return (Test-MissingStageArtifact -PathStr $PathStr -PayloadObj $PayloadObj -StageFilter 'stage3*')
}

function Test-GeneratedOutputPath {
    param([string]$PathStr)
    if ([string]::IsNullOrWhiteSpace($PathStr)) { return $false }
    $norm = $PathStr.Replace('/', '\')
    if ($norm -match '(?i)(^|\\)(scratch|tmp|temp)(\\|$)') { return $false }
    if ($norm -match '(?i)(^|\\)(dist|build)(\\|$)') { return $true }
    return $false
}

function Get-WriteContentString {
    param($ArgsObj)
    if ($null -eq $ArgsObj) { return '' }
    $parts = New-Object System.Collections.Generic.List[string]
    foreach ($cf in @('CodeContent', 'ReplacementContent', 'new_string', 'content')) {
        if ($ArgsObj.PSObject.Properties[$cf] -and $null -ne $ArgsObj.$cf) {
            $parts.Add([string]$ArgsObj.$cf)
        }
    }
    if ($ArgsObj.PSObject.Properties['edits'] -and $null -ne $ArgsObj.edits) {
        foreach ($ed in @($ArgsObj.edits)) {
            if ($null -ne $ed -and $ed.PSObject.Properties['new_string'] -and $null -ne $ed.new_string) {
                $parts.Add([string]$ed.new_string)
            }
        }
    }
    return ($parts -join "`n")
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

$isWriteTool = $toolName -match '^(write_to_file|(?:multi_)?replace_file_content|(?:Multi)?Edit|Write)$'
$isReadOrWriteTool = $isWriteTool -or ($toolName -match '^(view_file|Read)$')

if ($isReadOrWriteTool -and (Test-SecretFilePath $filePath)) {
    Emit-Deny 'secret-file-access' $filePath
}

if ($isWriteTool -and (Test-TamperFilePath $filePath)) {
    Emit-ForceAsk 'harness-config-self-tampering' $filePath
}

if ($isWriteTool -and (Test-GeneratedOutputPath $filePath)) {
    Emit-Deny 'generated-output-write-guard' 'Edit source files instead of /dist or /build output directories'
}

if ($isWriteTool -and (Test-MissingStage0Artifact $filePath $payload)) {
    Emit-Deny 'stage0-comprehend-problem-gate' 'Run comprehend-problem (.agents/skills/comprehend-problem/SKILL.md) and write non-empty scratch/stage0_<topic>.md or .json (with SAT status) before writing implementation_plan.md'
}

if ($isWriteTool -and (Test-PrematureExecutionLock $filePath $argsObj $payload)) {
    Emit-Deny 'stage3-premature-execution-lock' 'Complete Stage 3 design-validate and write non-empty scratch/stage3_<topic>.md or .json before setting RequestFeedback=true on implementation_plan.md'
}

if (($toolName -match '^(write_to_file|Write)$') -and (Test-Stage1CandidateSolutionsGate $filePath $argsObj)) {
    Emit-Deny 'stage1-candidate-solutions-gate' 'candidate_solutions.md must include all 3 cognitive framing lenses (Radical Innovator, Enterprise Minimalist, Security Paranoiac)'
}

if ($isWriteTool -and (Test-InvalidRubricScoreBlock (Get-WriteContentString $argsObj))) {
    Emit-Deny 'rubric-score-threshold-gate' 'RUBRIC_SCORE block failed validation (require evidence before score, min_score >= 2, and total_score >= threshold for APPROVE/PROCEED)'
}

if ($isWriteTool -and ($filePath -match '(?i)\.md$') -and $payload.PSObject.Properties['artifactDirectoryPath'] -and $payload.artifactDirectoryPath) {
    $taintMdPath = Join-Path (Join-Path ([string]$payload.artifactDirectoryPath) 'scratch') '.untrusted_web_taint.json'
    if (Test-Path -LiteralPath $taintMdPath) {
        $mdBody = Get-WriteContentString $argsObj
        if ($mdBody -match '!\[[^\]]*\]\(\s*https?://') {
            Emit-ForceAsk 'untrusted-web-markdown-image-exfil' 'Writing external Markdown image URL while session is web-tainted requires confirmation'
        }
    }
}

if ($toolName -eq 'send_message' -and $null -ne $argsObj) {
    $msgText = ''
    foreach ($mf in @('Message', 'message', 'content')) {
        if ($argsObj.PSObject.Properties[$mf] -and $null -ne $argsObj.$mf) {
            $msgText = [string]$argsObj.$mf
            break
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($msgText)) {
        $mLines = @($msgText -split "\r?\n")
        if ($mLines.Count -gt 200) {
            Emit-Deny 'subagent-mvc-prompt-cap' 'send_message payload exceeds 200-line MVC cap; write context to scratch/ and pass the file path'
        }
        if (($msgText -match '(sk-proj-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{50,}|AIzaSy[A-Za-z0-9_-]{33}|fc-[a-f0-9]{32}|tvly-[A-Za-z0-9_-]{20,}|GOCSPX-[A-Za-z0-9_-]{20,})') -or
            ($msgText -match '(?i)(ignore\s+(all\s+)?(previous|prior)\s+instructions|disregard\s+(all\s+)?(previous|prior)\s+(instructions|rules)|<\s*system\s*>)')) {
            Emit-Deny 'subagent-message-injection-guard' 'Blocked secret token or prompt-injection override directive in inter-agent send_message'
        }
        if (Test-InvalidRubricScoreBlock $msgText) {
            Emit-Deny 'rubric-score-threshold-gate' 'RUBRIC_SCORE block in send_message failed validation (require evidence before score, min_score >= 2, and total_score >= threshold for APPROVE/PROCEED)'
        }
    }
    Emit-Allow
}

if ($toolName -eq 'invoke_subagent' -and $null -ne $argsObj -and $argsObj.PSObject.Properties['Subagents'] -and $null -ne $argsObj.Subagents) {
    $hasWebTaint = $false
    if ($payload.PSObject.Properties['artifactDirectoryPath'] -and $payload.artifactDirectoryPath) {
        $taintSubPath = Join-Path (Join-Path ([string]$payload.artifactDirectoryPath) 'scratch') '.untrusted_web_taint.json'
        if (Test-Path -LiteralPath $taintSubPath) { $hasWebTaint = $true }
    }
    foreach ($sub in @($argsObj.Subagents)) {
        if ($null -eq $sub) { continue }
        if ($sub.PSObject.Properties['Prompt'] -and $null -ne $sub.Prompt) {
            $pLines = @(([string]$sub.Prompt) -split "\r?\n")
            if ($pLines.Count -gt 200) {
                Emit-Deny 'subagent-mvc-prompt-cap' 'Subagent Prompt exceeds 200-line MVC cap; write context to scratch/ and pass the file path'
            }
        }
        $subRole = ''
        if ($sub.PSObject.Properties['Role'] -and $null -ne $sub.Role) { $subRole = [string]$sub.Role }
        $subType = ''
        if ($sub.PSObject.Properties['TypeName'] -and $null -ne $sub.TypeName) { $subType = [string]$sub.TypeName }
        if ($subType -ieq 'self' -and $subRole -match '(?i)(Style Expert|Security Auditor|Code Health Agent|Idea Skeptic|System Architect|Requirements Engineer|Scope Reviewer|Cortex Librarian|Codebase Explorer)') {
            Emit-Deny 'subagent-role-least-privilege' "Read-only auditor/explorer role '$subRole' must not be spawned with write-capable TypeName='self'"
        }
        if ($hasWebTaint -and $subType -ieq 'self') {
            Emit-ForceAsk 'subagent-taint-delegation-guard' "Spawning write-capable subagent '$subRole' (TypeName='self') while session is web-tainted requires confirmation"
        }
    }
}

if ($toolName -eq 'schedule' -and $null -ne $argsObj) {
    if ($argsObj.PSObject.Properties['DurationSeconds'] -and $null -ne $argsObj.DurationSeconds -and $argsObj.PSObject.Properties['TimerCondition'] -and ([string]$argsObj.TimerCondition) -match '^(?i)any$') {
        Emit-Deny 'schedule-patience-timer-condition' 'One-shot schedule timers must use TimerCondition="never" (or a specific sender ID) per Asynchronous Patience Protocol'
    }
}

if (($toolName -eq 'call_mcp_tool' -or $toolName -match '^mcp__cortex__') -and $null -ne $argsObj) {
    $srvName = ''
    $mcpTool = ''
    if ($toolName -match '^mcp__cortex__(.+)$') {
        $srvName = 'cortex'
        $mcpTool = $Matches[1]
    } else {
        foreach ($sf in @('ServerName', 'server_name', 'server')) {
            if ($argsObj.PSObject.Properties[$sf] -and $null -ne $argsObj.$sf) {
                $srvName = [string]$argsObj.$sf
                break
            }
        }
        foreach ($tf in @('ToolName', 'tool_name', 'tool')) {
            if ($argsObj.PSObject.Properties[$tf] -and $null -ne $argsObj.$tf) {
                $mcpTool = [string]$argsObj.$tf
                break
            }
        }
    }
    if ($srvName -ieq 'cortex' -and $mcpTool -match '^(?i)(store_memory|upsert_entity|create_relation|store_procedure|import_memories)$') {
        $mcpPayloadStr = $argsObj | ConvertTo-Json -Depth 6 -Compress
        if (($mcpPayloadStr -match '(sk-proj-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{50,}|AIzaSy[A-Za-z0-9_-]{33}|fc-[a-f0-9]{32}|tvly-[A-Za-z0-9_-]{20,}|GOCSPX-[A-Za-z0-9_-]{20,})') -or
            ($mcpPayloadStr -match '(?i)(ignore\s+(all\s+)?(previous|prior)\s+instructions|disregard\s+(all\s+)?(previous|prior)\s+(instructions|rules)|<\s*system\s*>|\[VERDICT:\s*APPROVE\])')) {
            Emit-Deny 'cortex-memory-poisoning-guard' 'Blocked attempt to persist secret or prompt-injection directive into Cortex long-term memory'
        }
        if ($payload.PSObject.Properties['artifactDirectoryPath'] -and $payload.artifactDirectoryPath) {
            $taintCheckPath = Join-Path (Join-Path ([string]$payload.artifactDirectoryPath) 'scratch') '.untrusted_web_taint.json'
            if (Test-Path -LiteralPath $taintCheckPath) {
                Emit-ForceAsk 'untrusted-web-memory-taint' "Cortex $mcpTool requires confirmation while session is tainted by external web content"
            }
        }
    }
    Emit-Allow
}

if ($toolName -match '^(read_url_content|WebFetch)$' -and $null -ne $argsObj) {
    $targetUrl = ''
    foreach ($uField in @('Url', 'url')) {
        if ($argsObj.PSObject.Properties[$uField] -and $null -ne $argsObj.$uField) {
            $targetUrl = [string]$argsObj.$uField
            break
        }
    }
    if (-not [string]::IsNullOrWhiteSpace($targetUrl)) {
        if (Test-UnsafeFetchUrl $targetUrl) {
            Emit-Deny 'ssrf-local-metadata-url' $targetUrl
        }
        try {
            if ($payload.PSObject.Properties['artifactDirectoryPath'] -and $payload.artifactDirectoryPath) {
                $artDir = [string]$payload.artifactDirectoryPath
                if (Test-Path -LiteralPath $artDir) {
                    $scratchDir = Join-Path $artDir 'scratch'
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
            }
        } catch {
            # Ignore taint write failure on read-only paths.
        }
    }
    Emit-Allow
}

if ([string]::IsNullOrWhiteSpace($cmd)) {
    Emit-Allow
}

# ---- Anti-Obfuscation Canonicalization ----
function Get-CanonicalCommand {
    param([string]$RawCmd)
    # Strip PowerShell backticks, cmd carets, and quote-splitting obfuscation
    $deobf = $RawCmd -replace '`', '' -replace '\^', ''
    $deobf = $deobf -replace '(?<=[A-Za-z0-9_-])(?:''''|"")|(?:''''|"")(?=[A-Za-z0-9_-])', ''
    $deobf = $deobf -replace '(?<=[A-Za-z0-9_-])["'']([A-Za-z0-9_-]+)["'']|["'']([A-Za-z0-9_-]+)["''](?=[A-Za-z0-9_-])', '$1$2'
    return $deobf
}

$candidates = New-Object System.Collections.Generic.List[string]
$candidates.Add($cmd)
$canon = Get-CanonicalCommand $cmd
if ($canon -ne $cmd) { $candidates.Add($canon) }

# Detect -EncodedCommand / -encoded / -enco / -enc / -en / -e with Base64 payload
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
            Emit-Deny 'obfuscated-encoded-command' $checkStr
        }
    }
}

$exempt = '(^|[\s"'';=/\\])(scratch|tmp|temp|node_modules|dist|build|target|\.venv|__pycache__|\.pytest_cache|\.mypy_cache|\.ruff_cache|\.tox|coverage|htmlcov)([\s"'';/\\]|$)'

foreach ($evalCmd in $candidates) {
    # Stateful IFC (Fides) egress check when session is tainted by external web content
    if ($payload.PSObject.Properties['artifactDirectoryPath'] -and $payload.artifactDirectoryPath) {
        $taintCheckPath = Join-Path (Join-Path ([string]$payload.artifactDirectoryPath) 'scratch') '.untrusted_web_taint.json'
        if ((Test-Path -LiteralPath $taintCheckPath) -and
            ($evalCmd -match '(^|[\s;|&(])(curl(\.exe)?|wget(\.exe)?|Invoke-WebRequest|Invoke-RestMethod|iwr|irm|Start-BitsTransfer|scp(\.exe)?|ftp(\.exe)?)\b')) {
            Emit-ForceAsk 'untrusted-web-egress-taint' $evalCmd
        }
    }

    # Dynamic eval / scriptblock creation block
    if ($evalCmd -match '(^|[\s;|&(])(Invoke-[E]xpression|iex|\[ScriptBlock\]::Create)\b') {
        Emit-Deny 'dynamic-code-evaluation' $evalCmd
    }

    # Inline high-confidence secret token literals
    if ($evalCmd -match '(sk-proj-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{50,}|AIzaSy[A-Za-z0-9_-]{33}|fc-[a-f0-9]{32}|tvly-[A-Za-z0-9_-]{20,}|GOCSPX-[A-Za-z0-9_-]{20,})') {
        Emit-Deny 'inline-secret-token' 'Inline API token detected in command'
    }

    # Shell access to legacy antigravity/mcp_config.json, .env, or cloud/SSH credentials
    if (($evalCmd -match 'antigravity[/\\]mcp_config\.json(?!\.deprecated-redacted)') -or
        ($evalCmd -match '(^|\s)(cat|type|Get-Content|more|less|head|tail)\s+[^\r\n]*?(^|[/\\"\s])(\.env(?!\.(example|sample|template|dist|schema))|\.aws[/\\]credentials|\.kube[/\\]config|\.docker[/\\]config\.json|\.git-credentials|id_rsa|id_ed25519|id_ecdsa|id_dsa)(["\s]|$)') -or
        ($evalCmd -match '(^|[\s;|&(])(python[0-9.]*|py|node|ruby|perl|php|powershell|pwsh)\b[^\r\n]*?(\.env(?!\.(example|sample|template|dist|schema))|\.aws[/\\]credentials|\.kube[/\\]config|\.docker[/\\]config\.json|\.git-credentials|id_rsa|id_ed25519|id_ecdsa|id_dsa)')) {
        Emit-Deny 'secret-file-shell-read' $evalCmd
    }

    # Shell self-tampering writes/redirects targeting governance configs
    if (($evalCmd -notmatch '(?i)[/\\](scratch|tmp|temp)[/\\]') -and
        ($evalCmd -match '(>|>>|\bOut-File\b|\bSet-Content\b|\bAdd-Content\b|\bCopy-Item\b|\bMove-Item\b|\bRemove-Item\b|\bcp\b|\bmv\b|\brm\b|\bdel\b|\btee\b|WriteAllText|WriteAllLines|AppendAllText)[^\r\n]*?(hooks\.json|settings\.json|brc-guard\.ps1|telemetry-append\.ps1|\.pre-commit-config\.yaml|mcp_config\.json|\.mcp\.json|plugin\.json|AGENTS\.md|CLAUDE\.md|CODEX\.md|config\.toml|antigravity\.rules|agentic_telemetry\.md)')) {
        Emit-ForceAsk 'harness-config-self-tampering' $evalCmd
    }

    # Rule 1: recursive force delete outside temp/scratch
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
            Emit-Deny 'recursive-force-delete' $s
        }
    }

    # Rule 2: git push --force / -f to master or main
    if ($evalCmd -match 'git\s+push\b') {
        $forceFlag = ($evalCmd -match '(^|\s)--force(?!-with-lease)\b') -or ($evalCmd -match '(^|\s)-f(\s|$)')
        if ($forceFlag -and ($evalCmd -match '(^|[\s:/])(master|main)(\s|$|:)')) {
            Emit-Deny 'git-push-force-protected-branch' $evalCmd
        }
    }

    # Rule 3: git reset --hard on master or main
    if ($evalCmd -match 'git\s+reset\s+(--\S+\s+)*--hard\b') {
        if ($evalCmd -match '(^|[\s:/])(master|main)(\s|$|:)') {
            Emit-Deny 'git-reset-hard-protected-branch' $evalCmd
        }
    }

    # Rule 4: SQL DROP TABLE / DROP DATABASE / TRUNCATE TABLE
    $searchOnly = $evalCmd -match '^\s*(grep|rg|git\s+grep|findstr|Select-String|echo|cat|type|Get-Content|less|head|tail)\b'
    if (-not $searchOnly -and ($evalCmd -match '\b(DROP\s+(TABLE|DATABASE)|TRUNCATE\s+TABLE)\b')) {
        Emit-Deny 'sql-drop' $evalCmd
    }

    # Rule 4b: git config mutation guard (allow read-only --get / --list / -l)
    if (-not $searchOnly -and ($evalCmd -match '(^|[\s;|&(])git(\.exe)?\s+config\b') -and ($evalCmd -notmatch '\s(--get|--get-all|--get-regexp|--list|-l)(\s|$)')) {
        Emit-Deny 'git-config-mutation-guard' $evalCmd
    }

    # Rule 4c: git hook-bypass guard (--no-verify and git commit -n / -nm)
    if (-not $searchOnly) {
        $gitEval = $evalCmd -replace '(-[a-zA-Z]*m|--message)(?:=|\s*)(?:"[^"]*"|''[^'']*'')', '$1 ""'
        if (($gitEval -match '(^|[\s;|&(])git(\.exe)?\b[^;\r\n|&]*?\s--no-verify(\s|$|[;"''|&])') -or
            ($gitEval -match '(^|[\s;|&(])git(\.exe)?\s+(?:-\S+\s+)*commit\b[^;\r\n|&]*?\s-(?:[a-zA-Z]*n[a-zA-Z]*)\b')) {
            Emit-Deny 'git-no-verify-bypass' $evalCmd
        }
    }

    # Rule 5: filesystem creation (mkfs)
    if ($evalCmd -match '(^|[\s;&|])mkfs(\.\S+)?\b') {
        Emit-Deny 'mkfs' $evalCmd
    }

    # Rule 6: kill every process (kill -9 -1)
    if ($evalCmd -match '(^|[\s;&|])kill\s+(-9|-KILL|-s\s+(9|KILL))\s+-1(\s|$)') {
        Emit-Deny 'kill-all-processes' $evalCmd
    }

    # Rule 7: disk-wide format and extended destructive infra commands
    if (($evalCmd -match '(^|[\s;&|])format(\.com)?\s+[a-zA-Z]:') -or ($evalCmd -match '\bFormat-Volume\b')) {
        Emit-Deny 'disk-format' $evalCmd
    }
    if ($evalCmd -match '\b(git\s+clean\s+-[a-zA-Z]*f|docker\s+system\s+prune\s+-a|kubectl\s+delete\s+(namespace|node|--all)|terraform\s+destroy|diskpart|reg\s+delete)\b') {
        Emit-Deny 'destructive-infrastructure-command' $evalCmd
    }
}

Emit-Allow

