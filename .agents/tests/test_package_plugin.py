"""Unit tests for .agents/scripts/package_plugin.py and plugin manifest."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parents[1]
SCRIPTS_DIR = REPO_ROOT / ".agents" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import package_plugin as pp  # noqa: E402


class TestPackagePlugin(unittest.TestCase):
    def test_source_plugin_manifest_schema(self):
        manifest_path = (
            REPO_ROOT / ".agents" / "plugins" / "antigravity-core" / "plugin.json"
        )
        self.assertTrue(manifest_path.is_file(), "Missing plugin.json")
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(
            data.get("$schema"), "https://antigravity.google/schemas/v1/plugin.json"
        )
        self.assertEqual(data.get("name"), "antigravity-core")
        self.assertIs(data.get("disabled"), True)
        self.assertEqual(pp.validate_plugin_manifest(data), [])
        bad_schema = dict(data)
        bad_schema["$schema"] = "http://invalid-schema.example.com"
        self.assertTrue(
            any("$schema" in err for err in pp.validate_plugin_manifest(bad_schema))
        )

    def test_strip_leading_frontmatter_fence_full_block_and_bare(self):
        bare = b"---\r\n# Heading\r\nBody\r\n"
        self.assertEqual(
            pp.strip_leading_frontmatter_fence(bare), b"# Heading\nBody\n"
        )
        full_block = b"---\nname: test\ndescription: demo\n---\n# Heading\nBody\n"
        self.assertEqual(
            pp.strip_leading_frontmatter_fence(full_block), b"# Heading\nBody\n"
        )

    def test_package_plugin_builds_complete_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "antigravity-core"
            code, messages = pp.build_plugin_bundle(
                repo_root=REPO_ROOT, output_dir=out_dir, enable=True
            )
            self.assertEqual(code, 0, "\n".join(messages))
            manifest = json.loads((out_dir / "plugin.json").read_text(encoding="utf-8"))
            self.assertEqual(
                manifest.get("$schema"),
                "https://antigravity.google/schemas/v1/plugin.json",
            )
            self.assertIs(manifest.get("disabled"), False)
            rules_md = out_dir / "rules" / "AGENTS.md"
            self.assertTrue(rules_md.is_file())
            rules_bytes = rules_md.read_bytes()
            self.assertLessEqual(
                len(rules_bytes),
                18000,
                "rules/AGENTS.md must stay <= 18000 bytes to prevent 24 KB truncation",
            )
            rules_text = rules_bytes.decode("utf-8")
            self.assertFalse(
                rules_text.startswith("---"),
                "rules/AGENTS.md must not start with YAML frontmatter fence",
            )
            self.assertTrue((out_dir / "hooks.json").is_file())
            self.assertTrue((out_dir / "hooks" / "brc-guard.ps1").is_file())
            self.assertTrue((out_dir / "hooks" / "telemetry-append.ps1").is_file())
            self.assertTrue((out_dir / "mcp_config.json").is_file())
            self.assertTrue(
                (out_dir / "skills" / "security-auditor" / "SKILL.md").is_file()
            )
            for script_name in ("secret_scan.py", "mcp_keyring_launcher.py"):
                script_path = out_dir / "scripts" / script_name
                self.assertTrue(
                    script_path.is_file(), f"Missing bundled script: {script_name}"
                )
                self.assertNotIn(b"\r\n", script_path.read_bytes())
            scaffold_scanner = (
                out_dir / "skills" / "harness-scaffold" / "scripts" / "secret_scan.py"
            )
            self.assertTrue(
                scaffold_scanner.is_file(),
                "Missing skills/harness-scaffold/scripts/secret_scan.py",
            )
            self.assertNotIn(b"\r\n", scaffold_scanner.read_bytes())
            for excluded in (
                "package_plugin.py",
                "sync_global_config.py",
                "remediate_legacy_mcp.py",
            ):
                self.assertFalse(
                    (out_dir / "scripts" / excluded).exists(),
                    f"Repo-only script must not be bundled: {excluded}",
                )

    def test_package_plugin_rejects_in_place_and_ancestor_dirs(self):
        in_place_dir = REPO_ROOT / ".agents" / "plugins" / "antigravity-core"
        readme_path = in_place_dir / "README.md"
        code, messages = pp.build_plugin_bundle(
            repo_root=REPO_ROOT, output_dir=in_place_dir, enable=True
        )
        self.assertEqual(code, 1)
        self.assertTrue(any("Refusing" in m for m in messages))
        self.assertTrue(readme_path.is_file(), "README.md must not be deleted")

        with tempfile.TemporaryDirectory() as tmp:
            fake_repo = Path(tmp) / "workspace" / "repo"
            fake_plugin_src = (
                fake_repo / ".agents" / "plugins" / "antigravity-core"
            )
            fake_plugin_src.mkdir(parents=True, exist_ok=True)
            (fake_plugin_src / "plugin.json").write_text(
                json.dumps(
                    {
                        "$schema": "https://antigravity.google/schemas/v1/plugin.json",
                        "name": "antigravity-core",
                        "description": "test",
                        "disabled": True,
                    }
                ),
                encoding="utf-8",
            )
            for forbidden_dir in (
                fake_plugin_src,
                fake_plugin_src / "nested",
                fake_repo,
                fake_repo / ".agents",
                fake_repo.parent,
            ):
                code, messages = pp.build_plugin_bundle(
                    repo_root=fake_repo, output_dir=forbidden_dir, enable=True
                )
                self.assertEqual(code, 1, f"Expected failure for {forbidden_dir}")
                self.assertTrue(
                    any("Refusing" in m for m in messages),
                    f"Expected refusal message for {forbidden_dir}: {messages}",
                )
            self.assertTrue((fake_plugin_src / "plugin.json").is_file())

    def test_sync_global_config_double_load_guard_and_self_test(self):
        import sync_global_config as sgc

        code, msgs = sgc.run_self_test(REPO_ROOT)
        self.assertEqual(code, 0, "\n".join(msgs))

        with tempfile.TemporaryDirectory() as tmp:
            g_dir = Path(tmp)
            plugin_dir = g_dir / "plugins" / "antigravity-core"
            plugin_dir.mkdir(parents=True, exist_ok=True)
            (plugin_dir / "plugin.json").write_text(
                json.dumps({"name": "antigravity-core", "disabled": False}),
                encoding="utf-8",
            )
            errs = sgc.check_plugin_double_load(g_dir)
            self.assertTrue(
                any("double-load" in e.lower() for e in errs),
                f"Expected double-load error, got: {errs}",
            )


if __name__ == "__main__":
    unittest.main()

