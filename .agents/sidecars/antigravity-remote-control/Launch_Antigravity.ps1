param()

$SidecarDir = "$PSScriptRoot\.agents\sidecars\antigravity-remote-control"
$AppPath = "C:\Users\nferr\AppData\Local\Programs\Antigravity\Antigravity.exe"

Write-Host "Starting Antigravity Phone Connect Sidecar..."
# Start the sidecar in a new console window, keeping track of its PID
$sidecarProc = Start-Process "cmd.exe" -ArgumentList "/c start_ag_phone_connect.bat" -WorkingDirectory $SidecarDir -PassThru

Write-Host "Starting Antigravity..."
# Start Antigravity App
$appProc = Start-Process $AppPath -ArgumentList "--remote-debugging-port=9000" -PassThru

# Give it a moment to spawn its child processes
Start-Sleep -Seconds 2

Write-Host "Waiting for Antigravity to close..."
# Wait for the Antigravity App process to exit.
# NOTE: Electron single instance lock might cause the initial $appProc to exit immediately.
# So we poll Get-Process -Name Antigravity.
# We wait until there are NO Antigravity processes left.
while ((Get-Process -Name "Antigravity" -ErrorAction SilentlyContinue)) {
    Start-Sleep -Seconds 2
}

Write-Host "Antigravity closed. Terminating sidecar..."
# When Antigravity is fully closed, kill the sidecar process tree
taskkill.exe /PID $($sidecarProc.Id) /T /F | Out-Null

Write-Host "Cleanup complete."
