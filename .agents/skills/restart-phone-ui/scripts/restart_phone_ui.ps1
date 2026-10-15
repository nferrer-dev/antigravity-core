param(
    [switch]$DryRun
)
$ErrorActionPreference = 'Stop'
$pids = @(
    Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique |
        Where-Object { $_ -and $_ -gt 4 }
)
if ($DryRun) {
    Write-Output ("DRY_RUN port=3000 listener_pids=" + ($pids -join ','))
    exit 0
}
foreach ($targetPid in $pids) {
    Stop-Process -Id $targetPid -Force -ErrorAction SilentlyContinue
}
Write-Output ("TERMINATED port=3000 count=" + $pids.Count)
exit 0
