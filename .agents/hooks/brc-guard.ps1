# brc-guard.ps1 - Blast Radius Containment (BRC) and Secret PreToolUse guard.
#
# Supports Antigravity PreToolUse payloads (toolCall.name, toolCall.args)
# as well as tool_name / tool_input envelopes.
# Antigravity output contract: JSON on stdout {"decision": "allow"|"deny"|"force_ask", "reason": "..."} + exit 0.
# PowerShell 5.1 compatible. Strict 7-bit ASCII only. Parse-level fail-open, rule-level fail-closed.

$ErrorActionPreference = 'Stop'

$script:IsAntigravity = $false

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
    if ($norm -match '(^|\\)(hooks\.json|settings\.json|brc-guard\.ps1|telemetry-append\.ps1|\.pre-commit-config\.yaml|mcp_config\.json|plugin\.json)$') {
        return $true
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

if ([string]::IsNullOrWhiteSpace($cmd)) {
    Emit-Allow
}

# ---- Anti-Obfuscation Canonicalization ----
function Get-CanonicalCommand {
    param([string]$RawCmd)
    # Strip PowerShell backticks and cmd carets used for token splitting
    $deobf = $RawCmd -replace '`', '' -replace '\^', ''
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
        ($evalCmd -match '(^|\s)(cat|type|Get-Content|more|less|head|tail)\s+[^\r\n]*?(^|[/\\"\s])(\.env(?!\.(example|sample|template))|\.aws[/\\]credentials|\.kube[/\\]config|\.docker[/\\]config\.json|\.git-credentials|id_rsa|id_ed25519|id_ecdsa|id_dsa)(["\s]|$)')) {
        Emit-Deny 'secret-file-shell-read' $evalCmd
    }

    # Shell self-tampering writes/redirects targeting governance configs
    if ($evalCmd -match '(>|>>|\bOut-File\b|\bSet-Content\b|\bAdd-Content\b|\bCopy-Item\b|\bMove-Item\b|\bcp\b|\bmv\b|\btee\b)[^\r\n]*?(hooks\.json|brc-guard\.ps1|telemetry-append\.ps1|mcp_config\.json|plugin\.json)') {
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
