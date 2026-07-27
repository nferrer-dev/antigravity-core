$process = Invoke-WmiMethod -Class Win32_Process -Name Create -ArgumentList "cmd.exe /c cd /d C:\Projects\antigravity-core\.agents\sidecars\antigravity_phone_chat && `"C:\Program Files\nodejs\node.exe`" server.js > wmi.log 2>&1"
$process
