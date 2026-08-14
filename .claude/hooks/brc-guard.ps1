# brc-guard.ps1 - Blast Radius Containment (BRC) PreToolUse guard.
#
# Contract (Claude Code hooks): a JSON payload arrives on stdin with fields
# including tool_name and tool_input.command. Exit 0 allows the tool call.
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
    $payload = $raw | ConvertFrom-Json
} catch {
    exit 0
}

$cmd = ''
try {
    if ($payload -and $payload.tool_input -and $payload.tool_input.command) {
        $cmd = [string]$payload.tool_input.command
    }
} catch {
    $cmd = ''
}
if ([string]::IsNullOrWhiteSpace($cmd)) { exit 0 }

# Targets whose recursive deletion is routine and exempt (Low impact).
$exempt = '(?i)(tmp|temp|scratch|node_modules|worktree|\.cache|\bbuild\b|\bdist\b)'

# ---- Rule 1: recursive force delete outside temp/scratch ----
# Evaluated per pipeline segment so flags from unrelated commands cannot
# combine into a false positive (e.g. "rm -r x; tail -f log").
$segments = [regex]::Split($cmd, '&&|\|\||[;|&]')
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
if ($cmd -match 'git\s+push\b') {
    $forceFlag = ($cmd -match '(^|\s)--force(?!-with-lease)\b') -or ($cmd -match '(^|\s)-f(\s|$)')
    if ($forceFlag -and ($cmd -match '(^|[\s:/])(master|main)(\s|$|:)')) {
        Deny 'git-push-force-protected-branch' $cmd
    }
}

# ---- Rule 3: git reset --hard on master or main ----
if ($cmd -match 'git\s+reset\s+(--\S+\s+)*--hard\b') {
    if ($cmd -match '(^|[\s:/])(master|main)(\s|$|:)') {
        Deny 'git-reset-hard-protected-branch' $cmd
    }
}

# ---- Rule 4: SQL DROP TABLE / DROP DATABASE ----
# Skip read-only search/print commands that merely mention the string.
$searchOnly = $cmd -match '^\s*(grep|rg|git\s+grep|findstr|Select-String|echo|cat|type|Get-Content|less|head|tail)\b'
if (-not $searchOnly -and ($cmd -match '\bDROP\s+(TABLE|DATABASE)\b')) {
    Deny 'sql-drop' $cmd
}

# ---- Rule 5: filesystem creation (mkfs) ----
if ($cmd -match '(^|[\s;&|])mkfs(\.\S+)?\b') {
    Deny 'mkfs' $cmd
}

# ---- Rule 6: kill every process (kill -9 -1) ----
if ($cmd -match '(^|[\s;&|])kill\s+(-9|-KILL|-s\s+(9|KILL))\s+-1(\s|$)') {
    Deny 'kill-all-processes' $cmd
}

# ---- Rule 7: disk-wide format ----
if (($cmd -match '(^|[\s;&|])format(\.com)?\s+[a-zA-Z]:') -or ($cmd -match '\bFormat-Volume\b')) {
    Deny 'disk-format' $cmd
}

exit 0
