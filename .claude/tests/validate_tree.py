"""Claude harness tree validator (read-only).

Validates the invariants of the Claude Code SOP tree (root CLAUDE.md plus
the .claude/ directory) per the adjudicated implementation plan: INV-1
frontmatter spec, INV-2 JSON integrity, INV-3 hook references, INV-4/5
CLAUDE.md cross-references, INV-6 encoding, INV-7 edge-cases companions,
INV-8 vocabulary hygiene, INV-9 root-anchor integrity.

Deployment note: junction/symlink-adopted copies of .claude/ intentionally
hard-fail (INV-9). When the validator's own path resolves into a different
tree than it was invoked from, the root is untrusted and every downstream
result would be meaningless, so it prints one diagnostic and exits 1.

Exit code 0 when all invariants hold; 1 otherwise, one violation per line.
Stdlib only; runnable from any cwd; never writes.
"""
import json
import os
import re
import sys
from pathlib import Path

# --------------------------------------------------------------------------
# CONSTANTS
# --------------------------------------------------------------------------

# Forbidden Antigravity vocabulary, assembled from fragments so this file's
# own bytes never contain the contraband forms (split-literal invariant).
FORBIDDEN_TOKENS = (
    "grep_" + "search",
    "view_" + "file",
    "invoke_" + "subagent",
    "define_" + "subagent",
    "manage_" + "subagents",
    "manage_" + "task",
    "moma_" + "search",
)

SCAN_EXTENSIONS = {".md", ".json", ".ps1", ".py"}
INV8_EXCLUDED_RELPATHS = {".claude/settings.local.json"}
INV8_EXCLUDED_DIRS = {"tests"}

PIPELINE_HEADING = "## Stage 0-4 Pipeline"
RULES_BULLET_RE = re.compile(r"^- \*\*([a-z-]+)\*\* — ", re.MULTILINE)
BACKTICK_RE = re.compile(r"`([^`]+)`")
NAME_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
XML_TAG_RE = re.compile(r"<\s*[A-Za-z/!][^>]*>")
FM_LINE_RE = re.compile(r"([a-z][a-z0-9_-]*): (.*)")
HOOK_CANDIDATE_RE = re.compile(r"\$CLAUDE_PROJECT_DIR/([^\"\s]+)")
HOOK_REF_GATE_RE = re.compile(r"\.claude/hooks/[A-Za-z0-9][A-Za-z0-9._-]*")
DELIMITER_CELL_RE = re.compile(r":?-{3,}:?")


# --------------------------------------------------------------------------
# PURE PARSERS (no I/O)
# --------------------------------------------------------------------------

def bom_kind(data):
    """Return a description of a leading BOM, or None."""
    if data.startswith(b"\xef\xbb\xbf"):
        return "utf-8 BOM"
    if data.startswith(b"\xff\xfe"):
        return "utf-16 LE BOM"
    if data.startswith(b"\xfe\xff"):
        return "utf-16 BE BOM"
    return None


def has_nul(data):
    """NUL bytes mark BOM-less UTF-16 masquerading as UTF-8 (gate C)."""
    return b"\x00" in data


