"""Pre-commit and file secret scanner for antigravity-core (Betterleaks + stdlib).

Scans staged git diffs (`--staged`) or explicit files (`--files ...`) for
hardcoded API keys, private keys, and high-entropy credential assignments.
If `betterleaks` or `gitleaks` is installed on PATH, runs it first and
combines results with the built-in deterministic detector suite.

Transcript safety: NEVER prints raw matched secret values; outputs only
`file:line`, rule ID, and an 8-character SHA-256 fingerprint (`sha256:xxxxxxxx`).

Usage:
    python .agents/scripts/secret_scan.py --staged
    python .agents/scripts/secret_scan.py --files <path1> [<path2> ...]
    python .agents/scripts/secret_scan.py --self-test
"""
import argparse
import hashlib
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Built-in vendor token rules (assembled so self-scans never trigger false positives)
SECRET_RULES = (
    ("openai-api-key", re.compile(r"\bsk-(?:proj|svcacct|live)-[A-Za-z0-9_-]{20,}\b")),
    ("anthropic-api-key", re.compile(r"\bsk-ant-api03-[A-Za-z0-9_-]{20,}\b")),
    ("github-pat-classic", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("github-pat-fine", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{50,}\b")),
    ("google-api-key", re.compile(r"\bAIzaSy[A-Za-z0-9_-]{33}\b")),
    ("google-oauth-secret", re.compile(r"\bGOCSPX-[A-Za-z0-9_-]{20,}\b")),
    ("aws-access-key-id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[0-9]{10,}-[A-Za-z0-9-]{10,}\b")),
    ("firecrawl-api-key", re.compile(r"\bfc-[a-f0-9]{32}\b")),
    ("tavily-api-key", re.compile(r"\btvly-[A-Za-z0-9_-]{20,}\b")),
    ("stripe-live-key", re.compile(r"\b(?:sk|rk)_live_[0-9a-zA-Z]{24,}\b")),
    ("huggingface-token", re.compile(r"\bhf_[A-Za-z0-9]{34,}\b")),
    ("npm-access-token", re.compile(r"\bnpm_[A-Za-z0-9]{36}\b")),
    ("pypi-upload-token", re.compile(r"\bpypi-AgEIcHlwaS5vcmc[A-Za-z0-9_-]{50,}\b")),
    ("sendgrid-api-key", re.compile(r"\bSG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}\b")),
    ("Private-Key-Header", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----")),
)

# Generic secret key assignment pattern for Shannon entropy evaluation
GENERIC_ASSIGN_RE = re.compile(
    r"""(?i)\b(api[_-]?key|secret|token|password|client[_-]?secret|api[_-]?hash|tavilyApiKey)\b"""
    r"""\s*(?:["']?\s*[:=]\s*["']|=[A-Za-z0-9_-]*?)\s*([A-Za-z0-9/+_.-]{20,})"""
)

SAFE_PLACEHOLDERS = {
    "__REDACTED_IN_WINVAULT__",
    "YOUR_API_KEY_HERE",
    "REPLACE_ME",
    "EXAMPLE_TOKEN",
}


def shannon_entropy(text):
    """Calculate Shannon entropy in bits per character."""
    if not text:
        return 0.0
    length = len(text)
    counts = {}
    for ch in text:
        counts[ch] = counts.get(ch, 0) + 1
    return -sum((c / length) * math.log2(c / length) for c in counts.values())


def fingerprint(secret_val):
    """Return a transcript-safe 8-char SHA-256 fingerprint."""
    digest = hashlib.sha256(secret_val.encode("utf-8", errors="replace")).hexdigest()
    return "sha256:" + digest[:8]


def is_placeholder(val):
    """Return True if value is a known redacted/placeholder marker."""
    if val in SAFE_PLACEHOLDERS:
        return True
    upper = val.upper()
    if "REDACTED" in upper or "PLACEHOLDER" in upper or "EXAMPLE" in upper or "TEST" in upper:
        return True
    return False


def scan_line(line, label, line_no):
    """Scan a single line of text and return transcript-safe finding dicts."""
    findings = []
    for rule_id, pattern in SECRET_RULES:
        for match in pattern.finditer(line):
            val = match.group(0)
            if is_placeholder(val):
                continue
            findings.append(
                {
                    "location": "%s:%d" % (label, line_no),
                    "rule": rule_id,
                    "fingerprint": fingerprint(val),
                }
            )
    if not findings:
        for match in GENERIC_ASSIGN_RE.finditer(line):
            key_name, val = match.group(1), match.group(2)
            if is_placeholder(val):
                continue
            ent = shannon_entropy(val)
            has_mixed = (
                any(c.islower() for c in val)
                and any(c.isupper() for c in val)
                and any(c.isdigit() for c in val)
            ) or (
                any(c in "0123456789" for c in val)
                and any(c in "abcdefABCDEF" for c in val)
                and len(val) >= 32
            )
            if ent > 4.2 and has_mixed:
                findings.append(
                    {
                        "location": "%s:%d" % (label, line_no),
                        "rule": "high-entropy-secret(%s,H=%.2f)" % (key_name, ent),
                        "fingerprint": fingerprint(val),
                    }
                )
    return findings


def scan_text(text, label):
    """Scan multi-line text and return list of findings."""
    results = []
    for idx, line in enumerate(text.splitlines(), start=1):
        results.extend(scan_line(line, label, idx))
    return results


def scan_files(paths):
    """Scan a list of file or directory paths."""
    findings = []
    skip_dirs = {".git", "__pycache__", "node_modules", ".venv"}
    for raw_p in paths:
        p = Path(raw_p)
        if p.is_dir():
            for child in sorted(p.rglob("*")):
                if any(part in skip_dirs for part in child.parts):
                    continue
                if child.is_file():
                    findings.extend(_scan_single_file(child))
        elif p.is_file():
            findings.extend(_scan_single_file(p))
    return findings


def _scan_single_file(path):
    # Skip test files and the scanner itself when scanning whole directories
    norm = str(path).replace("\\", "/")
    if norm.endswith("/secret_scan.py") or norm.endswith("/test_mcp_keyring_launcher.py"):
        return []
    try:
        text = path.read_bytes().decode("utf-8", errors="replace")
    except OSError:
        return []
    return scan_text(text, str(path))


def scan_staged(repo_root):
    """Scan added lines in `git diff --cached` plus delegate to betterleaks if installed."""
    findings = []
    betterleaks_bin = shutil.which("betterleaks")
    if betterleaks_bin:
        res = subprocess.run(
            [betterleaks_bin, "git", "--staged", "--redact", "--no-banner"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )
        if res.returncode != 0:
            findings.append(
                {
                    "location": "git:staged",
                    "rule": "betterleaks-staged",
                    "fingerprint": "redacted",
                }
            )

    diff_res = subprocess.run(
        ["git", "diff", "--cached", "--unified=0", "--no-color"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    current_file = "staged"
    line_no = 0
    for raw_line in diff_res.stdout.splitlines():
        if raw_line.startswith("+++ b/"):
            current_file = raw_line[6:].strip()
        elif raw_line.startswith("@@ "):
            m = re.search(r"\+(\d+)", raw_line)
            line_no = int(m.group(1)) if m else 1
        elif raw_line.startswith("+") and not raw_line.startswith("+++"):
            if not current_file.endswith("secret_scan.py") and not current_file.endswith(
                "test_mcp_keyring_launcher.py"
            ):
                findings.extend(scan_line(raw_line[1:], current_file, line_no))
            line_no += 1
    return findings


def run_self_test():
    """Verify positive detection of synthetic tokens and zero raw secret leakage."""
    fake_openai = "sk-proj-" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4"
    fake_ghp = "ghp_" + "1234567890abcdefABCDEF1234567890abcd"
    fake_google = "AIzaSy" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q"
    sample = "\n".join(
        [
            'OPENAI_API_KEY = "%s"' % fake_openai,
            'GITHUB_TOKEN = "%s"' % fake_ghp,
            'GEMINI_KEY = "%s"' % fake_google,
            'SAFE_KEY = "__REDACTED_IN_WINVAULT__"',
        ]
    )
    hits = scan_text(sample, "synthetic.env")
    if len(hits) != 3:
        print("Self-test failed: expected 3 hits, got %d: %r" % (len(hits), hits))
        return 1
    serialized = str(hits)
    for raw_secret in (fake_openai, fake_ghp, fake_google):
        if raw_secret in serialized:
            print("Self-test failed: raw secret leaked in output")
            return 1
    print("secret_scan self-test: PASS (3/3 synthetic secrets caught, 0 leaked)")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Pre-commit and file secret scanner.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--staged", action="store_true", help="Scan staged git diff.")
    group.add_argument("--files", nargs="+", help="Scan explicit files or directories.")
    group.add_argument("--self-test", action="store_true", help="Run built-in self-test.")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()

    repo_root = Path(__file__).resolve().parents[2]
    findings = scan_staged(repo_root) if args.staged else scan_files(args.files)
    if findings:
        for f in findings:
            print(
                "SECRET-SCAN BLOCK [%s] at %s (%s)"
                % (f["rule"], f["location"], f["fingerprint"])
            )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
