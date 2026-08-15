"""Tests for validate_tree.py (Claude harness tree validator).

Three tiers per the adjudicated implementation plan: PureParsers (inline
literals, no disk), LiveTree (the real repository is its own fixture), and
Meta (self-audit, coverage, fail-closed injection).
"""
import ast
import subprocess
import sys
import unittest
from pathlib import Path

import validate_tree as vt

REPO_ROOT = Path(__file__).resolve().parents[2]

# Forbidden tokens assembled from fragments at runtime so this file's bytes
# never contain the contraband forms (split-literal invariant).
TOKEN_GREP = "grep_" + "search"
TOKEN_VIEW = "view_" + "file"
AGENTS_DIR = "." + "agents"

FM_VALID = b"---\nname: style-python\ndescription: A linter.\n---\nbody\n"


class PureParsers(unittest.TestCase):
    def fm_violations(self, data):
        _, violations = vt.parse_frontmatter(data, "x/SKILL.md")
        return violations

    def test_frontmatter_valid(self):
        fm, violations = vt.parse_frontmatter(FM_VALID, "x/SKILL.md")
        self.assertEqual(violations, [])
        self.assertEqual(fm, {"name": "style-python", "description": "A linter."})

    def test_frontmatter_crlf_is_violation(self):
        data = FM_VALID.replace(b"\n", b"\r\n")
        self.assertTrue(self.fm_violations(data))

    def test_frontmatter_bom_is_violation(self):
        self.assertTrue(self.fm_violations(b"\xef\xbb\xbf" + FM_VALID))

    def test_frontmatter_duplicate_key(self):
        data = b"---\nname: a\nname: b\ndescription: d\n---\n"
        self.assertTrue(self.fm_violations(data))

    def test_frontmatter_unknown_key(self):
        data = b"---\nname: a\ndescription: d\ntools: Read\n---\n"
        self.assertTrue(self.fm_violations(data))

    def test_frontmatter_missing_fence(self):
        self.assertTrue(self.fm_violations(b"name: a\ndescription: d\n"))

    def test_name_65_chars_rejected(self):
        name = "a" * 65
        data = ("---\nname: %s\ndescription: d\n---\n" % name).encode()
        self.assertTrue(self.fm_violations(data))

    def test_name_uppercase_rejected(self):
        data = b"---\nname: Bad-Name\ndescription: d\n---\n"
        self.assertTrue(self.fm_violations(data))

    def test_description_1025_chars_rejected(self):
        # Char-length semantics: 1024 chars pass, 1025 fail, measured on the
        # decoded str (em-dash is one char, three bytes).
        ok = "---\nname: a\ndescription: %s\n---\n" % ("\u2014" * 1024)
        bad = "---\nname: a\ndescription: %s\n---\n" % ("\u2014" * 1025)
        self.assertEqual(self.fm_violations(ok.encode("utf-8")), [])
        self.assertTrue(self.fm_violations(bad.encode("utf-8")))

    def test_description_xml_tag_rejected_but_math_ok(self):
        bad = b"---\nname: a\ndescription: has <tag> inside\n---\n"
        ok = b"---\nname: a\ndescription: a < b holds\n---\n"
        self.assertTrue(self.fm_violations(bad))
        self.assertEqual(self.fm_violations(ok), [])

    TABLE = (
        "## Stage 0-4 Pipeline\n\n"
        "| Stage | Skill | Trigger |\n"
        "|-------|-------|---------|\n"
        "| 0 \u2014 Comprehension | `comprehend-problem` | always |\n"
        "| 2 \u2014 Debate | `technical-debate` | `implementation_plan.md` |\n"
    )

    def test_table_extracts_column_two_only(self):
        names, row_violations = vt.extract_pipeline_skills(self.TABLE)
        self.assertEqual(names, ["comprehend-problem", "technical-debate"])
        self.assertEqual(row_violations, [])

    def test_table_header_and_delimiter_skipped(self):
        _, row_violations = vt.extract_pipeline_skills(self.TABLE)
        self.assertEqual(row_violations, [])

    def test_table_backtick_stripped_row_is_violation(self):
        damaged = self.TABLE.replace("`technical-debate`", "technical-debate")
        names, row_violations = vt.extract_pipeline_skills(damaged)
        self.assertEqual(names, ["comprehend-problem"])
        self.assertEqual(len(row_violations), 1)

    def test_table_missing_region_yields_no_names(self):
        names, _ = vt.extract_pipeline_skills("# nothing here\n")
        self.assertEqual(names, [])

    def test_rules_bullets_em_dash_only(self):
        text = "- **pipeline** \u2014 routing rules\n- **tdd** - hyphen not em dash\n"
        self.assertEqual(vt.extract_rules_modules(text), ["pipeline"])

    def test_token_scanner_hits_and_misses(self):
        self.assertTrue(vt.scan_tokens("use %s here" % TOKEN_GREP))
        self.assertFalse(vt.scan_tokens("my_%ser helper" % TOKEN_GREP))
        self.assertFalse(vt.scan_tokens("no-%s-to-live" % TOKEN_VIEW))

    def test_token_scanner_nul_blind_but_inv6_catches(self):
        utf16 = TOKEN_GREP.encode("utf-16-le")
        decoded = utf16.decode("utf-8", errors="replace")
        self.assertFalse(vt.scan_tokens(decoded))
        self.assertTrue(vt.has_nul(utf16))

    def test_bom_kind(self):
        self.assertEqual(vt.bom_kind(b"\xef\xbb\xbfabc"), "utf-8 BOM")
        self.assertEqual(vt.bom_kind(b"\xff\xfea\x00"), "utf-16 LE BOM")
        self.assertEqual(vt.bom_kind(b"\xfe\xff\x00a"), "utf-16 BE BOM")
        self.assertIsNone(vt.bom_kind(b"plain"))
        self.assertIsNone(vt.bom_kind(b""))

    def test_hook_ref_gate(self):
        good = ('powershell -NoProfile -ExecutionPolicy Bypass -File '
                '"$CLAUDE_PROJECT_DIR/.claude/hooks/brc-guard.ps1"')
        traversal = good.replace("brc-guard.ps1", "../../evil.ps1")
        self.assertEqual(vt.extract_hook_refs(good), [".claude/hooks/brc-guard.ps1"])
        self.assertEqual(vt.extract_hook_refs(traversal), [])


