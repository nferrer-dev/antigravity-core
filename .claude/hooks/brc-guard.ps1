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

# ---- Check file-access tools (Read, Edit, Write, MultiEdit) ----
$filePath = ''
foreach ($pf in @('file_path', 'path', 'notebook_path')) {
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
    if ($toolName -match '^(Edit|Write|MultiEdit)$') {
        if (($norm -notmatch '(?i)(^|\\)(scratch|tmp|temp)(\\|$)') -and
            ($norm -match '(?i)(^|\\)(hooks\.json|settings\.json|brc-guard\.ps1|telemetry-append\.ps1|\.pre-commit-config\.yaml|mcp_config\.json|\.mcp\.json|plugin\.json|CLAUDE\.md|AGENTS\.md|agentic_telemetry\.md)$')) {
            Deny 'harness-config-self-tampering' $filePath
        }
        if (($norm -notmatch '(?i)(^|\\)(scratch|tmp|temp)(\\|$)') -and
            ($norm -match '(?i)(^|\\)(dist|build)(\\|$)')) {
            Deny 'generated-output-write-guard' $filePath
        }
        if (($filePath -match '(?i)\.md$') -and $payload.PSObject.Properties['artifactDirectoryPath'] -and $payload.artifactDirectoryPath) {
            $taintMdPath = Join-Path (Join-Path ([string]$payload.artifactDirectoryPath) 'scratch') '.untrusted_web_taint.json'
            if (Test-Path -LiteralPath $taintMdPath) {
                $mdBody = Get-WriteContentString $toolInput
                if ($mdBody -match '!\[[^\]]*\]\(\s*https?://') {
                    Deny 'untrusted-web-markdown-image-exfil' 'Writing external Markdown image URL while session is web-tainted'
                }
            }
        }
    }
}

if ($toolName -match '^mcp__cortex__(store_memory|upsert_entity|create_relation|store_procedure|import_memories)$') {
    $mcpPayloadStr = $toolInput | ConvertTo-Json -Depth 6 -Compress
    if (($mcpPayloadStr -match '(sk-proj-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{50,}|AIzaSy[A-Za-z0-9_-]{33}|fc-[a-f0-9]{32}|tvly-[A-Za-z0-9_-]{20,}|GOCSPX-[A-Za-z0-9_-]{20,})') -or
        ($mcpPayloadStr -match '(?i)(ignore\s+(all\s+)?(previous|prior)\s+instructions|disregard\s+(all\s+)?(previous|prior)\s+(instructions|rules)|<\s*system\s*>|\[VERDICT:\s*APPROVE\])')) {
        Deny 'cortex-memory-poisoning-guard' 'Blocked attempt to persist secret or prompt-injection directive into Cortex long-term memory'
    }
    if ($payload.PSObject.Properties['artifactDirectoryPath'] -and $payload.artifactDirectoryPath) {
        $taintCheckPath = Join-Path (Join-Path ([string]$payload.artifactDirectoryPath) 'scratch') '.untrusted_web_taint.json'
        if (Test-Path -LiteralPath $taintCheckPath) {
            Deny 'untrusted-web-memory-taint' 'Cortex write blocked while session is tainted by external web content'
        }
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
    if ($payload.PSObject.Properties['artifactDirectoryPath'] -and $payload.artifactDirectoryPath) {
        $taintCheckPath = Join-Path (Join-Path ([string]$payload.artifactDirectoryPath) 'scratch') '.untrusted_web_taint.json'
        if ((Test-Path -LiteralPath $taintCheckPath) -and
            ($evalCmd -match '(^|[\s;|&(])(curl(\.exe)?|wget(\.exe)?|Invoke-WebRequest|Invoke-RestMethod|iwr|irm|Start-BitsTransfer|scp(\.exe)?|ftp(\.exe)?)\b')) {
            Deny 'untrusted-web-egress-taint' $evalCmd
        }
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
        ($evalCmd -match '(>|>>|\bOut-File\b|\bSet-Content\b|\bAdd-Content\b|\bCopy-Item\b|\bMove-Item\b|\bRemove-Item\b|\bcp\b|\bmv\b|\brm\b|\bdel\b|\btee\b|WriteAllText|WriteAllLines|AppendAllText)[^\r\n]*?(hooks\.json|settings\.json|brc-guard\.ps1|telemetry-append\.ps1|\.pre-commit-config\.yaml|mcp_config\.json|\.mcp\.json|plugin\.json|AGENTS\.md|CLAUDE\.md|agentic_telemetry\.md)')) {
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
