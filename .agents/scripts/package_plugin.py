"""Build and validate a standalone Antigravity plugin bundle for antigravity-core.

Packages `.agents/plugins/antigravity-core/plugin.json`, `README.md`,
`AGENTS.md` (as `rules/AGENTS.md` with leading frontmatter fence removed per
the Antigravity plugin specification), `hooks.json`, `hooks/*.ps1`,
`mcp_config.json`, and `skills/*` into a self-contained plugin directory.

Usage:
    python .agents/scripts/package_plugin.py --self-test
    python .agents/scripts/package_plugin.py --output-dir <dir> [--enable]
"""
import argparse
import hashlib
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

ALLOWED_PLUGIN_FIELDS = {
    "$schema",
    "name",
    "description",
    "logo",
    "suggestedPrompts",
    "displayName",
    "version",
    "disabled",
}
PLUGIN_SCHEMA_URL = "https://antigravity.google/schemas/v1/plugin.json"
BUNDLED_RUNTIME_SCRIPTS = ("secret_scan.py", "mcp_keyring_launcher.py")
KEBAB_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FORBIDDEN_CONTROL_BYTES = (
    set(range(0x00, 0x09)) | {0x0B, 0x0C, 0x0D} | set(range(0x0E, 0x20))
)


def _is_valid_suggested_prompts(prompts):
    """Return True if prompts is None or a list of 1..3 non-empty strings."""
    if prompts is None:
        return True
    if not isinstance(prompts, list) or not (1 <= len(prompts) <= 3):
        return False
    return all(isinstance(p, str) and bool(p.strip()) for p in prompts)


def _check_manifest_identity(data):
    """Check $schema, name, and description fields on a plugin.json dict."""
    violations = []
    if "$schema" in data and data["$schema"] != PLUGIN_SCHEMA_URL:
        violations.append("plugin.json '$schema' must be %r" % PLUGIN_SCHEMA_URL)
    name = data.get("name", "")
    if not isinstance(name, str) or not KEBAB_NAME_RE.fullmatch(name):
        violations.append("plugin.json 'name' must be lowercase kebab-case")
    desc = data.get("description", "")
    if not isinstance(desc, str) or not desc.strip():
        violations.append("plugin.json 'description' must be a non-empty string")
    return violations


def _check_manifest_fields(data):
    """Check required and optional fields on a plugin.json dict."""
    violations = _check_manifest_identity(data)
    if not _is_valid_suggested_prompts(data.get("suggestedPrompts")):
        violations.append(
            "plugin.json 'suggestedPrompts' must be a list of 1-3 non-empty strings"
        )
    if "disabled" in data and not isinstance(data["disabled"], bool):
        violations.append("plugin.json 'disabled' must be a boolean")
    return violations


def validate_plugin_manifest(data):
    """Validate a plugin.json dictionary against the Antigravity schema."""
    if not isinstance(data, dict):
        return ["plugin.json root must be a JSON object"]
    violations = []
    unknown = sorted(set(data.keys()) - ALLOWED_PLUGIN_FIELDS)
    if unknown:
        violations.append(
            "plugin.json contains unsupported top-level fields: %s" % unknown
        )
    violations.extend(_check_manifest_fields(data))
    return violations


def _find_closing_fence_index(lines):
    """Return the index of the closing '---' line within the first 35 lines, or None."""
    for idx in range(1, min(len(lines), 35)):
        if lines[idx].strip() == b"---":
            return idx
    return None


def strip_leading_frontmatter_fence(raw_bytes):
    """Remove a leading YAML frontmatter block or bare '---\\n' fence from rules/AGENTS.md."""
    cleaned = raw_bytes.replace(b"\r\n", b"\n")
    if cleaned.startswith(b"\xef\xbb\xbf"):
        cleaned = cleaned[3:]
    if not cleaned.startswith(b"---\n"):
        return cleaned
    lines = cleaned.split(b"\n")
    closing_idx = _find_closing_fence_index(lines)
    if closing_idx is not None:
        return b"\n".join(lines[closing_idx + 1 :])
    return cleaned[4:]