def parse_frontmatter(data, label):
    """Parse a SKILL.md byte payload. Returns (mapping_or_None, violations)."""
    violations = []
    kind = bom_kind(data)
    if kind:
        return None, ["%s: leading %s" % (label, kind)]
    if b"\r" in data:
        violations.append("%s: CRLF line endings (canonical form is LF)" % label)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        return None, ["%s: not strict UTF-8 (%s)" % (label, exc)]
    lines = text.split("\n")
    if not lines or lines[0].rstrip("\r") != "---":
        return None, violations + ["%s: missing opening frontmatter fence" % label]
    close = None
    for i, line in enumerate(lines[1:], start=1):
        if line.rstrip("\r") == "---":
            close = i
            break
    if close is None:
        return None, violations + ["%s: missing closing frontmatter fence" % label]
    mapping = {}
    for line in lines[1:close]:
        match = FM_LINE_RE.fullmatch(line.rstrip("\r"))
        if not match:
            violations.append("%s: malformed frontmatter line %r" % (label, line))
            continue
        key, value = match.group(1), match.group(2)
        if key in mapping:
            violations.append("%s: duplicate frontmatter key %r" % (label, key))
        mapping[key] = value
    keys = set(mapping)
    if keys != {"name", "description"}:
        violations.append(
            "%s: frontmatter keys must be exactly {name, description}, got %s"
            % (label, sorted(keys))
        )
    name = mapping.get("name", "")
    if "name" in mapping and not NAME_RE.fullmatch(name):
        violations.append("%s: invalid name %r" % (label, name))
    desc = mapping.get("description", "")
    if "description" in mapping:
        if not desc:
            violations.append("%s: empty description" % label)
        if len(desc) > 1024:
            violations.append("%s: description exceeds 1024 chars" % label)
        if XML_TAG_RE.search(desc):
            violations.append("%s: description contains an XML tag" % label)
    return mapping, violations


def extract_pipeline_skills(text):
    """Extract skill names from the pipeline table.

    Returns (names, row_violations). The region's first row (header) and
    delimiter rows are exempt; every other row must yield exactly one
    backticked token from column 2 (Stage 3 amendment: gate G).
    """
    names, row_violations = [], []
    lines = text.split("\n")
    try:
        start = next(
            i for i, line in enumerate(lines) if line.strip() == PIPELINE_HEADING
        )
    except StopIteration:
        return [], []
    rows = []
    for line in lines[start + 1:]:
        if line.startswith("|"):
            rows.append(line)
        elif rows:
            break
    for index, row in enumerate(rows):
        cells = [c.strip() for c in row.split("|")]
        if index == 0:
            continue  # header row exempt
        if len(cells) > 1 and all(
            DELIMITER_CELL_RE.fullmatch(c) for c in cells[1:-1] if c
        ):
            continue  # delimiter row exempt
        column_two = cells[2] if len(cells) > 2 else ""
        found = BACKTICK_RE.findall(column_two)
        if len(found) == 1:
            names.append(found[0])
        else:
            row_violations.append(
                "pipeline table row %r must contain exactly one backticked "
                "skill name in column 2" % row
            )
    return names, row_violations


def extract_rules_modules(text):
    """Extract rules-module stems from the CLAUDE.md pointer bullets."""
    return RULES_BULLET_RE.findall(text)


def scan_tokens(text):
    """Return forbidden tokens present in text (word-boundary matching)."""
    found = []
    for token in FORBIDDEN_TOKENS:
        if re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(token), text):
            found.append(token)
    return found


def extract_hook_refs(command):
    """Extract gated .claude/hooks references from one hook command string.

    Candidates failing the untrusted-name gate (traversal, odd charset) are
    dropped; the caller treats a command with zero gated refs as a violation.
    """
    refs = []
    for candidate in HOOK_CANDIDATE_RE.findall(command):
        if HOOK_REF_GATE_RE.fullmatch(candidate):
            refs.append(candidate)
    return refs


# --------------------------------------------------------------------------
# CHECKS (each: root -> list of violation strings)
# --------------------------------------------------------------------------

def _rel(root, path):
    try:
        return str(Path(path).relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path)


def check_inv9_junction(root):
    """Root-anchor integrity: refuse junction/symlink deployments (gate E)."""
    violations = []
    here = Path(__file__)
    absolute_root = os.path.normcase(str(here.absolute().parents[2]))
    resolved_root = os.path.normcase(str(here.resolve().parents[2]))
    if absolute_root != resolved_root:
        violations.append(
            "INV-9: junction/symlink deployment detected (invoked under %s "
            "but resolving into %s); junction-adopted trees intentionally "
            "hard-fail — run the validator in the source repository"
            % (absolute_root, resolved_root)
        )
    if not (root / "CLAUDE.md").is_file() or not (root / ".claude").is_dir():
        violations.append(
            "INV-9: repository root %s lacks CLAUDE.md or .claude/ — refusing "
            "to guess a root" % root
        )
    return violations


