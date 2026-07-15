Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd.exe /c node server.js", 0, False
