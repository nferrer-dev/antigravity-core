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
import tomllib
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
MCP_SCHEMA_INJECTION_RE = re.compile(
    r"\b(?:ignore|disregard)\s+(?:all\s+|any\s+)?(?:previous|prior|above|system)\s+"
    r"(?:instructions|prompts|rules|directives)\b",
    re.IGNORECASE,
)

CLAUDE_MD_NAME = "CLAUDE" + ".md"
CLAUDE_DIR_NAME = "." + "claude"
CLAUDE_JSON_NAME = "." + "claude.json"
CLAUDE_HOOKS_VAR = "$CLAUDE_PROJECT_DIR/" + CLAUDE_DIR_NAME + "/hooks"
CODEX_MD_NAME = "CODEX" + ".md"
CODEX_DIR_NAME = "." + "codex"
CODEX_HOOKS_REL = "./" + CODEX_DIR_NAME + "/hooks"
HERMES_DIR_NAME = "." + "hermes"
_TEXT_EXTS = {".md", ".json", ".toml", ".rules", ".yaml", ".ps1", ".py", ".js"}


def sha256_hex(data):
    """Return the hex SHA-256 digest of bytes."""
    return hashlib.sha256(data).hexdigest()


def check_control_bytes(data):
    """Return list of byte offsets containing forbidden control characters."""
    return [(idx, b) for idx, b in enumerate(data) if b in FORBIDDEN_CONTROL_BYTES]


def _collect_normalizable_files(repo_root):
    """Return all text files under .agents/, Claude, and Codex trees."""
    targets = [repo_root / CLAUDE_MD_NAME, repo_root / CODEX_MD_NAME]
    for sub_name in (".agents", CLAUDE_DIR_NAME, CODEX_DIR_NAME):
        sub_dir = repo_root / sub_name
        if sub_dir.is_dir():
            targets.extend(sorted(sub_dir.rglob("*")))
    return [
        p
        for p in targets
        if "node_modules" not in p.parts and p.is_file() and p.suffix in _TEXT_EXTS
    ]


def normalize_lf_utf8(repo_root):
    """Normalize all text files under .agents/, Claude, and Codex trees to UTF-8 no-BOM LF."""
    normalized = []
    for path in _collect_normalizable_files(repo_root):
        raw = path.read_bytes()
        cleaned = raw[3:] if raw.startswith(b"\xef\xbb\xbf") else raw
        cleaned = cleaned.replace(b"\r\n", b"\n")
        if cleaned != raw:
            path.write_bytes(cleaned)
            normalized.append(str(path.relative_to(repo_root)))
    return normalized


def _extract_plugins_map(u_data):
    """Extract the plugins mapping from a parsed user config.json object."""
    if not isinstance(u_data, dict):
        return None
    if isinstance(u_data.get("plugins"), dict):
        return u_data["plugins"]
    user_cfg = u_data.get("userConfig")
    if isinstance(user_cfg, dict) and isinstance(user_cfg.get("plugins"), dict):
        return user_cfg["plugins"]
    return None