def generate_integrity_manifest(bundle_dir):
    """Generate and write deterministic SHA-256 integrity_manifest.json for a plugin bundle."""
    bundle_dir = Path(bundle_dir)
    files_map = {}
    for file_path in sorted(bundle_dir.rglob("*")):
        if not file_path.is_file():
            continue
        rel = file_path.relative_to(bundle_dir).as_posix()
        if rel == "integrity_manifest.json":
            continue
        raw = file_path.read_bytes()
        files_map[rel] = {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
        }
    manifest = {
        "schema_version": 1,
        "files": files_map,
    }
    (bundle_dir / "integrity_manifest.json").write_bytes(
        (json.dumps(manifest, indent=2) + "\n").encode("utf-8")
    )
    return manifest


def _load_expected_manifest_files(bundle_dir):
    """Load and validate the files dictionary from integrity_manifest.json."""
    manifest_path = bundle_dir / "integrity_manifest.json"
    if not manifest_path.is_file():
        return None, ["Missing integrity_manifest.json in %s" % bundle_dir]
    try:
        manifest = json.loads(manifest_path.read_bytes().decode("utf-8"))
    except Exception as exc:
        return None, ["Unparseable integrity_manifest.json: %s" % exc]
    expected_files = manifest.get("files")
    if not isinstance(expected_files, dict) or not expected_files:
        return None, ["integrity_manifest.json 'files' must be a non-empty object"]
    return expected_files, []


def _check_bundled_file_hash(file_path, rel, expected_files):
    """Check one bundled file against expected_files; return violation string or None."""
    if rel not in expected_files:
        return "Untracked file in plugin bundle: %s" % rel
    raw = file_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    rec = expected_files[rel]
    if digest != rec.get("sha256") or len(raw) != rec.get("bytes"):
        return "SHA-256 / byte mismatch in bundled file: %s" % rel
    return None


def verify_plugin_bundle(bundle_dir):
    """Verify a packaged plugin bundle against its integrity_manifest.json."""
    bundle_dir = Path(bundle_dir)
    expected_files, load_errs = _load_expected_manifest_files(bundle_dir)
    if load_errs:
        return 1, load_errs

    violations = []
    actual_rels = set()
    for file_path in sorted(bundle_dir.rglob("*")):
        if not file_path.is_file():
            continue
        rel = file_path.relative_to(bundle_dir).as_posix()
        if rel == "integrity_manifest.json":
            continue
        actual_rels.add(rel)
        err = _check_bundled_file_hash(file_path, rel, expected_files)
        if err:
            violations.append(err)
    for missing in sorted(set(expected_files.keys()) - actual_rels):
        violations.append("Missing bundled file listed in manifest: %s" % missing)
    if violations:
        return 1, violations
    return 0, [
        "Plugin bundle integrity OK (%d files verified)" % len(expected_files)
    ]


def _is_forbidden_output_dir(repo_root, agents_dir, plugin_src_dir, output_dir):
    """Return True if output_dir would overwrite the repository or its source tree."""
    repo_resolved = repo_root.resolve()
    agents_resolved = agents_dir.resolve()
    src_resolved = plugin_src_dir.resolve()
    out_resolved = output_dir.resolve()
    return (
        out_resolved in {repo_resolved, agents_resolved, src_resolved}
        or out_resolved in repo_resolved.parents
        or src_resolved in out_resolved.parents
    )


