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
import os
import shutil
import sys
from pathlib import Path

FORBIDDEN_CONTROL_BYTES = (
    set(range(0x00, 0x09)) | {0x0B, 0x0C, 0x0D} | set(range(0x0E, 0x20))
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
        cleaned = cleaned.replace(b"read-only \x0desearch type", b"read-only `research` type")
        cleaned = cleaned.replace(
            b"\x0cailed to construct executor: no tool converter registered for moma_search.",
            b"`failed to construct executor: no tool converter registered for moma_search`.",
        )
        cleaned = cleaned.replace(
            b"predefined self or \x0desearch subagents",
            b"predefined `self` or `research` subagents",
        )
        if cleaned != raw:
            path.write_bytes(cleaned)
            normalized.append(str(path.relative_to(repo_root)))
    return normalized


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
                backup_path = Path(backup_dir) / (dst_path.name + ".bak")
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

    if errors:
        return 1, messages + errors
    return 0, messages


def main():
    parser = argparse.ArgumentParser(description="Sync .agents/AGENTS.md to global config.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true", help="Verify parity without writing.")
    group.add_argument("--apply", action="store_true", help="Normalize LF and sync global AGENTS.md.")
    parser.add_argument("--backup-dir", default=None, help="Optional directory to back up AGENTS.md.")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
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
