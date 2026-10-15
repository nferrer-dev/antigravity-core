---
name: restart-phone-ui
description: Restarts the Antigravity Phone UI sidecar server on port 3000 by terminating its owning listener process and letting the background watchdog respawn it. Use when the user asks to restart, reload, or reset the Phone UI server during development. Do not use for built-in Antigravity Remote Control tunnel commands or unrelated local dev servers.
---
# Restart Phone UI

When the user asks to restart, reload, or kill the Phone UI sidecar on port `3000` (governed by [mobile-ui.md](../../rules/mobile-ui.md)), execute the dedicated [restart_phone_ui.ps1](./scripts/restart_phone_ui.ps1) script via `run_command`:

```powershell
powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File .agents/skills/restart-phone-ui/scripts/restart_phone_ui.ps1
```

Or run the equivalent one-liner directly:

```powershell
Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | Where-Object { $_ -gt 4 } | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
```

After terminating the listener process on port `3000`, inform the user that the background watchdog or Antigravity `sidecar.json` supervisor (`"restart_policy": "always"`) will automatically respawn the server with the latest code within 15 seconds.

## Sidecar Supervisor & Auxiliary Pane Shortcut

If `antigravity-remote-control` is registered as an Antigravity sidecar (`~/.gemini/config/sidecars/antigravity-remote-control/sidecar.json`) with `"restart_policy": "always"`, `"has_web_ui": true`, and a `ui_config.views` entry using `"entrypoint": "SIDECAR_UI_ENTRYPOINT_AUX_PANE"`, surface the Auxiliary Pane shortcut pill:

- `[Phone UI](sidecar://antigravity-remote-control/)`

