import sys
import time
import sqlite3
from cortex.db import CortexDB, ProvenanceContext

content = """
Empirical Review: Shard 1: Initialization & Secrets Validation

The proposal to exit immediately via `process.exit(1)` when default secrets (e.g., APP_PASSWORD='antigravity') are detected in `server.js` FAILS the empirical gate.

Reasoning:
1. `watchdog.cjs` supervises `server.js` and automatically restarts it when it exits with a non-zero code.
2. `run_watchdog_hidden.vbs` executes `watchdog.cjs` silently in the background.
3. If `server.js` exits via `process.exit(1)` due to a static configuration error, `watchdog.cjs` will continuously restart it every 15 seconds.
4. This creates an unrecoverable, silent restart loop that causes CPU/disk thrashing while providing no visible feedback to the user.

Recommendation:
- Use a distinct exit code (e.g., `process.exit(78)`) and update `watchdog.cjs` to not restart on configuration errors.
- Alternatively, enter a safe mode where the server runs but displays a configuration error interface, preventing execution of sensitive logic while remaining visible to the operator.
"""

def main():
    db = CortexDB()
    prov = ProvenanceContext(session_id="debate-auth-harden-002", agent_role="orchestrator", producer="debate-orchestrator")
    
    max_retries = 10
    for i in range(max_retries):
        try:
            mem = db.store_memory(
                content=content.strip(),
                mem_type="procedure",
                source="claude-desktop",
                importance=1.0,
                provenance=prov
            )
            print("Successfully stored memory:", mem.id)
            break
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) or "busy" in str(e).lower():
                print(f"SQLITE_BUSY encountered. Retrying {i+1}/{max_retries}...")
                time.sleep(1)
            else:
                raise
        except Exception as e:
            if "locked" in str(e).lower() or "busy" in str(e).lower():
                print(f"Database locked exception. Retrying {i+1}/{max_retries}...")
                time.sleep(1)
            else:
                raise

if __name__ == "__main__":
    main()
