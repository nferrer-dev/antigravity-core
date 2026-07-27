---
name: restart-phone-ui
description: Restarts the Phone UI server during development by terminating its port process and letting the watchdog respawn it.
---
# Restart Phone UI

When the user asks to restart, reload, or kill the Phone UI, you MUST execute the dedicated restart script.

Use the `run_command` tool to execute it:
`C:\Projects\antigravity-core\.agents\sidecars\antigravity-remote-control\restart_server.bat`

The script will automatically hunt down the active Node process on port 39201 and terminate it. 
After executing the script, inform the user that the background watchdog will automatically resurrect the server with the latest code within 15 seconds.
