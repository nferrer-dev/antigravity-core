# Candidate Solutions: Sidecar Rename

## Candidate 1: The Radical Innovator
**Sidecar Virtualization Overlay & Semantic Graph Resolution**
1. **Decoupling Logic via Virtual File System (VFS) Junctions**: Instead of breaking 200+ files currently referencing the old path, immediately execute the physical rename to `antigravity-remote-control`, but dynamically generate a localized Windows Directory Junction (`mklink /J`) acting as a VFS pointer from `antigravity_phone_chat` to `antigravity-remote-control`.
2. **Graph-Theoretic Path Resolution**: Shift from physical path coupling to a central Registry Graph (`@sidecar/remote-control`).
3. **Semantic AST-Based Refactoring**: Bypass manual text manipulation. Deploy an AST-aware refactoring pass that traverses the execution paths mapped in the structural graph, mutating the nodes to depend on the abstract identifier.

## Candidate 2: The Security Paranoiac
**High Risk / Systemic Bottleneck Mitigation**
1. **The `venv` Absolute Path Trap (Denial of Execution)**: Python's `venv` module heavily hardcodes absolute execution paths in `pyvenv.cfg` and `Scripts/`. Moving the folder corrupts the virtual environment. The `venv` must be entirely nuked and rebuilt dynamically after the rename.
2. **Fork-Bombing Ghost Watchdogs**: The `watchdog.cjs` script manages `server.js` restarts and locks itself to `\\\\.\\pipe\\antigravity_watchdog_lock`. If renamed while running, it will fork-bomb or lock the pipe. Must explicitly `taskkill /F /IM node.exe` BEFORE the move.
3. **Hardcoded Launch Topologies**: Critical upstream callers explicitly hardcode the exact path (`Launch_Antigravity.ps1`, `restart-phone-ui` Skill, `AGENTS.md`). Failing to patch all upstream references will cause the main app to launch without the sidecar. Requires full regex search-and-replace.
4. **Orphaned TLS Certs & State Fragmentation**: Strict migration of all untracked `.env` and `.key` files must be enforced.

## Candidate 3: The Enterprise Minimalist
**Sidecar Rename via Self-Healing Paths & Junction**
1. **Core Rename & Backwards Compatibility (Junction)**: Execute the rename and immediately bridge the old path to the new path via `mklink /J`.
2. **Self-Healing Execution Path**: Replace hardcoded path in `Launch_Antigravity.ps1` with `$PSScriptRoot`.
3. **Update Global Repository References**: Update static pointers in `restart-phone-ui/SKILL.md` and `AGENTS.md`. Claims internal launcher dependencies (`venv`) are strictly relative and will not be disrupted.
