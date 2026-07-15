Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd.exe /c cd /d C:\Projects\antigravity-core\.agents\sidecars\antigravity_phone_chat && ""C:\Program Files\nodejs\node.exe"" server.js > vbs.log 2>&1", 0, False
