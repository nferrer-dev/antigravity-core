import sys
from cortex.db import CortexDB, ProvenanceContext

def main():
    content = """Architecture Critique: WebSocket Reconnection & State Management

The current client architecture in `app_v8.js` exhibits a critical flaw when handling expired or invalid session cookies during a WebSocket connection attempt. Instead of gracefully redirecting the user to the login page, the client becomes trapped in an infinite, aggressive WebSocket reconnection loop.

When the client initializes a WebSocket connection (`new WebSocket(...)`), the browser performs an HTTP Upgrade request. If the authentication cookie is missing or invalid, the server will reject this handshake with an HTTP 401 Unauthorized or 403 Forbidden status. By design, the browser's native `WebSocket` API does not expose HTTP status codes from failed handshakes for security reasons.

Because the API suppresses the 401 status, the client only receives a generic `onclose` event. The `onclose` handler in `connectWebSocket` blindly assumes the disconnection was due to a transient network error or server restart, and attempts to reconnect every 2 seconds indefinitely (`setTimeout(connectWebSocket, 2000)`). The check for an 'Unauthorized' message inside `ws.onmessage` is effectively dead code for connection-level authentication failures because the connection is never established.

This results in a self-inflicted Denial of Service (spamming the server with unauthenticated upgrade requests) and a degraded user experience (stuck in 'Reconnecting' instead of routing to login)."""
    
    try:
        db = CortexDB()
        prov = ProvenanceContext(
            session_id="debate-auth-harden-002",
            agent_role="critic_agent"
        )
        res = db.store_memory(
            content=content,
            mem_type="fact",
            source="claude-code",
            provenance=prov
        )
        print("Success, stored memory ID:", res.id)
    except Exception as e:
        print("Error:", e)
        sys.exit(1)

if __name__ == "__main__":
    main()
