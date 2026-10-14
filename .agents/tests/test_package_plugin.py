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
        self.assertEqual(data.get("name"), "antigravity-core")
        self.assertIs(data.get("disabled"), True)
        self.assertEqual(pp.validate_plugin_manifest(data), [])

    def test_package_plugin_builds_complete_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "antigravity-core"
            code, messages = pp.build_plugin_bundle(
                repo_root=REPO_ROOT, output_dir=out_dir, enable=True
            )
            self.assertEqual(code, 0, "\n".join(messages))
            manifest = json.loads((out_dir / "plugin.json").read_text(encoding="utf-8"))
            self.assertIs(manifest.get("disabled"), False)
            rules_md = out_dir / "rules" / "AGENTS.md"
            self.assertTrue(rules_md.is_file())
            rules_text = rules_md.read_text(encoding="utf-8")
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


if __name__ == "__main__":
    unittest.main()
