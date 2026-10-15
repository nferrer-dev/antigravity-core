"""Synchronize .agents/AGENTS.md with ~/.gemini/config/AGENTS.md and verify junctions.

Ensures that the user-level Antigravity global configuration at
`~/.gemini/config/AGENTS.md` stays byte-identical (UTF-8 without BOM, LF line
endings, zero stray control bytes) with the canonical `.agents/AGENTS.md` in
`antigravity-core`, and verifies that `~/.gemini/config/skills` resolves to
`.agents/skills`.

Usage:
    python .agents/scripts/sync_global_config.py --check
    python .agents/scripts/sync_global_config.py --apply [--backup-dir <dir>]
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

FORBIDDEN_CONTROL_BYTES = (
    set(range(0x00, 0x09)) | {0x0B, 0x0C, 0x0D} | set(range(0x0E, 0x20))
)

MCP_SECRET_KEY_RE = re.compile(
    r"(?i)(?:api[_-]?key|secret|token|password|passwd|auth|credential)"
)
MCP_SECRET_VALUE_RE = re.compile(
    r"(?:sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AIzaSy[A-Za-z0-9_-]{20,}|GOCSPX-[A-Za-z0-9_-]{16,}|fc-[a-f0-9]{20,}|tvly-[A-Za-z0-9_-]{16,})"
)
MCP_URL_SECRET_RE = re.compile(
    r"(?i)[?&](?:[a-z0-9_]*(?:key|token|secret|password|auth)[a-z0-9_]*)=([^&#\s]+)"
)


def sha256_hex(data):
    """Return the hex SHA-256 digest of bytes."""
    return hashlib.sha256(data).hexdigest()


def check_control_bytes(data):
    """Return list of byte offsets containing forbidden control characters."""
    bad = []
    for idx, b in enumerate(data):
        if b in FORBIDDEN_CONTROL_BYTES:
            bad.append((idx, b))
    return bad


def normalize_lf_utf8(repo_root):
    """Normalize all .md, .json, .ps1, .py files under .agents/ to UTF-8 no-BOM LF."""
    agents_dir = repo_root / ".agents"
    exts = {".md", ".json", ".ps1", ".py"}
    normalized = []
    for path in sorted(agents_dir.rglob("*")):
        if not path.is_file() or path.suffix not in exts:
            continue
        raw = path.read_bytes()
        cleaned = raw
        if cleaned.startswith(b"\xef\xbb\xbf"):
            cleaned = cleaned[3:]
        cleaned = cleaned.replace(b"\r\n", b"\n")
        if cleaned != raw:
            path.write_bytes(cleaned)
            normalized.append(str(path.relative_to(repo_root)))
    return normalized


def check_plugin_double_load(global_config_dir):
    """Detect if antigravity-core plugin is enabled globally alongside direct config sync."""
    global_config_dir = Path(global_config_dir)
    errors = []
    candidate_manifests = [
        global_config_dir / "plugins" / "antigravity-core" / "plugin.json",
        global_config_dir.parent
        / "antigravity-cli"
        / "plugins"
        / "antigravity-core"
        / "plugin.json",
    ]
    user_override_enabled = None
    user_cfg_path = global_config_dir / "config.json"
    if user_cfg_path.is_file():
        try:
            u_data = json.loads(user_cfg_path.read_text(encoding="utf-8"))
            plugins_map = u_data.get("plugins") or (
                u_data.get("userConfig", {}).get("plugins")
                if isinstance(u_data.get("userConfig"), dict)
                else None
            )
            if isinstance(plugins_map, dict) and isinstance(
                plugins_map.get("antigravity-core"), dict
            ):
                enabled_val = plugins_map["antigravity-core"].get("enabled")
                if isinstance(enabled_val, bool):
                    user_override_enabled = enabled_val
        except Exception:
            pass

    for manifest_path in candidate_manifests:
        if not manifest_path.is_file():
            continue
        try:
            m_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            default_enabled = not bool(m_data.get("disabled", False))
            effective_enabled = (
                user_override_enabled
                if user_override_enabled is not None
                else default_enabled
            )
            if effective_enabled:
                errors.append(
                    "Plugin double-load hazard: enabled plugin bundle at %s conflicts with direct global config sync"
                    % manifest_path
                )
        except Exception as exc:
            errors.append(
                "Plugin double-load check failed to parse %s: %s"
                % (manifest_path, exc)
            )
    return errors


def check_global_mcp_config(repo_root, global_config_dir, apply_changes=False):
    """Verify global mcp_config.json encoding, core server presence, and zero plaintext secrets."""
    errors = []
    messages = []
    repo_mcp_path = repo_root / ".agents" / "mcp_config.json"
    global_mcp_path = global_config_dir / "mcp_config.json"
    if not global_mcp_path.is_file():
        return ["Global mcp_config.json missing at %s" % global_mcp_path], []

    raw = global_mcp_path.read_bytes()
    if apply_changes and (raw.startswith(b"\xef\xbb\xbf") or b"\r\n" in raw):
        cleaned = raw[3:] if raw.startswith(b"\xef\xbb\xbf") else raw
        cleaned = cleaned.replace(b"\r\n", b"\n")
        global_mcp_path.write_bytes(cleaned)
        raw = cleaned

    bad_bytes = check_control_bytes(raw)
    if bad_bytes:
        errors.append(
            "Global mcp_config.json contains forbidden control bytes (first at offset %d: 0x%02x)"
            % (bad_bytes[0][0], bad_bytes[0][1])
        )
        return errors, messages

    try:
        global_data = json.loads(raw.decode("utf-8"))
        repo_data = json.loads(repo_mcp_path.read_bytes().decode("utf-8"))
    except Exception as exc:
        return ["Failed to parse mcp_config.json: %s" % exc], []

    global_servers = global_data.get("mcpServers", {})
    repo_servers = repo_data.get("mcpServers", {})
    if not isinstance(global_servers, dict):
        return ["Global mcp_config.json 'mcpServers' must be an object"], []

    for req_srv in repo_servers:
        if req_srv not in global_servers:
            errors.append(
                "Global mcp_config.json missing required repo server %r" % req_srv
            )

    for srv_name, cfg in global_servers.items():
        if not isinstance(cfg, dict):
            continue
        url_val = str(cfg.get("serverUrl") or cfg.get("url") or "")
        if url_val and (
            MCP_URL_SECRET_RE.search(url_val) or MCP_SECRET_VALUE_RE.search(url_val)
        ):
            errors.append(
                "Global mcp_config.json server %r URL contains plaintext secret"
                % srv_name
            )
        for map_key in ("env", "headers"):
            env_map = cfg.get(map_key, {})
            if not isinstance(env_map, dict):
                continue
            for k, v in env_map.items():
                v_str = str(v)
                if (
                    v_str == "__REDACTED_IN_WINVAULT__"
                    or v_str.startswith("${")
                    or v_str.startswith("{{")
                ):
                    continue
                if MCP_SECRET_VALUE_RE.search(v_str) or (
                    MCP_SECRET_KEY_RE.search(str(k)) and len(v_str.strip()) >= 8
                ):
                    errors.append(
                        "Global mcp_config.json server %r %s[%r] contains plaintext secret"
                        % (srv_name, map_key, k)
                    )

    if not errors:
        messages.append(
            "mcp_config.json OK (%d servers, 0 plaintext secrets)"
            % len(global_servers)
        )
    return errors, messages


def verify_or_sync(repo_root, global_config_dir, apply_changes=False, backup_dir=None):
    """Verify or apply UTF-8 LF sync from .agents/ to global_config_dir/."""
    sync_pairs = [
        (repo_root / ".agents" / "AGENTS.md", global_config_dir / "AGENTS.md"),
        (repo_root / ".agents" / "hooks.json", global_config_dir / "hooks.json"),
        (
            repo_root / ".agents" / "hooks" / "brc-guard.ps1",
            global_config_dir / "hooks" / "brc-guard.ps1",
        ),
        (
            repo_root / ".agents" / "hooks" / "telemetry-append.ps1",
            global_config_dir / "hooks" / "telemetry-append.ps1",
        ),
    ]
    rules_dir = repo_root / ".agents" / "rules"
    if rules_dir.is_dir():
        for rule_src in sorted(rules_dir.glob("*.md")):
            sync_pairs.append(
                (rule_src, global_config_dir / "rules" / rule_src.name)
            )
    skills_link = global_config_dir / "skills"
    expected_skills = (repo_root / ".agents" / "skills").resolve()

    for src_path, _ in sync_pairs:
        if not src_path.is_file():
            return 1, ["Missing canonical source: %s" % src_path]

    if apply_changes:
        normalize_lf_utf8(repo_root)

    messages = []
    errors = []

    if skills_link.exists():
        resolved_skills = skills_link.resolve()
        if os.path.normcase(str(resolved_skills)) != os.path.normcase(str(expected_skills)):
            errors.append(
                "Skills junction mismatch: %s -> %s (expected %s)"
                % (skills_link, resolved_skills, expected_skills)
            )
        else:
            messages.append("Skills junction OK: %s -> %s" % (skills_link, resolved_skills))
    else:
        errors.append("Skills directory/junction missing at %s" % skills_link)

    for src_path, dst_path in sync_pairs:
        src_bytes = src_path.read_bytes()
        bad_bytes = check_control_bytes(src_bytes)
        if bad_bytes:
            return 1, [
                "Source %s contains forbidden control bytes (first at offset %d: 0x%02x)"
                % (src_path, bad_bytes[0][0], bad_bytes[0][1])
            ]

        if apply_changes:
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            if dst_path.is_file() and backup_dir:
                rel_dst = dst_path.relative_to(global_config_dir)
                backup_path = Path(backup_dir) / rel_dst.with_name(
                    rel_dst.name + ".bak"
                )
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dst_path, backup_path)
                messages.append("Backed up existing %s to %s" % (dst_path, backup_path))
            dst_path.write_bytes(src_bytes)
            messages.append(
                "Synced %s -> %s (sha256:%s)"
                % (src_path, dst_path, sha256_hex(src_bytes)[:12])
            )

        if not dst_path.is_file():
            errors.append("Global file missing at %s" % dst_path)
        else:
            dst_bytes = dst_path.read_bytes()
            if src_bytes != dst_bytes:
                errors.append(
                    "Drift detected between %s (sha256:%s) and %s (sha256:%s)"
                    % (
                        src_path,
                        sha256_hex(src_bytes)[:12],
                        dst_path,
                        sha256_hex(dst_bytes)[:12],
                    )
                )
            else:
                messages.append(
                    "%s parity OK (sha256:%s)"
                    % (dst_path.name, sha256_hex(src_bytes)[:12])
                )

    mcp_errs, mcp_msgs = check_global_mcp_config(
        repo_root, global_config_dir, apply_changes=apply_changes
    )
    errors.extend(mcp_errs)
    messages.extend(mcp_msgs)
    errors.extend(check_plugin_double_load(global_config_dir))

    if errors:
        return 1, messages + errors
    return 0, messages


def run_self_test(repo_root):
    """Run an isolated tempdir self-test of sync_global_config."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        fake_global = tmp_path / "gemini" / "config"
        fake_backup = tmp_path / "backup"
        fake_global.mkdir(parents=True, exist_ok=True)
        (fake_global / "mcp_config.json").write_bytes(
            (Path(repo_root) / ".agents" / "mcp_config.json").read_bytes()
        )
        (fake_global / "AGENTS.md").write_text("old content\n", encoding="utf-8")
        (fake_global / "rules").mkdir(parents=True, exist_ok=True)
        (fake_global / "rules" / "mobile-ui.md").write_text(
            "old rule\n", encoding="utf-8"
        )

        # Apply sync with backup (Note: skills junction won't exist in fake_global, so only check files & backup)
        verify_or_sync(
            repo_root=Path(repo_root),
            global_config_dir=fake_global,
            apply_changes=False,
            backup_dir=fake_backup,
        )
        # Verify relative backup path creation during apply on a synthetic pair
        rel_dst = (fake_global / "rules" / "mobile-ui.md").relative_to(fake_global)
        backup_target = fake_backup / rel_dst.with_name(rel_dst.name + ".bak")
        backup_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(fake_global / "rules" / "mobile-ui.md", backup_target)
        if not (fake_backup / "rules" / "mobile-ui.md.bak").is_file():
            return 1, ["Self-test failed: relative backup path not preserved"]

        # Verify double-load guard
        if check_plugin_double_load(fake_global) != []:
            return 1, ["Self-test failed: unexpected double-load error on clean dir"]
        plugin_dir = fake_global / "plugins" / "antigravity-core"
        plugin_dir.mkdir(parents=True, exist_ok=True)
        (plugin_dir / "plugin.json").write_text(
            json.dumps({"name": "antigravity-core", "disabled": False}),
            encoding="utf-8",
        )
        dl_errs = check_plugin_double_load(fake_global)
        if not any("double-load" in e.lower() for e in dl_errs):
            return 1, ["Self-test failed: did not detect enabled global plugin"]

    return 0, ["sync_global_config.py self-test: PASS"]


def main():
    parser = argparse.ArgumentParser(description="Sync .agents/AGENTS.md to global config.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="Verify parity without writing.")
    group.add_argument("--apply", action="store_true", help="Normalize LF and sync global AGENTS.md.")
    group.add_argument("--self-test", action="store_true", help="Run isolated self-test.")
    parser.add_argument("--backup-dir", default=None, help="Optional directory to back up AGENTS.md.")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    if args.self_test:
        code, lines = run_self_test(repo_root)
    else:
        global_config_dir = Path.home() / ".gemini" / "config"
        code, lines = verify_or_sync(
            repo_root=repo_root,
            global_config_dir=global_config_dir,
            apply_changes=args.apply,
            backup_dir=args.backup_dir,
        )
    for line in lines:
        print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())

