"""Unit tests for mcp_keyring_launcher.py and remediate_legacy_mcp.py."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parents[1]
SCRIPTS_DIR = REPO_ROOT / ".agents" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


class TestMcpKeyringLauncher(unittest.TestCase):
    def test_injects_secrets_from_keyring_and_preserves_stdio(self):
        import mcp_keyring_launcher as mkl

        vault = {
            ("antigravity-mcp", "TEST_API_KEY"): "super-secret-value-12345",
        }

        def fake_get_password(service, key):
            return vault.get((service, key))

        with mock.patch.object(mkl, "get_secret", side_effect=fake_get_password):
            env = mkl.build_injected_env(
                service="antigravity-mcp",
                env_keys=["TEST_API_KEY"],
                base_env={"EXISTING_VAR": "ok"},
            )
            self.assertEqual(env["TEST_API_KEY"], "super-secret-value-12345")
            self.assertEqual(env["EXISTING_VAR"], "ok")

    def test_missing_key_raises_fail_closed_error(self):
        import mcp_keyring_launcher as mkl

        with mock.patch.object(mkl, "get_secret", return_value=None):
            with self.assertRaises(RuntimeError):
                mkl.build_injected_env(
                    service="antigravity-mcp",
                    env_keys=["MISSING_SECRET_KEY"],
                    base_env={},
                )

    def test_passthrough_subprocess_preserves_exact_stdout_bytes(self):
        import mcp_keyring_launcher as mkl

        with mock.patch.object(mkl, "get_secret", return_value="secret-xyz"):
            code = mkl.run_with_keyring(
                service="antigravity-mcp",
                env_keys=["INJECTED_TEST_KEY"],
                command=[
                    sys.executable,
                    "-c",
                    "import os, sys; sys.exit(0 if os.environ.get('INJECTED_TEST_KEY') == 'secret-xyz' else 1)",
                ],
            )
            self.assertEqual(code, 0)


class TestRemediateLegacyMcp(unittest.TestCase):
    def test_scrubs_and_migrates_without_leaking_values(self):
        import remediate_legacy_mcp as rlm

        sample_config = {
            "mcpServers": {
                "openai-server": {
                    "command": "npx",
                    "args": ["-y", "openai-mcp"],
                    "env": {
                        "OPENAI_API_KEY": "sk-proj-testvalue1234567890abcdef",
                        "NON_SECRET_MODE": "production",
                    },
                },
                "tavily-remote": {
                    "url": "https://mcp.tavily.com/mcp/?tavilyApiKey=tvly-testsecret9876543210"
                },
            }
        }

        stored = {}

        def fake_set(service, key, val):
            stored[(service, key)] = val

        def fake_get(service, key):
            return stored.get((service, key))

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            legacy_file = tmp_path / "mcp_config.json"
            legacy_file.write_text(json.dumps(sample_config, indent=2), encoding="utf-8")

            with mock.patch.object(rlm, "store_in_vault", side_effect=fake_set), mock.patch.object(
                rlm, "read_from_vault", side_effect=fake_get
            ):
                report = rlm.remediate_config_file(legacy_file, service="antigravity-mcp")

            # Original plaintext file must be unlinked
            self.assertFalse(legacy_file.exists())

            # Redacted archive must exist and contain zero raw secrets
            redacted_path = tmp_path / "mcp_config.json.deprecated-redacted"
            self.assertTrue(redacted_path.is_file())
            redacted_text = redacted_path.read_text(encoding="utf-8")
            self.assertNotIn("sk-proj-testvalue1234567890abcdef", redacted_text)
            self.assertNotIn("tvly-testsecret9876543210", redacted_text)
            self.assertIn("__REDACTED_IN_WINVAULT__", redacted_text)

            # Report must contain key names and sha256 prefixes, never raw values
            report_json = json.dumps(report)
            self.assertNotIn("sk-proj-testvalue1234567890abcdef", report_json)
            self.assertNotIn("tvly-testsecret9876543210", report_json)
            key_names = {entry["key_name"] for entry in report["migrated_keys"]}
            self.assertEqual(key_names, {"OPENAI_API_KEY", "tavilyApiKey"})


if __name__ == "__main__":
    unittest.main()