def check_inv1_frontmatter(root):
    violations = []
    for skill_file in sorted((root / ".claude" / "skills").glob("*/SKILL.md")):
        label = _rel(root, skill_file)
        mapping, errors = parse_frontmatter(skill_file.read_bytes(), label)
        violations.extend("INV-1: %s" % e for e in errors)
        if mapping and mapping.get("name", skill_file.parent.name) != skill_file.parent.name:
            violations.append(
                "INV-1: %s: name %r does not match directory %r"
                % (label, mapping["name"], skill_file.parent.name)
            )
    return violations


def _load_json(path):
    def reject_duplicates(pairs):
        seen = {}
        for key, value in pairs:
            if key in seen:
                raise ValueError("duplicate key %r" % key)
            seen[key] = value
        return seen

    return json.loads(path.read_bytes().decode("utf-8"), object_pairs_hook=reject_duplicates)


def check_inv2_json(root):
    violations = []
    required = (root / ".claude" / "settings.json", root / ".mcp.json")
    for path in required:
        label = _rel(root, path)
        if not path.is_file():
            violations.append("INV-2: %s: missing" % label)
            continue
        try:
            _load_json(path)
        except (ValueError, UnicodeDecodeError) as exc:
            violations.append("INV-2: %s: %s" % (label, exc))
    local = root / ".claude" / "settings.local.json"
    if local.is_file():
        try:
            _load_json(local)
        except (ValueError, UnicodeDecodeError) as exc:
            violations.append(
                "INV-2: %s: machine-local file unparseable (%s)"
                % (_rel(root, local), exc)
            )
    return violations


def check_inv3_hooks(root):
    violations = []
    settings = root / ".claude" / "settings.json"
    try:
        config = _load_json(settings)
    except (OSError, ValueError, UnicodeDecodeError):
        return ["INV-3: %s unparseable; hook references unverifiable"
                % _rel(root, settings)]
    refs = set()
    for entries in (config.get("hooks") or {}).values():
        for entry in entries:
            for hook in entry.get("hooks", []):
                command = hook.get("command", "")
                gated = extract_hook_refs(command)
                if "$CLAUDE_PROJECT_DIR" in command and not gated:
                    violations.append(
                        "INV-3: hook command %r contains no gate-passing "
                        ".claude/hooks reference" % command
                    )
                refs.update(gated)
    hooks_dir = (root / ".claude" / "hooks").resolve()
    for ref in sorted(refs):
        target = root / ref
        if not target.is_file():
            violations.append("INV-3: %s: referenced hook missing" % ref)
        elif not str(target.resolve()).startswith(str(hooks_dir)):
            violations.append("INV-3: %s: resolves outside .claude/hooks" % ref)
    return violations


def check_inv4_pipeline_table(root):
    violations = []
    text = (root / "CLAUDE.md").read_bytes().decode("utf-8", errors="replace")
    names, row_violations = extract_pipeline_skills(text)
    violations.extend("INV-4: %s" % v for v in row_violations)
    if not names:
        violations.append("INV-4: pipeline table yielded zero data rows")
    for name in names:
        if not (root / ".claude" / "skills" / name / "SKILL.md").is_file():
            violations.append(
                "INV-4: pipeline table names %r but "
                ".claude/skills/%s/SKILL.md is missing" % (name, name)
            )
    return violations


