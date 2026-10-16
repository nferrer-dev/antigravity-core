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

function Deny {
    param([string]$Rule, [string]$Cmd)
    $excerpt = $Cmd -replace '\s+', ' '
    if ($excerpt.Length -gt 160) { $excerpt = $excerpt.Substring(0, 160) + '...' }
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

# ---- Check file-access tools (Read, Edit, Write, MultiEdit) ----
$filePath = ''
foreach ($pf in @('file_path', 'path', 'notebook_path')) {
    if ($toolInput.PSObject.Properties[$pf] -and $null -ne $toolInput.$pf) {
        $filePath = [string]$toolInput.$pf
        break
    }
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
        if ($norm -match '(^|\\)(settings\.json|brc-guard\.ps1|telemetry-append\.ps1|\.pre-commit-config\.yaml|\.mcp\.json)$') {
            Deny 'harness-config-self-tampering' $filePath
        }
        if (($norm -notmatch '(?i)(^|\\)(scratch|tmp|temp)(\\|$)') -and
            ($norm -match '(?i)(^|\\)(dist|build)(\\|$)')) {
            Deny 'generated-output-write-guard' $filePath
        }
    }
}

$cmd = ''
if ($toolInput.PSObject.Properties['command'] -and $null -ne $toolInput.command) {
    $cmd = [string]$toolInput.command
}
if ([string]::IsNullOrWhiteSpace($cmd)) { exit 0 }

# ---- Anti-Obfuscation Canonicalization ----
function Get-CanonicalCommand {
    param([string]$RawCmd)
    return ($RawCmd -replace '`', '' -replace '\^', '')
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
    if ($evalCmd -match '(^|[\s;|&(])(Invoke-[E]xpression|iex|\[ScriptBlock\]::Create)\b') {
        Deny 'dynamic-code-evaluation' $evalCmd
    }

    if ($evalCmd -match '(sk-proj-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{50,}|AIzaSy[A-Za-z0-9_-]{33}|fc-[a-f0-9]{32}|tvly-[A-Za-z0-9_-]{20,}|GOCSPX-[A-Za-z0-9_-]{20,})') {
        Deny 'inline-secret-token' 'Inline API token detected in command'
    }

    if (($evalCmd -match 'antigravity[/\\]mcp_config\.json(?!\.deprecated-redacted)') -or
        ($evalCmd -match '(^|\s)(cat|type|Get-Content|more|less|head|tail)\s+[^\r\n]*?(^|[/\\"\s])(\.env(?!\.(example|sample|template))|\.aws[/\\]credentials|\.kube[/\\]config|\.docker[/\\]config\.json|\.git-credentials|id_rsa|id_ed25519|id_ecdsa|id_dsa)(["\s]|$)')) {
        Deny 'secret-file-shell-read' $evalCmd
    }

    if ($evalCmd -match '(>|>>|\bOut-File\b|\bSet-Content\b|\bAdd-Content\b|\bCopy-Item\b|\bMove-Item\b|\bcp\b|\bmv\b|\btee\b)[^\r\n]*?(settings\.json|brc-guard\.ps1|telemetry-append\.ps1|\.pre-commit-config\.yaml|\.mcp\.json)') {
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