def _read_user_plugin_override(user_cfg_path):
    """Return the boolean enabled override for antigravity-core in config.json, or None."""
    if not user_cfg_path.is_file():
        return None
    try:
        u_data = json.loads(user_cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    plugins_map = _extract_plugins_map(u_data)
    core_cfg = plugins_map.get("antigravity-core") if plugins_map else None
    if isinstance(core_cfg, dict) and isinstance(core_cfg.get("enabled"), bool):
        return core_cfg["enabled"]
    return None


def _check_single_plugin_manifest(manifest_path, user_override_enabled):
    """Check one candidate plugin.json for double-load conflict."""
    if not manifest_path.is_file():
        return []
    try:
        m_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return ["Plugin double-load check failed to parse %s: %s" % (manifest_path, exc)]
    default_enabled = not bool(m_data.get("disabled", False))
    effective_enabled = (
        user_override_enabled if user_override_enabled is not None else default_enabled
    )
    if effective_enabled:
        return [
            "Plugin double-load hazard: enabled plugin bundle at %s conflicts with direct global config sync"
            % manifest_path
        ]
    return []


def check_plugin_double_load(global_config_dir):
    """Detect if antigravity-core plugin is enabled globally alongside direct config sync."""
    global_config_dir = Path(global_config_dir)
    candidate_manifests = (
        global_config_dir / "plugins" / "antigravity-core" / "plugin.json",
        global_config_dir.parent
        / "antigravity-cli"
        / "plugins"
        / "antigravity-core"
        / "plugin.json",
    )
    override = _read_user_plugin_override(global_config_dir / "config.json")
    errors = []
    for manifest_path in candidate_manifests:
        errors.extend(_check_single_plugin_manifest(manifest_path, override))
    return errors


def _is_safe_secret_placeholder(v_str):
    """Return True if a config value string is a vault placeholder or template reference."""
    return (
        v_str == "__REDACTED_IN_WINVAULT__"
        or v_str.startswith("${")
        or v_str.startswith("{{")
    )


def _is_plaintext_secret_kv(key_name, val_obj):
    """Return True if (key_name, val_obj) is an unredacted plaintext secret entry."""
    v_str = str(val_obj)
    if _is_safe_secret_placeholder(v_str):
        return False
    if MCP_SECRET_VALUE_RE.search(v_str):
        return True
    return bool(MCP_SECRET_KEY_RE.search(str(key_name)) and len(v_str.strip()) >= 8)


def _scan_server_env_maps(file_label, srv_name, cfg, map_keys):
    """Scan env/header dictionaries on a single MCP server config for plaintext secrets."""
    errors = []
    for map_key in map_keys:
        env_map = cfg.get(map_key, {})
        if not isinstance(env_map, dict):
            continue
        for k, v in env_map.items():
            if _is_plaintext_secret_kv(k, v):
                errors.append(
                    "Global %s server %r %s[%r] contains plaintext secret"
                    % (file_label, srv_name, map_key, k)
                )
    return errors


def _scan_single_mcp_server_secrets(file_label, srv_name, cfg, map_keys=("env", "headers")):
    """Scan URL and env/headers of one MCP server entry for plaintext secrets."""
    if not isinstance(cfg, dict):
        return []
    errors = []
    url_val = str(cfg.get("serverUrl") or cfg.get("url") or "")
    if url_val and (
        MCP_URL_SECRET_RE.search(url_val) or MCP_SECRET_VALUE_RE.search(url_val)
    ):
        errors.append(
            "Global %s server %r URL contains plaintext secret" % (file_label, srv_name)
        )
    errors.extend(_scan_server_env_maps(file_label, srv_name, cfg, map_keys))
    return errors


def _scan_mcp_schemas_for_injection(global_config_dir):
    """Scan lazy MCP tool schema JSON files for prompt-injection directives."""
    mcp_schemas_root = global_config_dir.parent / "antigravity" / "mcp"
    if not mcp_schemas_root.is_dir():
        return []
    errors = []
    for schema_file in sorted(mcp_schemas_root.glob("*/*.json")):
        if not schema_file.is_file():
            continue
        s_text = schema_file.read_bytes().decode("utf-8", errors="replace")
        if MCP_SCHEMA_INJECTION_RE.search(s_text):
            errors.append(
                "Lazy MCP schema %s contains prompt-injection override directive (tool-poisoning guard)"
                % schema_file
            )
    return errors


def _read_and_optionally_clean_bytes(path, apply_changes):
    """Read bytes from path, stripping UTF-8 BOM and CRLF in-place when apply_changes is True."""
    raw = path.read_bytes()
    if apply_changes and (raw.startswith(b"\xef\xbb\xbf") or b"\r\n" in raw):
        cleaned = raw[3:] if raw.startswith(b"\xef\xbb\xbf") else raw
        cleaned = cleaned.replace(b"\r\n", b"\n")
        path.write_bytes(cleaned)
        return cleaned
    return raw


def check_global_mcp_config(repo_root, global_config_dir, apply_changes=False):
    """Verify global mcp_config.json encoding, core server presence, and zero plaintext secrets."""
    repo_mcp_path = repo_root / ".agents" / "mcp_config.json"
    global_mcp_path = Path(global_config_dir) / "mcp_config.json"
    if not global_mcp_path.is_file():
        return ["Global mcp_config.json missing at %s" % global_mcp_path], []

    raw = _read_and_optionally_clean_bytes(global_mcp_path, apply_changes)
    bad_bytes = check_control_bytes(raw)
    if bad_bytes:
        return [
            "Global mcp_config.json contains forbidden control bytes (first at offset %d: 0x%02x)"
            % (bad_bytes[0][0], bad_bytes[0][1])
        ], []

    try:
        global_data = json.loads(raw.decode("utf-8"))
        repo_data = json.loads(repo_mcp_path.read_bytes().decode("utf-8"))
    except Exception as exc:
        return ["Failed to parse mcp_config.json: %s" % exc], []

    global_servers = global_data.get("mcpServers", {})
    if not isinstance(global_servers, dict):
        return ["Global mcp_config.json 'mcpServers' must be an object"], []

    errors = [
        "Global mcp_config.json missing required repo server %r" % req_srv
        for req_srv in repo_data.get("mcpServers", {})
        if req_srv not in global_servers
    ]
    for srv_name, cfg in global_servers.items():
        errors.extend(_scan_single_mcp_server_secrets("mcp_config.json", srv_name, cfg))
    errors.extend(_scan_mcp_schemas_for_injection(Path(global_config_dir)))

    if errors:
        return errors, []
    return [], [
        "mcp_config.json OK (%d servers, 0 plaintext secrets)" % len(global_servers)
    ]


def _create_directory_junction(src_dir, dst_dir):
    """Create an NTFS directory junction on Windows or symlink fallback."""
    try:
        import _winapi

        _winapi.CreateJunction(str(src_dir), str(dst_dir))
    except Exception:
        os.symlink(str(src_dir), str(dst_dir), target_is_directory=True)


def _extract_core_mcp_from_file(mcp_src, desired_servers):
    """Merge core MCP server definitions (cortex, code-graph-context, rea) from mcp_src."""
    if not mcp_src.is_file():
        return
    try:
        m_data = json.loads(mcp_src.read_bytes().decode("utf-8"))
    except Exception:
        return
    for s_name, s_cfg in (m_data.get("mcpServers") or {}).items():
        if s_name in ("cortex", "code-graph-context", "rea") and isinstance(s_cfg, dict):
            entry = dict(s_cfg)
            if "command" in entry and "type" not in entry:
                entry = {"type": "stdio", **entry}
            desired_servers[s_name] = entry


def _collect_desired_claude_mcp_servers(repo_root, global_config_dir):
    """Collect desired core MCP servers from repo and global MCP configs."""
    desired = {}
    for mcp_src in (
        repo_root / ".agents" / "mcp_config.json",
        repo_root / ".mcp.json",
        Path(global_config_dir) / "mcp_config.json",
    ):
        _extract_core_mcp_from_file(mcp_src, desired)
    return desired


def _load_or_init_claude_json(claude_json_path, apply_changes):
    """Load or initialize global Claude JSON config; return (data_dict, error_list)."""
    if not claude_json_path.is_file():
        if not apply_changes:
            return None, ["Global Claude JSON missing at %s" % claude_json_path]
        return {"mcpServers": {}}, []
    try:
        claude_data = json.loads(claude_json_path.read_bytes().decode("utf-8"))
    except Exception as exc:
        return None, ["Failed to parse %s: %s" % (claude_json_path, exc)]
    if not isinstance(claude_data.get("mcpServers"), dict):
        if not apply_changes:
            return None, ["%s 'mcpServers' must be an object" % claude_json_path]
        claude_data["mcpServers"] = {}
    return claude_data, []


def _upsert_claude_mcp_entries(mcp_servers, desired_servers, claude_json_path, apply_changes):
    """Ensure desired_servers exist in mcp_servers; return (modified, errors, messages)."""
    modified = False
    errors = []
    messages = []
    for srv_name, desired_cfg in desired_servers.items():
        if srv_name in mcp_servers:
            continue
        if apply_changes:
            mcp_servers[srv_name] = desired_cfg
            modified = True
            messages.append("Added core MCP server %r to %s" % (srv_name, claude_json_path))
        else:
            errors.append(
                "Global %s missing required core MCP server %r"
                % (claude_json_path.name, srv_name)
            )
    return modified, errors, messages


def _write_json_with_optional_backup(target_path, data, backup_path):
    """Write data as UTF-8 LF JSON to target_path after optional backup."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if target_path.is_file() and backup_path is not None:
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target_path, backup_path)
    target_path.write_bytes((json.dumps(data, indent=2) + "\n").encode("utf-8"))


def check_or_sync_claude_mcp(
    repo_root,
    global_config_dir,
    claude_json_path,
    apply_changes=False,
    backup_dir=None,
):
    """Ensure core harness MCP servers exist in global Claude JSON config non-destructively."""
    claude_json_path = Path(claude_json_path)
    desired_servers = _collect_desired_claude_mcp_servers(repo_root, global_config_dir)
    claude_data, init_errs = _load_or_init_claude_json(claude_json_path, apply_changes)
    if init_errs:
        return init_errs, []

    mcp_servers = claude_data["mcpServers"]
    modified, errors, messages = _upsert_claude_mcp_entries(
        mcp_servers, desired_servers, claude_json_path, apply_changes
    )
    if apply_changes and modified:
        b_path = (
            Path(backup_dir) / "claude" / (claude_json_path.name + ".bak")
            if backup_dir
            else None
        )
        _write_json_with_optional_backup(claude_json_path, claude_data, b_path)

    for srv_name in desired_servers:
        errors.extend(
            _scan_single_mcp_server_secrets(
                claude_json_path.name, srv_name, mcp_servers.get(srv_name)
            )
        )
    if not errors:
        messages.append(
            "Global %s core MCP servers OK (%d managed servers verified)"
            % (claude_json_path.name, len(desired_servers))
        )
    return errors, messages


def _compute_backup_target(dst_path, target_root, backup_dir, backup_subdir):
    """Compute the destination backup path for dst_path, or None if backup_dir is unset."""
    if not backup_dir:
        return None
    rel_dst = dst_path.relative_to(target_root)
    base = Path(backup_dir) / backup_subdir if backup_subdir else Path(backup_dir)
    return base / rel_dst.with_name(rel_dst.name + ".bak")


def _apply_single_file_sync(src_path, dst_path, src_bytes, target_root, backup_dir, backup_subdir):
    """Write src_bytes to dst_path if needed, backing up any existing file."""
    messages = []
    if dst_path.is_file() and dst_path.read_bytes() == src_bytes:
        return messages
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    b_path = _compute_backup_target(dst_path, target_root, backup_dir, backup_subdir)
    if dst_path.is_file() and b_path is not None:
        b_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dst_path, b_path)
        messages.append("Backed up existing %s to %s" % (dst_path, b_path))
    dst_path.write_bytes(src_bytes)
    messages.append(
        "Synced %s -> %s (sha256:%s)"
        % (src_path, dst_path, sha256_hex(src_bytes)[:12])
    )
    return messages


def _verify_or_sync_single_pair(
    src_path, dst_path, target_root, label, apply_changes, backup_dir, backup_subdir
):
    """Verify or sync a single (src_path, dst_path) file pair."""
    if not src_path.is_file():
        return ["Missing canonical %s source: %s" % (label, src_path)], []
    src_bytes = src_path.read_bytes()
    bad_bytes = check_control_bytes(src_bytes)
    if bad_bytes:
        return [
            "Source %s contains forbidden control bytes (first at offset %d: 0x%02x)"
            % (src_path, bad_bytes[0][0], bad_bytes[0][1])
        ], []

    messages = []
    if apply_changes:
        messages.extend(
            _apply_single_file_sync(
                src_path, dst_path, src_bytes, target_root, backup_dir, backup_subdir
            )
        )
    if not dst_path.is_file():
        return ["Global %s file missing at %s" % (label, dst_path)], messages
    dst_bytes = dst_path.read_bytes()
    if src_bytes != dst_bytes:
        return [
            "Drift detected between %s (sha256:%s) and %s (sha256:%s)"
            % (
                src_path,
                sha256_hex(src_bytes)[:12],
                dst_path,
                sha256_hex(dst_bytes)[:12],
            )
        ], messages
    messages.append(
        "%s %s parity OK (sha256:%s)" % (label, dst_path.name, sha256_hex(src_bytes)[:12])
    )
    return [], messages


def _sync_file_pairs(pairs, target_root, label, apply_changes, backup_dir, backup_subdir):
    """Verify or sync a sequence of (src_path, dst_path) pairs."""
    errors = []
    messages = []
    for src_path, dst_path in pairs:
        p_errs, p_msgs = _verify_or_sync_single_pair(
            src_path, dst_path, target_root, label, apply_changes, backup_dir, backup_subdir
        )
        errors.extend(p_errs)
        messages.extend(p_msgs)
    return errors, messages


def _is_matching_junction(sk_dst, exp_resolved):
    """Return True if sk_dst exists and resolves to exp_resolved."""
    return (
        os.path.lexists(sk_dst)
        and sk_dst.exists()
        and os.path.normcase(str(sk_dst.resolve()))
        == os.path.normcase(str(exp_resolved))
    )


def _repair_or_create_skill_junction(sk_dst, exp_resolved, label):
    """Create or replace a skill directory junction at sk_dst; return error list."""
    sk_dst.parent.mkdir(parents=True, exist_ok=True)
    if not os.path.lexists(sk_dst):
        _create_directory_junction(exp_resolved, sk_dst)
        return []
    is_reparse = not sk_dst.exists() or (
        os.path.normcase(str(sk_dst.resolve()))
        != os.path.normcase(str(os.path.abspath(sk_dst)))
    )
    if is_reparse:
        os.rmdir(sk_dst)
        _create_directory_junction(exp_resolved, sk_dst)
        return []
    return [
        "%s skill path %s is a non-junction directory; refusing to overwrite"
        % (label, sk_dst)
    ]


def _sync_single_skill_junction(sk_src, target_root, label, apply_changes):
    """Verify or create a single per-skill NTFS directory junction."""
    sk_dst = target_root / "skills" / sk_src.name
    exp = sk_src.resolve()
    errors = []
    messages = []
    if not _is_matching_junction(sk_dst, exp) and apply_changes:
        errors.extend(_repair_or_create_skill_junction(sk_dst, exp, label))
    if not sk_dst.exists():
        errors.append("%s skill junction missing at %s" % (label, sk_dst))
        return errors, messages
    resolved_sk = sk_dst.resolve()
    if os.path.normcase(str(resolved_sk)) != os.path.normcase(str(exp)):
        errors.append(
            "%s skill junction mismatch: %s -> %s (expected %s)"
            % (label, sk_dst, resolved_sk, exp)
        )
    else:
        messages.append("%s skill junction OK: %s -> %s" % (label, sk_dst, resolved_sk))
    return errors, messages


def _sync_skill_junctions(skills_src_root, target_root, label, apply_changes):
    """Verify or create per-skill NTFS directory junctions under target_root/skills."""
    if not skills_src_root.is_dir():
        return [], []
    errors = []
    messages = []
    for sk_src in sorted(skills_src_root.iterdir()):
        if sk_src.is_dir():
            s_errs, s_msgs = _sync_single_skill_junction(
                sk_src, target_root, label, apply_changes
            )
            errors.extend(s_errs)
            messages.extend(s_msgs)
    return errors, messages


def _item_commands_string(item):
    """Return concatenated hook command strings inside a hook entry dict."""
    if not isinstance(item, dict):
        return ""
    return " ".join(
        h.get("command", "")
        for h in (item.get("hooks") or [])
        if isinstance(h, dict)
    )


def _replace_or_append_hook_entry(cur_list, req_entry, script_base):
    """Replace existing hook entry matching script_base or append req_entry."""
    replaced = False
    new_list = []
    for item in cur_list:
        if script_base in _item_commands_string(item):
            if not replaced:
                new_list.append(req_entry)
                replaced = True
        else:
            new_list.append(item)
    if not replaced:
        new_list.append(req_entry)
    return new_list


def _load_hooks_container_json(json_path, apply_changes):
    """Load settings.json or hooks.json and return (data_dict_or_none, errors)."""
    if not json_path.is_file():
        return {}, []
    errors = []
    raw = json_path.read_bytes()
    if check_control_bytes(raw) and not apply_changes:
        errors.append("Global %s contains forbidden control bytes" % json_path)
    try:
        data = json.loads(raw.replace(b"\r\n", b"\n").decode("utf-8-sig"))
    except Exception as exc:
        errors.append("Failed to parse %s: %s" % (json_path, exc))
        return None, errors
    return data if isinstance(data, dict) else None, errors


def _reconcile_required_hooks(data, required_hooks, json_path, apply_changes):
    """Reconcile required_hooks into data['hooks']; return (modified, errors)."""
    hooks_map = data.get("hooks")
    if not isinstance(hooks_map, dict):
        hooks_map = {}
    modified = False
    errors = []
    for event_name, req_entries in required_hooks.items():
        cur_list = list(hooks_map.get(event_name) or [])
        for req_entry in req_entries:
            req_cmd = req_entry["hooks"][0]["command"]
            script_base = (
                "brc-guard.ps1" if "brc-guard.ps1" in req_cmd else "telemetry-append.ps1"
            )
            if req_entry in cur_list:
                continue
            if apply_changes:
                cur_list = _replace_or_append_hook_entry(cur_list, req_entry, script_base)
                hooks_map[event_name] = cur_list
                data["hooks"] = hooks_map
                modified = True
            else:
                errors.append(
                    "Global %s missing or drifted hook %s (%s)"
                    % (json_path, event_name, script_base)
                )
    return modified, errors


def _sync_hooks_container_file(
    json_path, required_hooks, label, backup_subdir, apply_changes, backup_dir
):
    """Non-destructively upsert required_hooks into settings.json or hooks.json."""
    data, errors = _load_hooks_container_json(json_path, apply_changes)
    messages = []
    if data is None:
        return errors, messages
    modified, h_errs = _reconcile_required_hooks(
        data, required_hooks, json_path, apply_changes
    )
    errors.extend(h_errs)
    if apply_changes and (modified or not json_path.is_file()):
        b_path = (
            Path(backup_dir) / backup_subdir / (json_path.name + ".bak")
            if backup_dir
            else None
        )
        _write_json_with_optional_backup(json_path, data, b_path)
        messages.append("Updated global %s hooks in %s" % (label, json_path))
    if not errors:
        messages.append("Global %s %s OK" % (label, json_path.name))
    return errors, messages


def _build_claude_pairs(repo_root, c_src, claude_dir):
    """Build list of (src_path, dst_path) pairs for global Claude Code sync."""
    pairs = [(repo_root / CLAUDE_MD_NAME, claude_dir / CLAUDE_MD_NAME)]
    for sub, pat in (("rules", "*.md"), ("hooks", "*.ps1"), ("agents", "*.md")):
        sub_dir = c_src / sub
        if sub_dir.is_dir():
            for src_f in sorted(sub_dir.glob(pat)):
                pairs.append((src_f, claude_dir / sub / src_f.name))
    return pairs


def verify_or_sync_claude(
    repo_root,
    global_config_dir,
    claude_dir,
    claude_json=None,
    apply_changes=False,
    backup_dir=None,
):
    """Verify or apply non-destructive global Claude Code sync to claude_dir and claude_json."""
    repo_root = Path(repo_root)
    claude_dir = Path(claude_dir)
    c_src = repo_root / CLAUDE_DIR_NAME

    claude_pairs = _build_claude_pairs(repo_root, c_src, claude_dir)
    errors, messages = _sync_file_pairs(
        claude_pairs, claude_dir, "Claude", apply_changes, backup_dir, "claude"
    )
    sk_errs, sk_msgs = _sync_skill_junctions(
        c_src / "skills", claude_dir, "Claude", apply_changes
    )
    errors.extend(sk_errs)
    messages.extend(sk_msgs)

    hooks_dir_posix = (claude_dir / "hooks").as_posix()
    canon_settings_raw = (
        (c_src / "settings.json")
        .read_text(encoding="utf-8")
        .replace(CLAUDE_HOOKS_VAR, hooks_dir_posix)
    )
    required_hooks = json.loads(canon_settings_raw).get("hooks", {})
    h_errs, h_msgs = _sync_hooks_container_file(
        claude_dir / "settings.json",
        required_hooks,
        "Claude",
        "claude",
        apply_changes,
        backup_dir,
    )
    errors.extend(h_errs)
    messages.extend(h_msgs)

    if claude_json is not None:
        c_mcp_errs, c_mcp_msgs = check_or_sync_claude_mcp(
            repo_root,
            global_config_dir,
            claude_json,
            apply_changes=apply_changes,
            backup_dir=backup_dir,
        )
        errors.extend(c_mcp_errs)
        messages.extend(c_mcp_msgs)

    return errors, messages


def _rebuild_codex_top_header(top_part):
    """Rebuild the root-level TOML key block before the first [section] header."""
    new_top_lines = []
    found_fallback = False
    found_max_bytes = False
    for line in top_part.splitlines():
        stripped = line.strip()
        if re.match(r"^project_doc_fallback_filenames\s*=", stripped):
            new_top_lines.append('project_doc_fallback_filenames = ["CODEX.md"]')
            found_fallback = True
        elif re.match(r"^project_doc_max_bytes\s*=", stripped):
            new_top_lines.append("project_doc_max_bytes = 65536")
            found_max_bytes = True
        else:
            new_top_lines.append(line)

    insert_header = []
    if not found_fallback:
        insert_header.append('project_doc_fallback_filenames = ["CODEX.md"]')
    if not found_max_bytes:
        insert_header.append("project_doc_max_bytes = 65536")
    if insert_header:
        while new_top_lines and new_top_lines[-1].strip() == "":
            new_top_lines.pop()
        new_top_lines.extend(insert_header)
    return "\n".join(new_top_lines).rstrip() + "\n\n"


def _upsert_codex_features_section(rest_part):
    """Ensure [features] section in rest_part sets codex_hooks = true."""
    feat_hdr = re.search(r"(?m)^\[features\][ \t]*$", rest_part)
    if not feat_hdr:
        trimmed = rest_part.rstrip()
        prefix = trimmed + "\n\n" if trimmed else ""
        return prefix + "[features]\ncodex_hooks = true\n"

    after_feat = rest_part[feat_hdr.end() :]
    next_sec = re.search(r"(?m)^\[", after_feat)
    feat_body = after_feat[: next_sec.start()] if next_sec else after_feat
    feat_tail = after_feat[next_sec.start() :] if next_sec else ""
    if re.search(r"(?m)^[ \t]*codex_hooks[ \t]*=", feat_body):
        feat_body = re.sub(
            r"(?m)^[ \t]*codex_hooks[ \t]*=.*$", "codex_hooks = true", feat_body
        )
    else:
        sep = "" if feat_body.startswith("\n") else "\n"
        feat_body = "\ncodex_hooks = true" + sep + feat_body
    return rest_part[: feat_hdr.end()] + feat_body + feat_tail


def _upsert_codex_mcp_sections(rest_part, include_cortex):
    """Append [mcp_servers.code-graph-context] and optional [mcp_servers.cortex] if absent."""
    if not re.search(r"(?m)^\[mcp_servers\.code-graph-context\][ \t]*$", rest_part):
        rest_part = (
            rest_part.rstrip()
            + "\n\n[mcp_servers.code-graph-context]\n"
            + 'command = "cgc"\n'
            + 'args = ["mcp", "start"]\n'
            + "startup_timeout_sec = 20\n"
        )
    if include_cortex and not re.search(
        r"(?m)^\[mcp_servers\.cortex\][ \t]*$", rest_part
    ):
        rest_part = (
            rest_part.rstrip()
            + "\n\n[mcp_servers.cortex]\n"
            + 'url = "http://127.0.0.1:8585/mcp"\n'
        )
    return rest_part


def _merge_codex_config_toml(existing_text, include_cortex=False):
    """Non-destructively merge Antigravity Codex keys into config.toml with root keys before [section]."""
    text = (existing_text or "").replace("\r\n", "\n").replace("\r", "\n")
    if text.startswith("\ufeff"):
        text = text[1:]

    sec_match = re.search(r"(?m)^\[", text)
    top_part = text[: sec_match.start()] if sec_match else text
    rest_part = text[sec_match.start() :] if sec_match else ""

    top_rebuilt = _rebuild_codex_top_header(top_part)
    rest_part = _upsert_codex_features_section(rest_part)
    rest_part = _upsert_codex_mcp_sections(rest_part, include_cortex)
    return top_rebuilt + rest_part.lstrip("\n").rstrip() + "\n"


def _build_codex_pairs(repo_root, x_src, codex_dir):
    """Build list of (src_path, dst_path) pairs for global OpenAI Codex sync."""
    pairs = [
        (repo_root / CODEX_MD_NAME, codex_dir / "AGENTS.md"),
        (
            x_src / "rules" / "antigravity.rules",
            codex_dir / "rules" / "antigravity.rules",
        ),
    ]
    for sub, pat in (("rules", "*.md"), ("hooks", "*.ps1"), ("agents", "*.toml")):
        sub_dir = x_src / sub
        if sub_dir.is_dir():
            for src_f in sorted(sub_dir.glob(pat)):
                pairs.append((src_f, codex_dir / sub / src_f.name))
    return pairs


def _should_include_cortex_for_codex(global_config_dir, existing_cfg_text):
    """Return True if cortex is configured in global mcp_config.json or existing config.toml."""
    if re.search(r"(?m)^\[mcp_servers\.cortex\][ \t]*$", existing_cfg_text):
        return True
    global_mcp_path = Path(global_config_dir) / "mcp_config.json"
    if not global_mcp_path.is_file():
        return False
    try:
        m_data = json.loads(
            global_mcp_path.read_bytes().replace(b"\r\n", b"\n").decode("utf-8-sig")
        )
        return "cortex" in (m_data.get("mcpServers") or {})
    except Exception:
        return False


def _check_codex_toml_root_and_features(cfg_path, parsed_toml):
    """Validate root keys and [features].codex_hooks in parsed Codex config.toml."""
    errors = []
    if parsed_toml.get("project_doc_fallback_filenames") != ["CODEX.md"]:
        errors.append(
            "Global %s root project_doc_fallback_filenames must be ['CODEX.md']" % cfg_path
        )
    if parsed_toml.get("project_doc_max_bytes") != 65536:
        errors.append("Global %s root project_doc_max_bytes must be 65536" % cfg_path)
    features = parsed_toml.get("features")
    if not isinstance(features, dict) or features.get("codex_hooks") is not True:
        errors.append("Global %s [features].codex_hooks must be true" % cfg_path)
    return errors


def _validate_codex_toml_content(cfg_path, existing_cfg_text, include_cortex):
    """Parse and validate root keys, [features], and [mcp_servers] in Codex config.toml."""
    try:
        parsed_toml = tomllib.loads(existing_cfg_text)
    except Exception as exc:
        return ["Failed to parse TOML %s: %s" % (cfg_path, exc)], []

    errors = _check_codex_toml_root_and_features(cfg_path, parsed_toml)
    mcp_tbl = parsed_toml.get("mcp_servers") or {}
    req_srvs = (
        ("code-graph-context", "cortex") if include_cortex else ("code-graph-context",)
    )
    for req_srv in req_srvs:
        if req_srv not in mcp_tbl:
            errors.append("Global %s missing [mcp_servers.%s]" % (cfg_path, req_srv))
    for srv_name, cfg in mcp_tbl.items():
        errors.extend(
            _scan_single_mcp_server_secrets(
                cfg_path.name, srv_name, cfg, map_keys=("env", "http_headers")
            )
        )
    if errors:
        return errors, []
    return [], [
        "Global Codex config.toml OK (%d MCP servers verified)" % len(mcp_tbl)
    ]


def _read_existing_codex_toml(cfg_path, apply_changes):
    """Read existing config.toml if present; return (text_or_none, errors)."""
    if not cfg_path.is_file():
        if not apply_changes:
            return None, ["Global Codex config.toml missing at %s" % cfg_path]
        return "", []
    c_raw = cfg_path.read_bytes()
    errors = []
    if check_control_bytes(c_raw) and not apply_changes:
        errors.append("Global %s contains forbidden control bytes" % cfg_path)
    text = c_raw.replace(b"\r\n", b"\n").decode("utf-8-sig", errors="replace")
    return text, errors


def _write_codex_toml_if_changed(cfg_path, merged_bytes, backup_dir):
    """Write merged_bytes to cfg_path if different, backing up when requested."""
    if cfg_path.is_file() and cfg_path.read_bytes() == merged_bytes:
        return []
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    if cfg_path.is_file() and backup_dir:
        b_path = Path(backup_dir) / "codex" / "config.toml.bak"
        b_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cfg_path, b_path)
    cfg_path.write_bytes(merged_bytes)
    return ["Updated global Codex config in %s" % cfg_path]


def _sync_and_check_codex_toml(codex_dir, global_config_dir, apply_changes, backup_dir):
    """Merge (when apply_changes is True) and validate global Codex config.toml."""
    cfg_path = codex_dir / "config.toml"
    existing_cfg_text, errors = _read_existing_codex_toml(cfg_path, apply_changes)
    if existing_cfg_text is None:
        return errors, []

    messages = []
    include_cortex = _should_include_cortex_for_codex(
        global_config_dir, existing_cfg_text
    )
    if apply_changes:
        merged_cfg_text = _merge_codex_config_toml(
            existing_cfg_text, include_cortex=include_cortex
        )
        messages.extend(
            _write_codex_toml_if_changed(
                cfg_path, merged_cfg_text.encode("utf-8"), backup_dir
            )
        )
        existing_cfg_text = merged_cfg_text

    if cfg_path.is_file():
        t_errs, t_msgs = _validate_codex_toml_content(
            cfg_path, existing_cfg_text, include_cortex
        )
        errors.extend(t_errs)
        messages.extend(t_msgs)
    return errors, messages


def verify_or_sync_codex(
    repo_root,
    global_config_dir,
    codex_dir,
    apply_changes=False,
    backup_dir=None,
):
    """Verify or apply non-destructive global OpenAI Codex sync to codex_dir."""
    repo_root = Path(repo_root)
    codex_dir = Path(codex_dir)
    x_src = repo_root / CODEX_DIR_NAME

    codex_pairs = _build_codex_pairs(repo_root, x_src, codex_dir)
    errors, messages = _sync_file_pairs(
        codex_pairs, codex_dir, "Codex", apply_changes, backup_dir, "codex"
    )
    sk_errs, sk_msgs = _sync_skill_junctions(
        x_src / "skills", codex_dir, "Codex", apply_changes
    )
    errors.extend(sk_errs)
    messages.extend(sk_msgs)

    hooks_dir_posix = (codex_dir / "hooks").as_posix()
    canon_hooks_raw = (
        (x_src / "hooks.json")
        .read_text(encoding="utf-8")
        .replace(CODEX_HOOKS_REL, hooks_dir_posix)
    )
    required_hooks = json.loads(canon_hooks_raw).get("hooks", {})
    h_errs, h_msgs = _sync_hooks_container_file(
        codex_dir / "hooks.json",
        required_hooks,
        "Codex",
        "codex",
        apply_changes,
        backup_dir,
    )
    errors.extend(h_errs)
    messages.extend(h_msgs)

    t_errs, t_msgs = _sync_and_check_codex_toml(
        codex_dir, global_config_dir, apply_changes, backup_dir
    )
    errors.extend(t_errs)
    messages.extend(t_msgs)
    return errors, messages


def _build_agents_sync_pairs(repo_root, global_config_dir):
    """Build list of (src_path, dst_path) pairs for .agents -> ~/.gemini/config sync."""
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
    for sub in ("rules", "agents"):
        src_dir = repo_root / ".agents" / sub
        if src_dir.is_dir():
            for item_src in sorted(src_dir.glob("*.md")):
                sync_pairs.append((item_src, global_config_dir / sub / item_src.name))
    return sync_pairs


def _check_root_skills_junction(skills_link, expected_skills):
    """Verify that ~/.gemini/config/skills resolves to .agents/skills."""
    if not skills_link.exists():
        return ["Skills directory/junction missing at %s" % skills_link], []
    resolved_skills = skills_link.resolve()
    if os.path.normcase(str(resolved_skills)) != os.path.normcase(str(expected_skills)):
        return [
            "Skills junction mismatch: %s -> %s (expected %s)"
            % (skills_link, resolved_skills, expected_skills)
        ], []
    return [], ["Skills junction OK: %s -> %s" % (skills_link, resolved_skills)]


def sync_hermes_target(repo_root, hermes_dir, apply=False, backup_dir=None):
    """Verify or apply one-way .agents/AGENTS.md and skills sync to hermes_dir."""
    repo_root = Path(repo_root)
    hermes_dir = Path(hermes_dir)
    pairs = [(repo_root / ".agents" / "AGENTS.md", hermes_dir / "AGENTS.md")]
    errors, _ = _sync_file_pairs(
        pairs, hermes_dir, "Hermes", apply, backup_dir, "hermes"
    )
    sk_errs, _ = _sync_skill_junctions(
        repo_root / ".agents" / "skills", hermes_dir, "Hermes", apply
    )
    errors.extend(sk_errs)
    return errors


def _sync_optional_peer_harnesses(
    repo_root,
    global_config_dir,
    claude_dir,
    claude_json,
    codex_dir,
    apply_changes,
    backup_dir,
    hermes_dir=None,
):
    """Run optional Claude, Codex, and Hermes verification/sync passes."""
    errors = []
    messages = []
    if claude_dir is not None:
        c_errs, c_msgs = verify_or_sync_claude(
            repo_root,
            global_config_dir,
            claude_dir,
            claude_json=claude_json,
            apply_changes=apply_changes,
            backup_dir=backup_dir,
        )
        errors.extend(c_errs)
        messages.extend(c_msgs)
    if codex_dir is not None:
        x_errs, x_msgs = verify_or_sync_codex(
            repo_root,
            global_config_dir,
            codex_dir,
            apply_changes=apply_changes,
            backup_dir=backup_dir,
        )
        errors.extend(x_errs)
        messages.extend(x_msgs)
    if hermes_dir is not None:
        h_errs = sync_hermes_target(
            repo_root, hermes_dir, apply=apply_changes, backup_dir=backup_dir
        )
        errors.extend(h_errs)
    return errors, messages


def verify_or_sync(
    repo_root,
    global_config_dir,
    apply_changes=False,
    backup_dir=None,
    claude_dir=None,
    claude_json=None,
    codex_dir=None,
    hermes_dir=None,
):
    """Verify or apply UTF-8 LF sync from .agents/ (and optionally Claude/Codex/Hermes trees) to global dirs."""
    repo_root = Path(repo_root)
    global_config_dir = Path(global_config_dir)
    sync_pairs = _build_agents_sync_pairs(repo_root, global_config_dir)

    for src_path, _ in sync_pairs:
        if not src_path.is_file():
            return 1, ["Missing canonical source: %s" % src_path]
        bad_bytes = check_control_bytes(src_path.read_bytes())
        if bad_bytes:
            return 1, [
                "Source %s contains forbidden control bytes (first at offset %d: 0x%02x)"
                % (src_path, bad_bytes[0][0], bad_bytes[0][1])
            ]

    if apply_changes:
        normalize_lf_utf8(repo_root)

    expected_skills = (repo_root / ".agents" / "skills").resolve()
    errors, messages = _check_root_skills_junction(
        global_config_dir / "skills", expected_skills
    )
    pair_errs, pair_msgs = _sync_file_pairs(
        sync_pairs, global_config_dir, "Global", apply_changes, backup_dir, ""
    )
    errors.extend(pair_errs)
    messages.extend(pair_msgs)

    mcp_errs, mcp_msgs = check_global_mcp_config(
        repo_root, global_config_dir, apply_changes=apply_changes
    )
    errors.extend(mcp_errs)
    messages.extend(mcp_msgs)
    errors.extend(check_plugin_double_load(global_config_dir))

    peer_errs, peer_msgs = _sync_optional_peer_harnesses(
        repo_root,
        global_config_dir,
        claude_dir,
        claude_json,
        codex_dir,
        apply_changes,
        backup_dir,
        hermes_dir=hermes_dir,
    )
    errors.extend(peer_errs)
    messages.extend(peer_msgs)

    return (1, messages + errors) if errors else (0, messages)


def _self_test_backup_and_double_load(repo_root, fake_global, fake_backup):
    """Verify backup path creation and plugin double-load detection."""
    verify_or_sync(
        repo_root=Path(repo_root),
        global_config_dir=fake_global,
        apply_changes=False,
        backup_dir=fake_backup,
    )
    rel_dst = (fake_global / "rules" / "mobile-ui.md").relative_to(fake_global)
    backup_target = fake_backup / rel_dst.with_name(rel_dst.name + ".bak")
    backup_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(fake_global / "rules" / "mobile-ui.md", backup_target)
    if not (fake_backup / "rules" / "mobile-ui.md.bak").is_file():
        return ["Self-test failed: relative backup path not preserved"]

    if check_plugin_double_load(fake_global) != []:
        return ["Self-test failed: unexpected double-load error on clean dir"]
    plugin_dir = fake_global / "plugins" / "antigravity-core"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "plugin.json").write_text(
        json.dumps({"name": "antigravity-core", "disabled": False}),
        encoding="utf-8",
    )
    dl_errs = check_plugin_double_load(fake_global)
    if not any("double-load" in e.lower() for e in dl_errs):
        return ["Self-test failed: did not detect enabled global plugin"]
    return []


def _seed_fake_claude_env(fake_claude, fake_claude_json):
    """Seed synthetic user skills, agents, settings.json, and claude.json for self-test."""
    (fake_claude / "skills" / "custom-user-skill").mkdir(parents=True, exist_ok=True)
    (fake_claude / "skills" / "custom-user-skill" / "SKILL.md").write_text(
        "# User skill\n", encoding="utf-8"
    )
    (fake_claude / "agents").mkdir(parents=True, exist_ok=True)
    (fake_claude / "agents" / "custom-user-agent.md").write_text(
        "# User agent\n", encoding="utf-8"
    )
    (fake_claude / "settings.json").write_text(
        json.dumps({"skipWorkflowUsageWarning": True}), encoding="utf-8"
    )
    fake_claude_json.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "cortex": {"type": "http", "url": "http://127.0.0.1:8585/mcp"},
                    "third-party": {"type": "stdio", "command": "npx"},
                }
            }
        ),
        encoding="utf-8",
    )


def _verify_claude_self_test_state(fake_claude, fake_claude_json):
    """Verify preserved user skills, agents, settings, and merged MCP servers after Claude sync."""
    if not (fake_claude / "skills" / "custom-user-skill" / "SKILL.md").is_file():
        return ["Self-test failed: custom user skill was not preserved"]
    if not (fake_claude / "agents" / "custom-user-agent.md").is_file():
        return ["Self-test failed: custom user agent was not preserved"]
    merged_settings = json.loads(
        (fake_claude / "settings.json").read_text(encoding="utf-8")
    )
    if merged_settings.get("skipWorkflowUsageWarning") is not True:
        return ["Self-test failed: skipWorkflowUsageWarning was not preserved"]
    merged_mcp = json.loads(fake_claude_json.read_text(encoding="utf-8"))["mcpServers"]
    if (
        merged_mcp.get("cortex", {}).get("url") != "http://127.0.0.1:8585/mcp"
        or "code-graph-context" not in merged_mcp
        or "third-party" not in merged_mcp
    ):
        return ["Self-test failed: Claude MCP servers merge incorrect"]
    return []


def _self_test_claude_sync(repo_root, tmp_path, fake_global, fake_backup):
    """Run hermetic twice-applied idempotency and preservation self-tests for Claude sync."""
    fake_claude = tmp_path / "claude"
    fake_claude_json = tmp_path / "claude.json"
    _seed_fake_claude_env(fake_claude, fake_claude_json)

    for apply_flag in (True, True, False):
        c_errs, _ = verify_or_sync_claude(
            repo_root=Path(repo_root),
            global_config_dir=fake_global,
            claude_dir=fake_claude,
            claude_json=fake_claude_json,
            apply_changes=apply_flag,
            backup_dir=fake_backup if apply_flag else None,
        )
        if c_errs:
            return ["Self-test failed during Claude sync (apply=%s): %s" % (apply_flag, c_errs)]
    return _verify_claude_self_test_state(fake_claude, fake_claude_json)


def _check_codex_cortex_free_toml(fake_codex):
    """Verify Codex TOML merge when cortex is not in global mcp_config.json."""
    if not (fake_codex / "skills" / ".system" / "SKILL.md").is_file():
        return ["Self-test failed: Codex .system skill was not preserved"]
    parsed_x = tomllib.loads((fake_codex / "config.toml").read_text(encoding="utf-8"))
    mcp_srvs = parsed_x.get("mcp_servers", {})
    win_tbl = parsed_x.get("windows", {})
    expected_root = (
        parsed_x.get("project_doc_fallback_filenames"),
        parsed_x.get("project_doc_max_bytes"),
        parsed_x.get("model"),
        win_tbl.get("sandbox") if isinstance(win_tbl, dict) else None,
    )
    if expected_root != (["CODEX.md"], 65536, "gpt-5.4", "elevated"):
        return ["Self-test failed: Codex TOML cortex-free merge incorrect"]
    if {"ida-pro-mcp", "code-graph-context"} - set(mcp_srvs) or "cortex" in mcp_srvs:
        return ["Self-test failed: Codex TOML cortex-free merge incorrect"]
    return []


def _self_test_codex_sync(repo_root, tmp_path, fake_global, fake_backup):
    """Run hermetic twice-applied idempotency and TOML merge self-tests for OpenAI Codex."""
    fake_codex = tmp_path / "codex"
    (fake_codex / "skills" / ".system").mkdir(parents=True, exist_ok=True)
    (fake_codex / "skills" / ".system" / "SKILL.md").write_text(
        "# System skill\n", encoding="utf-8"
    )
    (fake_codex / "config.toml").write_text(
        'model = "gpt-5.4"\n[mcp_servers.ida-pro-mcp]\ncommand = "uv"\n[windows]\nsandbox = "elevated"\n',
        encoding="utf-8",
    )
    for apply_flag in (True, True, False):
        x_errs, _ = verify_or_sync_codex(
            repo_root=Path(repo_root),
            global_config_dir=fake_global,
            codex_dir=fake_codex,
            apply_changes=apply_flag,
            backup_dir=fake_backup if apply_flag else None,
        )
        if x_errs:
            return ["Self-test failed during Codex sync (apply=%s): %s" % (apply_flag, x_errs)]

    errs = _check_codex_cortex_free_toml(fake_codex)
    if errs:
        return errs

    gmcp = json.loads((fake_global / "mcp_config.json").read_text(encoding="utf-8"))
    gmcp.setdefault("mcpServers", {})["cortex"] = {"url": "http://127.0.0.1:8585/mcp"}
    (fake_global / "mcp_config.json").write_text(
        json.dumps(gmcp, indent=2) + "\n", encoding="utf-8"
    )
    x_errs_c, _ = verify_or_sync_codex(
        repo_root=Path(repo_root),
        global_config_dir=fake_global,
        codex_dir=fake_codex,
        apply_changes=True,
        backup_dir=fake_backup,
    )
    if x_errs_c:
        return ["Self-test failed during Codex cortex-enabled apply: %s" % x_errs_c]
    parsed_xc = tomllib.loads((fake_codex / "config.toml").read_text(encoding="utf-8"))
    if "cortex" not in (parsed_xc.get("mcp_servers") or {}):
        return ["Self-test failed: Codex TOML opt-in cortex merge missing"]
    return []


def _self_test_hermes_sync(repo_root, tmp_path, fake_backup):
    """Run hermetic twice-applied idempotency and check self-tests for Hermes sync."""
    fake_hermes = tmp_path / "hermes"
    (fake_hermes / "skills" / "custom-hermes-skill").mkdir(parents=True, exist_ok=True)
    (fake_hermes / "skills" / "custom-hermes-skill" / "SKILL.md").write_text(
        "# Custom Hermes skill\n", encoding="utf-8"
    )
    if not sync_hermes_target(repo_root, fake_hermes, apply=False):
        return ["Self-test failed: Hermes check before apply should report missing files"]
    for apply_flag in (True, True, False):
        h_errs = sync_hermes_target(
            repo_root=Path(repo_root),
            hermes_dir=fake_hermes,
            apply=apply_flag,
            backup_dir=fake_backup if apply_flag else None,
        )
        if h_errs:
            return [
                "Self-test failed during Hermes sync (apply=%s): %s"
                % (apply_flag, h_errs)
            ]
    if not (fake_hermes / "AGENTS.md").is_file():
        return ["Self-test failed: Hermes AGENTS.md not synced"]
    if not (fake_hermes / "skills" / "custom-hermes-skill" / "SKILL.md").is_file():
        return ["Self-test failed: custom Hermes skill was not preserved"]
    return []


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
        (fake_global / "rules" / "mobile-ui.md").write_text("old rule\n", encoding="utf-8")

        for step in (
            lambda: _self_test_backup_and_double_load(repo_root, fake_global, fake_backup),
            lambda: _self_test_claude_sync(repo_root, tmp_path, fake_global, fake_backup),
            lambda: _self_test_codex_sync(repo_root, tmp_path, fake_global, fake_backup),
            lambda: _self_test_hermes_sync(repo_root, tmp_path, fake_backup),
        ):
            errs = step()
            if errs:
                return 1, errs

    return 0, ["sync_global_config.py self-test: PASS"]


def _resolve_hermes_cli_dir(args):
    """Return target Hermes directory from CLI args if opted in, else None."""
    if args.hermes_dir is not None:
        return Path(args.hermes_dir)
    if args.hermes:
        return Path.home() / HERMES_DIR_NAME
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Sync .agents, Claude, and OpenAI Codex global configs."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="Verify parity without writing.")
    group.add_argument(
        "--apply", action="store_true", help="Normalize LF and sync global configs."
    )
    group.add_argument("--self-test", action="store_true", help="Run isolated self-test.")
    parser.add_argument(
        "--backup-dir",
        default=None,
        help="Optional directory to back up overwritten files.",
    )
    parser.add_argument(
        "--hermes",
        action="store_true",
        help="Opt-in sync/check for Nous Hermes Agent (~/.hermes).",
    )
    parser.add_argument(
        "--hermes-dir",
        type=Path,
        default=None,
        help="Optional explicit target directory for Nous Hermes Agent sync.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    if args.self_test:
        code, lines = run_self_test(repo_root)
    else:
        global_config_dir = Path.home() / ".gemini" / "config"
        claude_dir = Path.home() / CLAUDE_DIR_NAME
        claude_json = Path.home() / CLAUDE_JSON_NAME
        codex_dir = Path.home() / CODEX_DIR_NAME
        code, lines = verify_or_sync(
            repo_root=repo_root,
            global_config_dir=global_config_dir,
            apply_changes=args.apply,
            backup_dir=args.backup_dir,
            claude_dir=claude_dir,
            claude_json=claude_json,
            codex_dir=codex_dir,
            hermes_dir=_resolve_hermes_cli_dir(args),
        )
    for line in lines:
        print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
