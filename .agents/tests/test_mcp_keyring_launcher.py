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

    def test_check_flag_reports_fingerprint_without_leaking_secret(self):
        import io
        import mcp_keyring_launcher as mkl

        vault = {("antigravity-mcp", "TEST_API_KEY"): "sk-proj-secret1234567890abcdef"}
        buf = io.StringIO()
        with mock.patch.object(
            mkl, "get_secret", side_effect=lambda s, k: vault.get((s, k))
        ), mock.patch("sys.stdout", buf):
            code_ok = mkl.main(["--check", "TEST_API_KEY"])
            code_missing = mkl.main(["--check", "MISSING_KEY"])
        out = buf.getvalue()
        self.assertEqual(code_ok, 0)
        self.assertEqual(code_missing, 1)
        self.assertIn("PRESENT (sha256:", out)
        self.assertIn("MISSING", out)
        self.assertNotIn("sk-proj-secret1234567890abcdef", out)

    def test_self_test_cli_flag(self):
        import subprocess

        script = SCRIPTS_DIR / "mcp_keyring_launcher.py"
        res = subprocess.run(
            [sys.executable, str(script), "--self-test"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_sync_global_config_checks_global_mcp_config(self):
        import sync_global_config as sgc

        with tempfile.TemporaryDirectory() as tmp:
            global_dir = Path(tmp)
            clean_mcp = {
                "mcpServers": {
                    "code-graph-context": {"command": "cgc", "args": ["mcp", "start"]}
                }
            }
            (global_dir / "mcp_config.json").write_bytes(
                (json.dumps(clean_mcp, indent=2) + "\n").encode("utf-8")
            )
            errs_clean, msgs_clean = sgc.check_global_mcp_config(REPO_ROOT, global_dir)
            self.assertEqual(errs_clean, [])
            self.assertTrue(any("mcp_config.json OK" in m for m in msgs_clean))

            dirty_mcp = {
                "mcpServers": {
                    "code-graph-context": {
                        "command": "cgc",
                        "args": ["mcp", "start"],
                        "env": {"OPENAI_API_KEY": "sk-proj-secretvalue1234567890abcdef"},
                    }
                }
            }
            (global_dir / "mcp_config.json").write_bytes(
                (json.dumps(dirty_mcp, indent=2) + "\n").encode("utf-8")
            )
            errs_dirty, _ = sgc.check_global_mcp_config(REPO_ROOT, global_dir)
            self.assertTrue(
                any("plaintext secret" in e for e in errs_dirty),
                "Expected plaintext secret error, got %r" % errs_dirty,
            )


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