def _copy_metadata_and_sidecars(plugin_src_dir, agents_dir, output_dir, manifest_out):
    """Write plugin.json, README.md, assets, and sidecars into output_dir."""
    (output_dir / "plugin.json").write_bytes(
        (json.dumps(manifest_out, indent=2) + "\n").encode("utf-8")
    )
    readme_src = plugin_src_dir / "README.md"
    if readme_src.is_file():
        (output_dir / "README.md").write_bytes(
            readme_src.read_bytes().replace(b"\r\n", b"\n")
        )
    assets_src = plugin_src_dir / "assets"
    if assets_src.is_dir():
        shutil.copytree(assets_src, output_dir / "assets")
    for sidecars_candidate in (plugin_src_dir / "sidecars", agents_dir / "sidecars"):
        if sidecars_candidate.is_dir():
            shutil.copytree(
                sidecars_candidate,
                output_dir / "sidecars",
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "node_modules"),
            )
    sidecars_out = output_dir / "sidecars"
    if sidecars_out.is_dir():
        for sc_file in sorted(sidecars_out.rglob("*")):
            if sc_file.is_file() and sc_file.suffix in {".md", ".json", ".ps1", ".py", ".js"}:
                sc_file.write_bytes(sc_file.read_bytes().replace(b"\r\n", b"\n"))


def _copy_hooks_and_configs(agents_dir, output_dir):
    """Copy hooks.json, mcp_config.json, and hooks/*.ps1 into output_dir."""
    for json_name in ("hooks.json", "mcp_config.json"):
        src = agents_dir / json_name
        if not src.is_file():
            return ["Missing required file: %s" % src]
        (output_dir / json_name).write_bytes(src.read_bytes().replace(b"\r\n", b"\n"))
    hooks_dst = output_dir / "hooks"
    hooks_dst.mkdir(parents=True, exist_ok=True)
    for ps1_path in sorted((agents_dir / "hooks").glob("*.ps1")):
        (hooks_dst / ps1_path.name).write_bytes(
            ps1_path.read_bytes().replace(b"\r\n", b"\n")
        )
    return []


def _copy_rules_and_agents(agents_dir, output_dir):
    """Copy rules/AGENTS.md, modular rules/*.md, and agents/*.md into output_dir."""
    rules_dst = output_dir / "rules"
    rules_dst.mkdir(parents=True, exist_ok=True)
    agents_md_src = agents_dir / "AGENTS.md"
    if not agents_md_src.is_file():
        return ["Missing required rules source: %s" % agents_md_src]
    (rules_dst / "AGENTS.md").write_bytes(
        strip_leading_frontmatter_fence(agents_md_src.read_bytes())
    )
    rules_src_dir = agents_dir / "rules"
    if rules_src_dir.is_dir():
        for rule_path in sorted(rules_src_dir.glob("*.md")):
            (rules_dst / rule_path.name).write_bytes(
                rule_path.read_bytes().replace(b"\r\n", b"\n")
            )
    custom_agents_src = agents_dir / "agents"
    if custom_agents_src.is_dir():
        custom_agents_dst = output_dir / "agents"
        custom_agents_dst.mkdir(parents=True, exist_ok=True)
        for agent_path in sorted(custom_agents_src.glob("*.md")):
            (custom_agents_dst / agent_path.name).write_bytes(
                agent_path.read_bytes().replace(b"\r\n", b"\n")
            )
    return []