def check_inv5_rules_modules(root):
    violations = []
    text = (root / "CLAUDE.md").read_bytes().decode("utf-8", errors="replace")
    stems = extract_rules_modules(text)
    if not stems:
        violations.append("INV-5: rules pointer list yielded zero modules")
    for stem in stems:
        if not (root / ".claude" / "rules" / (stem + ".md")).is_file():
            violations.append(
                "INV-5: CLAUDE.md points at rules module %r but "
                ".claude/rules/%s.md is missing" % (stem, stem)
            )
    return violations


def check_inv6_encoding(root):
    violations = []
    targets = [
        root / "CLAUDE.md",
        root / ".claude" / "settings.json",
        root / ".mcp.json",
        root / ".claude" / "telemetry" / "agentic_telemetry.md",
    ]
    targets.extend(sorted((root / ".claude" / "hooks").glob("*.ps1")))
    for path in targets:
        label = _rel(root, path)
        if not path.is_file():
            violations.append("INV-6: %s: missing" % label)
            continue
        data = path.read_bytes()
        kind = bom_kind(data)
        if kind:
            violations.append("INV-6: %s: leading %s" % (label, kind))
        if has_nul(data):
            violations.append(
                "INV-6: %s: NUL bytes (BOM-less UTF-16?)" % label
            )
        try:
            data.decode("utf-8")
        except UnicodeDecodeError as exc:
            violations.append("INV-6: %s: not strict UTF-8 (%s)" % (label, exc))
        if path.suffix == ".ps1":
            try:
                data.decode("ascii")
            except UnicodeDecodeError:
                violations.append(
                    "INV-6: %s: hook scripts declare ASCII-only and must "
                    "stay pure ASCII" % label
                )
    return violations


def check_inv7_edge_cases(root):
    violations = []
    suffix = "-edge-cases.md"
    for path in sorted((root / ".claude").rglob("*" + suffix)):
        label = _rel(root, path)
        stem = path.name[: -len(suffix)]
        if stem != path.parent.name:
            violations.append(
                "INV-7: %s: prefix %r must equal parent directory %r"
                % (label, stem, path.parent.name)
            )
        if not (path.parent / "SKILL.md").is_file():
            violations.append("INV-7: %s: no sibling SKILL.md" % label)
    return violations


def check_inv8_vocabulary(root):
    violations = []
    targets = [root / "CLAUDE.md"]
    for dirpath, dirnames, filenames in os.walk(root / ".claude"):
        dirnames[:] = [d for d in dirnames if d not in INV8_EXCLUDED_DIRS]
        for filename in filenames:
            targets.append(Path(dirpath) / filename)
    for path in sorted(targets):
        label = _rel(root, path)
        if label in INV8_EXCLUDED_RELPATHS or path.suffix not in SCAN_EXTENSIONS:
            continue
        text = path.read_bytes().decode("utf-8", errors="replace")
        for token in scan_tokens(text):
            violations.append(
                "INV-8: %s: forbidden vocabulary %r" % (label, token)
            )
    return violations


CHECKS = (
    ("INV-9", check_inv9_junction),
    ("INV-1", check_inv1_frontmatter),
    ("INV-2", check_inv2_json),
    ("INV-3", check_inv3_hooks),
    ("INV-4", check_inv4_pipeline_table),
    ("INV-5", check_inv5_rules_modules),
    ("INV-6", check_inv6_encoding),
    ("INV-7", check_inv7_edge_cases),
    ("INV-8", check_inv8_vocabulary),
)


def run_checks(root, checks=CHECKS):
    """Run checks fail-closed; INV-9 firing short-circuits the rest."""
    violations = []
    for inv_id, check in checks:
        try:
            found = check(root)
        except Exception as exc:  # fail-closed: a crashed check never passes
            found = ["INTERNAL-ERROR (%s): %r" % (inv_id, exc)]
        if inv_id == "INV-9" and found:
            return sorted(found)
        violations.extend(found)
    return sorted(violations)


def main():
    root = Path(__file__).resolve().parents[2]
    violations = run_checks(root)
    for line in violations:
        print(line)
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
