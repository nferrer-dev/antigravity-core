"""Antigravity (.agents/) harness tree validator (read-only).

Validates the invariants of the Antigravity SOP tree (.agents/ directory)
per the adjudicated implementation plan:
- INV-1: SKILL.md frontmatter spec and <= 500 line cap
- INV-2: JSON integrity (.agents/hooks.json, .agents/mcp_config.json) and concrete path resolution
- INV-3: Antigravity hook contract (Grouped PreToolUse, Flat Stop, script existence, timeout sum <= 15s)
- INV-4: Skill cross-references in .agents/AGENTS.md resolve to .agents/skills/<name>/SKILL.md
- INV-5: PowerShell hook script safety (strict 7-bit ASCII, zero Invoke-Expression)
- INV-6: Encoding & control-byte hygiene (UTF-8 no BOM, LF line endings, zero stray control bytes)
- INV-7: Edge-cases companion file structure (*-edge-cases.md)
- INV-8: Vocabulary hygiene (zero stale Claude-only or deprecated tool identifiers)
- INV-9: Root-anchor integrity (repo-self-contained junction check)

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

# Forbidden Claude-only and deprecated tool vocabulary, assembled from
# fragments so this file's own bytes never contain the contraband forms
# (split-literal invariant).
FORBIDDEN_TOKENS = (
    "CLAUDE" + ".md",
    ".claude" + "/",
    "Subagent" + "Stop",
    "multi_replace_" + "file_content",
    "list_" + "dir",
)

FORBIDDEN_PS1_CALL = "Invoke-" + "Expression"

SCAN_EXTENSIONS = {".md", ".json", ".ps1", ".py"}
INV8_EXCLUDED_DIRS = {"tests", "__pycache__"}

NAME_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
XML_TAG_RE = re.compile(r"<\s*[A-Za-z/!][^>]*>")
FM_LINE_RE = re.compile(r"([a-z][a-z0-9_-]*):(?:\s+(.*))?")
HOOK_SCRIPT_RE = re.compile(r"(?:\./hooks|\.agents/hooks)/([A-Za-z0-9._-]+\.ps1)")
CONCRETE_PATH_RE = re.compile(
    r"(?:^|[\s(`\"'])(?:(\.agents/[A-Za-z0-9._/-]+)|file:///C:/Projects/antigravity-core/(\.agents/[A-Za-z0-9._/-]+))"
)

GROUPED_HOOK_EVENTS = {"PreToolUse", "PostToolUse"}
FLAT_HOOK_EVENTS = {"PreInvocation", "PostInvocation", "Stop"}
VALID_HOOK_EVENTS = GROUPED_HOOK_EVENTS | FLAT_HOOK_EVENTS

FORBIDDEN_CONTROL_BYTES = (
    set(range(0x00, 0x09)) | {0x0B, 0x0C, 0x0D} | set(range(0x0E, 0x20))
)

EXPECTED_AGENTS_SKILLS = (
    "comprehend-problem",
    "brainstorm-solutions",
    "technical-debate",
    "debate",
    "design-validate",
    "iterative-implement",
    "skill-evolve",
    "security-auditor",
    "style-python",
    "style-go",
    "style-js",
    "style-cpp",
    "style-java",
    "style-rust",
    "markdown-style-expert",
)

ALLOWED_PLUGIN_FIELDS = {
    "name",
    "description",
    "logo",
    "suggestedPrompts",
    "displayName",
    "version",
    "disabled",
}

INVISIBLE_UNICODE_RANGES = (
    (0x200B, 0x200D),
    (0x202A, 0x202E),
    (0x2060, 0x2060),
    (0x2066, 0x2069),
    (0xFEFF, 0xFEFF),
    (0xE0000, 0xE007F),
)

SKILL_SECURITY_PATTERNS = (
    (
        "prompt-injection override directive",
        re.compile(
            r"\b(?:ignore|disregard)\s+(?:all\s+|any\s+)?(?:previous|prior|above|system)\s+"
            r"(?:instructions|prompts|rules|directives)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "outbound secret exfiltration command",
        re.compile(
            r"\b(?:curl|wget|Invoke-WebRequest|Invoke-RestMethod|iwr|irm)\b[^\n]*"
            r"(?:\$\{?[A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD)|\.env\b|id_rsa)",
            re.IGNORECASE,
        ),
    ),
    (
        "encoded shell payload in skill",
        re.compile(
            r"\b(?:powershell|pwsh)\b[^\n]*\s-(?:e|enc|encodedcommand)\s+[A-Za-z0-9+/=]{16,}",
            re.IGNORECASE,
        ),
    ),
)


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
    """Return True if data contains NUL bytes."""
    return b"\x00" in data


def has_forbidden_control_bytes(data):
    """Return True if data contains NUL, bare CR, form-feed, or other control bytes."""
    return any(b in FORBIDDEN_CONTROL_BYTES for b in data)


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
    if len(lines) > 500:
        violations.append("%s: exceeds 500-line cap (%d lines)" % (label, len(lines)))
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
    in_metadata = False
    for line in lines[1:close]:
        stripped = line.rstrip("\r")
        if in_metadata and stripped.startswith("  "):
            continue
        in_metadata = False
        match = FM_LINE_RE.fullmatch(stripped)
        if not match:
            violations.append("%s: malformed frontmatter line %r" % (label, line))
            continue
        key, value = match.group(1), (match.group(2) or "")
        if key == "metadata" and value == "":
            in_metadata = True
            continue
        if key in mapping:
            violations.append("%s: duplicate frontmatter key %r" % (label, key))
        mapping[key] = value
    keys = set(mapping)
    if keys != {"name", "description"}:
        violations.append(
            "%s: frontmatter keys must be {name, description}, got %s"
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


def scan_tokens(text):
    """Return forbidden tokens present in text."""
    found = []
    for token in FORBIDDEN_TOKENS:
        if token.endswith("/"):
            if token in text:
                found.append(token)
        elif re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(token), text):
            found.append(token)
    return found


def extract_concrete_repo_paths(text):
    """Extract concrete .agents/... repo paths, excluding template placeholders."""
    results = []
    for match in CONCRETE_PATH_RE.finditer(text):
        candidate = match.group(1) or match.group(2)
        if not candidate:
            continue
        candidate = candidate.split("#")[0].rstrip(".,;:)")
        if "<" in candidate or ">" in candidate or "[" in candidate or "]" in candidate:
            continue
        if candidate.endswith("/"):
            continue
        # Skip generic prose references like .agents/skills or .agents/hooks
        if candidate in {".agents/skills", ".agents/hooks", ".agents/tests", ".agents/scripts"}:
            continue
        results.append(candidate)
    return sorted(set(results))


def scan_skill_security(text, label):
    """Scan skill markdown text for invisible Unicode smuggling and injection."""
    violations = []
    for idx, ch in enumerate(text):
        cp = ord(ch)
        for lo, hi in INVISIBLE_UNICODE_RANGES:
            if lo <= cp <= hi:
                violations.append(
                    "%s: invisible Unicode codepoint U+%04X at char %d"
                    % (label, cp, idx)
                )
                break
    for desc, pattern in SKILL_SECURITY_PATTERNS:
        if pattern.search(text):
            violations.append("%s: suspicious %s" % (label, desc))
    return violations


# --------------------------------------------------------------------------
# CHECKS (each: root -> list of violation strings)
# --------------------------------------------------------------------------

def _rel(root, path):
    try:
        return str(Path(path).relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path)


def _load_json(path):
    def reject_duplicates(pairs):
        seen = {}
        for key, value in pairs:
            if key in seen:
                raise ValueError("duplicate key %r" % key)
            seen[key] = value
        return seen

    return json.loads(path.read_bytes().decode("utf-8"), object_pairs_hook=reject_duplicates)


def check_inv9_junction(root):
    """Root-anchor integrity: repo-self-contained junction check."""
    violations = []
    here = Path(__file__)
    absolute_root = os.path.normcase(str(here.absolute().parents[2]))
    resolved_root = os.path.normcase(str(here.resolve().parents[2]))
    if absolute_root != resolved_root:
        violations.append(
            "INV-9: junction/symlink deployment detected (invoked under %s "
            "but resolving into %s); run the validator in the source repository"
            % (absolute_root, resolved_root)
        )
    if not (root / ".agents" / "AGENTS.md").is_file() or not (root / ".agents").is_dir():
        violations.append(
            "INV-9: repository root %s lacks .agents/AGENTS.md or .agents/" % root
        )
    return violations


def check_inv1_frontmatter(root):
    violations = []
    for skill_file in sorted((root / ".agents" / "skills").glob("*/SKILL.md")):
        label = _rel(root, skill_file)
        mapping, errors = parse_frontmatter(skill_file.read_bytes(), label)
        violations.extend("INV-1: %s" % e for e in errors)
        if mapping and mapping.get("name", skill_file.parent.name) != skill_file.parent.name:
            violations.append(
                "INV-1: %s: name %r does not match directory %r"
                % (label, mapping["name"], skill_file.parent.name)
            )
    return violations


def check_inv2_json_and_paths(root):
    violations = []
    required_json = (
        root / ".agents" / "hooks.json",
        root / ".agents" / "mcp_config.json",
        root / ".agents" / "plugins" / "antigravity-core" / "plugin.json",
    )
    for path in required_json:
        label = _rel(root, path)
        if not path.is_file():
            violations.append("INV-2: %s: missing" % label)
            continue
        try:
            data = _load_json(path)
            if path.name == "mcp_config.json":
                servers = data.get("mcpServers", {})
                if "chiasmus" in servers:
                    violations.append(
                        "INV-2: %s: contains broken 'chiasmus' MCP server entry" % label
                    )
            elif path.name == "plugin.json":
                unknown = sorted(set(data.keys()) - ALLOWED_PLUGIN_FIELDS)
                if unknown:
                    violations.append(
                        "INV-2: %s: unsupported top-level fields %s" % (label, unknown)
                    )
                if data.get("disabled") is not True:
                    violations.append(
                        "INV-2: %s: must set disabled=true in source repo checkout"
                        % label
                    )
        except (ValueError, UnicodeDecodeError) as exc:
            violations.append("INV-2: %s: %s" % (label, exc))

    md_targets = [root / ".agents" / "AGENTS.md"]
    md_targets.extend(sorted((root / ".agents" / "skills").rglob("*.md")))
    for md_path in md_targets:
        if not md_path.is_file():
            continue
        label = _rel(root, md_path)
        text = md_path.read_bytes().decode("utf-8", errors="replace")
        for ref_rel in extract_concrete_repo_paths(text):
            target = root / ref_rel
            if not target.exists():
                violations.append(
                    "INV-2: %s: referenced path %r does not exist" % (label, ref_rel)
                )
    return violations


def check_inv3_hooks(root):
    violations = []
    hooks_json = root / ".agents" / "hooks.json"
    label = _rel(root, hooks_json)
    if not hooks_json.is_file():
        return ["INV-3: %s: missing" % label]
    try:
        config = _load_json(hooks_json)
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        return ["INV-3: %s unparseable (%s)" % (label, exc)]

    total_timeout = 0
    referenced_scripts = set()
    for group_name, event_map in config.items():
        if not isinstance(event_map, dict):
            violations.append("INV-3: %s: hook group %r must be an object" % (label, group_name))
            continue
        for event_name, entries in event_map.items():
            if event_name not in VALID_HOOK_EVENTS:
                violations.append(
                    "INV-3: %s: invalid Antigravity hook event %r" % (label, event_name)
                )
                continue
            if not isinstance(entries, list) or not entries:
                violations.append(
                    "INV-3: %s: event %r must map to a non-empty list" % (label, event_name)
                )
                continue
            if event_name in GROUPED_HOOK_EVENTS:
                for entry in entries:
                    if "hooks" not in entry or not isinstance(entry["hooks"], list):
                        violations.append(
                            "INV-3: %s: Grouped event %r entry missing 'hooks' array"
                            % (label, event_name)
                        )
                        continue
                    for h in entry["hooks"]:
                        total_timeout += int(h.get("timeout", 0))
                        cmd = h.get("command", "")
                        if '"' in cmd:
                            violations.append(
                                "INV-3: %s: hook command %r must not contain inner double quotes (use -File ./hooks/<script>.ps1)"
                                % (label, cmd)
                            )
                        for s_name in HOOK_SCRIPT_RE.findall(cmd):
                            referenced_scripts.add(s_name)
            elif event_name in FLAT_HOOK_EVENTS:
                for h in entries:
                    if "matcher" in h or "hooks" in h:
                        violations.append(
                            "INV-3: %s: Flat event %r must not contain 'matcher' or 'hooks' wrapper"
                            % (label, event_name)
                        )
                    total_timeout += int(h.get("timeout", 0))
                    cmd = h.get("command", "")
                    if '"' in cmd:
                        violations.append(
                            "INV-3: %s: hook command %r must not contain inner double quotes (use -File ./hooks/<script>.ps1)"
                            % (label, cmd)
                        )
                    for s_name in HOOK_SCRIPT_RE.findall(cmd):
                        referenced_scripts.add(s_name)

    if total_timeout > 15:
        violations.append(
            "INV-3: %s: total hook timeout %ds exceeds 15s cap" % (label, total_timeout)
        )
    if not referenced_scripts:
        violations.append("INV-3: %s: no hook scripts referenced" % label)
    for script_name in sorted(referenced_scripts):
        target = root / ".agents" / "hooks" / script_name
        if not target.is_file():
            violations.append(
                "INV-3: .agents/hooks/%s: referenced hook script missing" % script_name
            )
    return violations


def check_inv4_pipeline_skills(root):
    violations = []
    agents_md = root / ".agents" / "AGENTS.md"
    if not agents_md.is_file():
        return ["INV-4: .agents/AGENTS.md missing"]
    text = agents_md.read_bytes().decode("utf-8", errors="replace").lower()
    for skill_name in EXPECTED_AGENTS_SKILLS:
        spaced = skill_name.replace("-", " ")
        if (skill_name not in text) and (spaced not in text):
            violations.append(
                "INV-4: .agents/AGENTS.md missing reference to core skill %r" % skill_name
            )
        skill_path = root / ".agents" / "skills" / skill_name / "SKILL.md"
        if not skill_path.is_file():
            violations.append(
                "INV-4: .agents/skills/%s/SKILL.md is missing" % skill_name
            )
    return violations


def check_inv5_ps1_safety(root):
    violations = []
    ps1_files = sorted((root / ".agents" / "hooks").glob("*.ps1"))
    if not ps1_files:
        return ["INV-5: no .ps1 hook scripts found in .agents/hooks"]
    for path in ps1_files:
        label = _rel(root, path)
        data = path.read_bytes()
        try:
            text = data.decode("ascii")
        except UnicodeDecodeError:
            violations.append("INV-5: %s: must be strict 7-bit ASCII" % label)
            continue
        if FORBIDDEN_PS1_CALL in text:
            violations.append(
                "INV-5: %s: contains forbidden %s call" % (label, FORBIDDEN_PS1_CALL)
            )
    return violations


def check_inv6_encoding(root):
    violations = []
    for dirpath, dirnames, filenames in os.walk(root / ".agents"):
        dirnames[:] = [d for d in dirnames if d not in {"__pycache__"}]
        for filename in sorted(filenames):
            path = Path(dirpath) / filename
            if path.suffix not in SCAN_EXTENSIONS:
                continue
            label = _rel(root, path)
            data = path.read_bytes()
            kind = bom_kind(data)
            if kind:
                violations.append("INV-6: %s: leading %s" % (label, kind))
            if has_nul(data):
                violations.append("INV-6: %s: NUL bytes" % label)
            if b"\r" in data:
                violations.append("INV-6: %s: CRLF or bare CR byte present" % label)
            if has_forbidden_control_bytes(data):
                violations.append("INV-6: %s: forbidden ASCII control byte present" % label)
            try:
                data.decode("utf-8")
            except UnicodeDecodeError as exc:
                violations.append("INV-6: %s: not strict UTF-8 (%s)" % (label, exc))
    return violations


def check_inv7_edge_cases(root):
    violations = []
    suffix = "-edge-cases.md"
    for path in sorted((root / ".agents").rglob("*" + suffix)):
        label = _rel(root, path)
        stem = path.name[: -len(suffix)]
        if stem != path.parent.name:
            violations.append(
                "INV-7: %s: prefix %r must equal parent directory %r"
                % (label, stem, path.parent.name)
            )
        if not (path.parent / "SKILL.md").is_file():
            violations.append("INV-7: %s: no sibling SKILL.md" % label)
        text = path.read_bytes().decode("utf-8", errors="replace").lstrip()
        if not text.startswith("# "):
            violations.append("INV-7: %s: must begin with a '# ' H1 heading" % label)
    return violations


def check_inv8_vocabulary(root):
    violations = []
    for dirpath, dirnames, filenames in os.walk(root / ".agents"):
        dirnames[:] = [d for d in dirnames if d not in INV8_EXCLUDED_DIRS]
        for filename in sorted(filenames):
            path = Path(dirpath) / filename
            if path.suffix not in SCAN_EXTENSIONS:
                continue
            # sync_global_config.py is allowed to clean control bytes; skip scripts/
            label = _rel(root, path)
            text = path.read_bytes().decode("utf-8", errors="replace")
            for token in scan_tokens(text):
                violations.append(
                    "INV-8: %s: forbidden vocabulary %r" % (label, token)
                )
    return violations


def check_inv10_skill_security(root):
    violations = []
    skills_dir = root / ".agents" / "skills"
    targets = list(skills_dir.rglob("SKILL.md")) + list(
        skills_dir.rglob("*-edge-cases.md")
    )
    for path in sorted(set(targets)):
        if not path.is_file():
            continue
        label = _rel(root, path)
        text = path.read_bytes().decode("utf-8", errors="replace")
        for err in scan_skill_security(text, label):
            violations.append("INV-10: %s" % err)
    return violations


CHECKS = (
    ("INV-9", check_inv9_junction),
    ("INV-1", check_inv1_frontmatter),
    ("INV-2", check_inv2_json_and_paths),
    ("INV-3", check_inv3_hooks),
    ("INV-4", check_inv4_pipeline_skills),
    ("INV-5", check_inv5_ps1_safety),
    ("INV-6", check_inv6_encoding),
    ("INV-7", check_inv7_edge_cases),
    ("INV-8", check_inv8_vocabulary),
    ("INV-10", check_inv10_skill_security),
)


def run_checks(root, checks=CHECKS):
    """Run checks fail-closed; INV-9 firing short-circuits the rest."""
    violations = []
    for inv_id, check in checks:
        try:
            found = check(root)
        except Exception as exc:
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