def _copy_skills_and_runtime_scripts(agents_dir, output_dir):
    """Copy skills/* and runtime scripts into output_dir."""
    skills_dst = output_dir / "skills"
    shutil.copytree(
        agents_dir / "skills",
        skills_dst,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    scripts_src_dir = agents_dir / "scripts"
    scripts_dst = output_dir / "scripts"
    scripts_dst.mkdir(parents=True, exist_ok=True)
    for script_name in BUNDLED_RUNTIME_SCRIPTS:
        script_src = scripts_src_dir / script_name
        if not script_src.is_file():
            return ["Missing required runtime script: %s" % script_src]
        normalized = script_src.read_bytes().replace(b"\r\n", b"\n")
        (scripts_dst / script_name).write_bytes(normalized)

    scaffold_scripts_dst = skills_dst / "harness-scaffold" / "scripts"
    scaffold_scripts_dst.mkdir(parents=True, exist_ok=True)
    (scaffold_scripts_dst / "secret_scan.py").write_bytes(
        (scripts_dst / "secret_scan.py").read_bytes()
    )
    return []


def build_plugin_bundle(repo_root, output_dir, enable=True):
    """Materialize the complete antigravity-core plugin bundle into output_dir."""
    repo_root = Path(repo_root)
    output_dir = Path(output_dir)
    agents_dir = repo_root / ".agents"
    plugin_src_dir = agents_dir / "plugins" / "antigravity-core"

    if _is_forbidden_output_dir(repo_root, agents_dir, plugin_src_dir, output_dir):
        return 1, [
            "Refusing to overwrite repository, ancestor, or in-repo source manifest directory: %s"
            % output_dir
        ]

    manifest_src = plugin_src_dir / "plugin.json"
    if not manifest_src.is_file():
        return 1, ["Missing source manifest: %s" % manifest_src]

    manifest_data = json.loads(manifest_src.read_bytes().decode("utf-8"))
    errors = validate_plugin_manifest(manifest_data)
    if errors:
        return 1, errors

    manifest_out = dict(manifest_data, disabled=not bool(enable))
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    _copy_metadata_and_sidecars(plugin_src_dir, agents_dir, output_dir, manifest_out)
    for step_fn in (
        _copy_hooks_and_configs,
        _copy_rules_and_agents,
        _copy_skills_and_runtime_scripts,
    ):
        step_errs = step_fn(agents_dir, output_dir)
        if step_errs:
            return 1, step_errs

    generate_integrity_manifest(output_dir)
    return 0, ["Packaged antigravity-core plugin bundle at %s" % output_dir]


def _check_forbidden_targets_self_test(repo_root):
    """Ensure build_plugin_bundle rejects repo_root, .agents, and source plugin dir."""
    for forbidden in (
        Path(repo_root),
        Path(repo_root) / ".agents",
        Path(repo_root) / ".agents" / "plugins" / "antigravity-core",
    ):
        f_code, _ = build_plugin_bundle(repo_root, forbidden, enable=True)
        if f_code == 0:
            return [
                "Self-test failed: bundler did not reject forbidden target %s"
                % forbidden
            ]
    return []


def _check_bundled_modular_rules(repo_root, target):
    """Verify bundled modular rules/*.md retain YAML frontmatter."""
    rules_src_dir = Path(repo_root) / ".agents" / "rules"
    if not rules_src_dir.is_dir():
        return []
    for rule_src in sorted(rules_src_dir.glob("*.md")):
        bundled_rule = target / "rules" / rule_src.name
        if not bundled_rule.is_file() or not bundled_rule.read_bytes().startswith(b"---\n"):
            return [
                "Self-test failed: missing or invalid bundled modular rule rules/%s"
                % rule_src.name
            ]
    return []


def _check_bundled_manifest_and_rules(repo_root, target):
    """Verify bundled plugin.json, rules/AGENTS.md, and modular rules/*.md."""
    built_manifest = json.loads((target / "plugin.json").read_bytes().decode("utf-8"))
    if built_manifest.get("$schema") != PLUGIN_SCHEMA_URL:
        return [
            "Self-test failed: expected $schema=%r in bundled plugin.json"
            % PLUGIN_SCHEMA_URL
        ]
    if built_manifest.get("disabled") is not False:
        return ["Self-test failed: expected disabled=false in enabled bundle"]
    rules_bytes = (target / "rules" / "AGENTS.md").read_bytes()
    if rules_bytes.startswith(b"---"):
        return ["Self-test failed: rules/AGENTS.md still starts with '---'"]
    if len(rules_bytes) > 18000:
        return [
            "Self-test failed: rules/AGENTS.md exceeds 18000 bytes (%d)"
            % len(rules_bytes)
        ]
    return _check_bundled_modular_rules(repo_root, target)


def _check_bundled_custom_agents(repo_root, target):
    """Verify bundled custom agents/*.md exist."""
    custom_agents_src = Path(repo_root) / ".agents" / "agents"
    if not custom_agents_src.is_dir():
        return []
    for agent_src in sorted(custom_agents_src.glob("*.md")):
        if not (target / "agents" / agent_src.name).is_file():
            return ["Self-test failed: missing bundled custom agent agents/%s" % agent_src.name]
    return []


def _check_bundled_agents_and_scripts(repo_root, target):
    """Verify custom agents, hooks, runtime scripts, and excluded repo-only scripts."""
    agent_errs = _check_bundled_custom_agents(repo_root, target)
    if agent_errs:
        return agent_errs
    if not (target / "hooks" / "brc-guard.ps1").is_file():
        return ["Self-test failed: missing hooks/brc-guard.ps1"]
    for script_name in BUNDLED_RUNTIME_SCRIPTS:
        if not (target / "scripts" / script_name).is_file():
            return ["Self-test failed: missing scripts/%s" % script_name]
    if not (target / "skills" / "harness-scaffold" / "scripts" / "secret_scan.py").is_file():
        return ["Self-test failed: missing skills/harness-scaffold/scripts/secret_scan.py"]
    if (target / "scripts" / "package_plugin.py").exists():
        return ["Self-test failed: repo-only package_plugin.py must not be bundled"]
    return []


def _has_bom_or_control_bytes(raw):
    """Return True if raw starts with UTF-8 BOM or contains forbidden control bytes."""
    if raw.startswith(b"\xef\xbb\xbf"):
        return True
    return any(b in FORBIDDEN_CONTROL_BYTES for b in raw)


def _check_bundle_encoding_and_tamper(target):
    """Verify UTF-8 no-BOM LF encoding and integrity_manifest tamper detection."""
    text_exts = {".md", ".json", ".ps1", ".py", ".js"}
    for bundled_file in sorted(target.rglob("*")):
        if bundled_file.is_file() and bundled_file.suffix in text_exts:
            if _has_bom_or_control_bytes(bundled_file.read_bytes()):
                return ["Self-test failed: BOM or control/CR byte in %s" % bundled_file]
    v_code, v_msgs = verify_plugin_bundle(target)
    if v_code != 0:
        return ["Self-test failed: verify_plugin_bundle: %s" % v_msgs]
    (target / "README.md").write_bytes(b"tampered\n")
    t_code, _ = verify_plugin_bundle(target)
    if t_code == 0:
        return ["Self-test failed: verify_plugin_bundle missed tampered file"]
    return []


def run_self_test(repo_root):
    """Run an in-memory/tempdir self-test of the plugin bundler."""
    with tempfile.TemporaryDirectory() as tmp:
        forbid_errs = _check_forbidden_targets_self_test(repo_root)
        if forbid_errs:
            return 1, forbid_errs
        target = Path(tmp) / "antigravity-core"
        code, messages = build_plugin_bundle(repo_root, target, enable=True)
        if code != 0:
            return code, messages
        for check_fn in (
            lambda: _check_bundled_manifest_and_rules(repo_root, target),
            lambda: _check_bundled_agents_and_scripts(repo_root, target),
            lambda: _check_bundle_encoding_and_tamper(target),
        ):
            errs = check_fn()
            if errs:
                return 1, errs
    return 0, ["package_plugin.py self-test: PASS"]


def main():
    parser = argparse.ArgumentParser(
        description="Package antigravity-core as a standalone Antigravity plugin."
    )
    parser.add_argument(
        "--self-test", action="store_true", help="Run self-test in a temp directory."
    )
    parser.add_argument(
        "--output-dir", default=None, help="Target directory for the plugin bundle."
    )
    parser.add_argument(
        "--verify-dir",
        default=None,
        help="Verify an existing plugin bundle against its integrity_manifest.json.",
    )
    parser.add_argument(
        "--enable",
        action="store_true",
        help="Set disabled=false in the packaged plugin.json.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    if args.self_test:
        code, lines = run_self_test(repo_root)
    elif args.verify_dir:
        code, lines = verify_plugin_bundle(Path(args.verify_dir))
    elif args.output_dir:
        code, lines = build_plugin_bundle(
            repo_root=repo_root, output_dir=Path(args.output_dir), enable=args.enable
        )
    else:
        parser.error("Specify --self-test, --verify-dir <dir>, or --output-dir <dir>")
        return 2

    for line in lines:
        print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
