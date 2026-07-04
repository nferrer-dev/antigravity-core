#!/bin/bash
# macOS/Linux: Configures the host's Tailscale daemon to route traffic to the chat sidecar
tailscale serve http://127.0.0.1:37189
echo "Tailscale reverse proxy configured successfully."