class LiveTree(unittest.TestCase):
    def test_every_check_clean_on_real_tree(self):
        for inv_id, check in vt.CHECKS:
            with self.subTest(inv=inv_id):
                self.assertEqual(check(REPO_ROOT), [])

    def test_exit_zero_from_foreign_cwd(self):
        script = str(Path(vt.__file__).resolve())
        result = subprocess.run(
            [sys.executable, script], cwd="C:\\", capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), "")

    def test_determinism_two_runs_identical(self):
        first = vt.run_checks(REPO_ROOT)
        second = vt.run_checks(REPO_ROOT)
        self.assertEqual(first, second)

    def test_junction_check_clean_in_real_checkout(self):
        self.assertEqual(vt.check_inv9_junction(REPO_ROOT), [])


class Meta(unittest.TestCase):
    def test_checks_tuple_covers_all_invariants(self):
        ids = {inv_id for inv_id, _ in vt.CHECKS}
        self.assertEqual(ids, {"INV-%d" % i for i in range(1, 10)})

    def test_inv9_is_first_check(self):
        self.assertEqual(vt.CHECKS[0][0], "INV-9")

    def test_validator_source_is_read_only(self):
        source = Path(vt.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = getattr(func, "attr", getattr(func, "id", ""))
                self.assertNotIn(
                    name,
                    {"write_text", "write_bytes", "remove", "unlink",
                     "rmtree", "rename", "chdir"},
                    "write-capable call %r found" % name,
                )
                if name == "open":
                    for arg in list(node.args[1:2]) + [
                        kw.value for kw in node.keywords if kw.arg == "mode"
                    ]:
                        if isinstance(arg, ast.Constant):
                            self.assertNotRegex(str(arg.value), r"[wa+]")

    def test_no_agents_literal_in_validator(self):
        source = Path(vt.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                self.assertNotIn(AGENTS_DIR, node.value)

    def test_split_literal_invariant(self):
        for path in (Path(vt.__file__), Path(__file__)):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn(TOKEN_GREP, source)
            self.assertNotIn(TOKEN_VIEW, source)

    def test_fail_closed_injection(self):
        def bomb(_root):
            raise RuntimeError("boom")

        lines = vt.run_checks(REPO_ROOT, checks=(("INV-1", bomb),))
        self.assertEqual(len(lines), 1)
        self.assertIn("INTERNAL-ERROR", lines[0])


if __name__ == "__main__":
    unittest.main()
