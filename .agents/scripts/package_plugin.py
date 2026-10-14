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
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

ALLOWED_PLUGIN_FIELDS = {
    "name",
    "description",
    "logo",
    "suggestedPrompts",
    "displayName",
    "version",
    "disabled",
}
BUNDLED_RUNTIME_SCRIPTS = ("secret_scan.py", "mcp_keyring_launcher.py")
KEBAB_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def validate_plugin_manifest(data):
    """Validate a plugin.json dictionary against the Antigravity schema."""
    violations = []
    if not isinstance(data, dict):
        return ["plugin.json root must be a JSON object"]
    unknown = sorted(set(data.keys()) - ALLOWED_PLUGIN_FIELDS)
    if unknown:
        violations.append(
            "plugin.json contains unsupported top-level fields: %s" % unknown
        )
    name = data.get("name", "")
    if not isinstance(name, str) or not KEBAB_NAME_RE.fullmatch(name):
        violations.append("plugin.json 'name' must be lowercase kebab-case")
    desc = data.get("description", "")
    if not isinstance(desc, str) or not desc.strip():
        violations.append("plugin.json 'description' must be a non-empty string")
    prompts = data.get("suggestedPrompts")
    if prompts is not None:
        if (
            not isinstance(prompts, list)
            or len(prompts) > 3
            or not all(isinstance(p, str) and p.strip() for p in prompts)
        ):
            violations.append(
                "plugin.json 'suggestedPrompts' must be a list of 1-3 non-empty strings"
            )
    if "disabled" in data and not isinstance(data["disabled"], bool):
        violations.append("plugin.json 'disabled' must be a boolean")
    return violations


def strip_leading_frontmatter_fence(raw_bytes):
    """Remove a leading '---\\n' marker so rules/AGENTS.md is plain Markdown."""
    cleaned = raw_bytes.replace(b"\r\n", b"\n")
    if cleaned.startswith(b"---\n"):
        cleaned = cleaned[4:]
    return cleaned


def build_plugin_bundle(repo_root, output_dir, enable=True):
    """Materialize the complete antigravity-core plugin bundle into output_dir."""
    repo_root = Path(repo_root)
    output_dir = Path(output_dir)
    agents_dir = repo_root / ".agents"
    plugin_src_dir = agents_dir / "plugins" / "antigravity-core"
    manifest_src = plugin_src_dir / "plugin.json"

    if not manifest_src.is_file():
        return 1, ["Missing source manifest: %s" % manifest_src]

    manifest_data = json.loads(manifest_src.read_bytes().decode("utf-8"))
    errors = validate_plugin_manifest(manifest_data)
    if errors:
        return 1, errors

    manifest_out = dict(manifest_data)
    manifest_out["disabled"] = not bool(enable)

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / "plugin.json").write_bytes(
        (json.dumps(manifest_out, indent=2) + "\n").encode("utf-8")
    )

    readme_src = plugin_src_dir / "README.md"
    if readme_src.is_file():
        (output_dir / "README.md").write_bytes(
            readme_src.read_bytes().replace(b"\r\n", b"\n")
        )

    for json_name in ("hooks.json", "mcp_config.json"):
        src = agents_dir / json_name
        if not src.is_file():
            return 1, ["Missing required file: %s" % src]
        (output_dir / json_name).write_bytes(src.read_bytes().replace(b"\r\n", b"\n"))

    hooks_dst = output_dir / "hooks"
    hooks_dst.mkdir(parents=True, exist_ok=True)
    for ps1_path in sorted((agents_dir / "hooks").glob("*.ps1")):
        (hooks_dst / ps1_path.name).write_bytes(
            ps1_path.read_bytes().replace(b"\r\n", b"\n")
        )

    rules_dst = output_dir / "rules"
    rules_dst.mkdir(parents=True, exist_ok=True)
    agents_md_src = agents_dir / "AGENTS.md"
    if not agents_md_src.is_file():
        return 1, ["Missing required rules source: %s" % agents_md_src]
    (rules_dst / "AGENTS.md").write_bytes(
        strip_leading_frontmatter_fence(agents_md_src.read_bytes())
    )

    skills_src = agents_dir / "skills"
    skills_dst = output_dir / "skills"
    shutil.copytree(
        skills_src,
        skills_dst,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )

    scripts_src_dir = agents_dir / "scripts"
    scripts_dst = output_dir / "scripts"
    scripts_dst.mkdir(parents=True, exist_ok=True)
    for script_name in BUNDLED_RUNTIME_SCRIPTS:
        script_src = scripts_src_dir / script_name
        if not script_src.is_file():
            return 1, ["Missing required runtime script: %s" % script_src]
        normalized = script_src.read_bytes().replace(b"\r\n", b"\n")
        (scripts_dst / script_name).write_bytes(normalized)

    scaffold_scripts_dst = skills_dst / "harness-scaffold" / "scripts"
    scaffold_scripts_dst.mkdir(parents=True, exist_ok=True)
    (scaffold_scripts_dst / "secret_scan.py").write_bytes(
        (scripts_dst / "secret_scan.py").read_bytes()
    )

    return 0, ["Packaged antigravity-core plugin bundle at %s" % output_dir]


def run_self_test(repo_root):
    """Run an in-memory/tempdir self-test of the plugin bundler."""
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "antigravity-core"
        code, messages = build_plugin_bundle(repo_root, target, enable=True)
        if code != 0:
            return code, messages
        built_manifest = json.loads(
            (target / "plugin.json").read_bytes().decode("utf-8")
        )
        if built_manifest.get("disabled") is not False:
            return 1, ["Self-test failed: expected disabled=false in enabled bundle"]
        rules_bytes = (target / "rules" / "AGENTS.md").read_bytes()
        if rules_bytes.startswith(b"---"):
            return 1, ["Self-test failed: rules/AGENTS.md still starts with '---'"]
        if not (target / "hooks" / "brc-guard.ps1").is_file():
            return 1, ["Self-test failed: missing hooks/brc-guard.ps1"]
        for script_name in BUNDLED_RUNTIME_SCRIPTS:
            if not (target / "scripts" / script_name).is_file():
                return 1, ["Self-test failed: missing scripts/%s" % script_name]
        if not (
            target / "skills" / "harness-scaffold" / "scripts" / "secret_scan.py"
        ).is_file():
            return 1, [
                "Self-test failed: missing skills/harness-scaffold/scripts/secret_scan.py"
            ]
        if (target / "scripts" / "package_plugin.py").exists():
            return 1, [
                "Self-test failed: repo-only package_plugin.py must not be bundled"
            ]
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
        "--enable",
        action="store_true",
        help="Set disabled=false in the packaged plugin.json.",
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    if args.self_test:
        code, lines = run_self_test(repo_root)
    elif args.output_dir:
        code, lines = build_plugin_bundle(
            repo_root=repo_root, output_dir=Path(args.output_dir), enable=args.enable
        )
    else:
        parser.error("Specify either --self-test or --output-dir <dir>")
        return 2

    for line in lines:
        print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
