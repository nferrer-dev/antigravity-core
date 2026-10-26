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
import ast
import hashlib
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

FORBIDDEN_PS1_CALL = "Invoke-" + "Expression"

SCAN_EXTENSIONS = {".md", ".json", ".ps1", ".py", ".js"}
INV8_EXCLUDED_RELPATHS = {".claude/settings.local.json"}
INV8_EXCLUDED_DIRS = {"tests", "__pycache__", "node_modules"}

FORBIDDEN_CONTROL_BYTES = (
    set(range(0x00, 0x09)) | {0x0B, 0x0C, 0x0D} | set(range(0x0E, 0x20))
)
CLAUDE_MD_MAX_BYTES = 18000
SKILL_MD_MAX_LINES = 500

EXPECTED_CLAUDE_SKILLS = (
    "brainstorm-solutions",
    "coherence-bake",
    "comprehend-problem",
    "cortex-librarian",
    "debate",
    "design-validate",
    "harness-scaffold",
    "iterative-implement",
    "markdown-style-expert",
    "security-auditor",
    "skill-evolve",
    "style-cpp",
    "style-go",
    "style-java",
    "style-js",
    "style-python",
    "style-rust",
    "technical-debate",
)

EXPECTED_CLAUDE_AGENTS = (
    "cortex-librarian",
    "stage3-design-reviewer",
    "stage4-code-auditor",
)

PIPELINE_HEADING = "## Stage 0-4 Pipeline"
RULES_BULLET_RE = re.compile(r"^- \*\*([a-z-]+)\*\* — ", re.MULTILINE)
BACKTICK_RE = re.compile(r"`([^`]+)`")
NAME_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
XML_TAG_RE = re.compile(r"<\s*[A-Za-z/!][^>]*>")
FM_LINE_RE = re.compile(r"([a-z][a-z0-9_-]*): (.*)")
HOOK_CANDIDATE_RE = re.compile(r"\$CLAUDE_PROJECT_DIR/([^\"\s]+)")
HOOK_REF_GATE_RE = re.compile(r"\.claude/hooks/[A-Za-z0-9][A-Za-z0-9._-]*")
DELIMITER_CELL_RE = re.compile(r":?-{3,}:?")
TELEMETRY_CHAIN_RE = re.compile(r"^(.*)\s\[chain:([0-9a-fA-F]{8})\]$")

REQUIRED_BRC_GUARD_RULES = (
    "secret-file-access",
    "harness-config-self-tampering",
    "generated-output-write-guard",
    "stage0-comprehend-problem-gate",
    "stage1-candidate-solutions-gate",
    "rubric-score-threshold-gate",
    "untrusted-web-markdown-image-exfil",
    "subagent-mvc-prompt-cap",
    "subagent-message-injection-guard",
    "subagent-role-least-privilege",
    "subagent-taint-delegation-guard",
    "cortex-memory-poisoning-guard",
    "untrusted-web-memory-taint",
    "ssrf-local-metadata-url",
    "obfuscated-encoded-command",
    "untrusted-web-egress-taint",
    "dynamic-code-evaluation",
    "inline-secret-token",
    "secret-file-shell-read",
    "recursive-force-delete",
    "git-push-force-protected-branch",
    "git-reset-hard-protected-branch",
    "sql-drop",
    "git-config-mutation-guard",
    "git-no-verify-bypass",
    "mkfs",
    "kill-all-processes",
    "disk-format",
    "destructive-infrastructure-command",
)

REQUIRED_TELEMETRY_MARKERS = (
    "[VERDICT: REJECT]",
    "[VERDICT: PROCEED_FIX]",
    "[GLOBAL VERDICT: REJECT]",
    "[GLOBAL VERDICT: PROCEED]",
    "<BLAST_RADIUS>",
    "BLOCKING:",
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
    """NUL bytes mark BOM-less UTF-16 masquerading as UTF-8 (gate C)."""
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


def check_skill_description_triggers(desc, label):
    """Verify that a skill description includes positive and negative trigger clauses."""
    violations = []
    lower = (desc or "").lower()
    has_positive = any(
        phrase in lower
        for phrase in ("use when", "use for", "use before", "use after")
    )
    has_negative = any(
        phrase in lower
        for phrase in ("do not use", "do not invoke", "skip ")
    )
    if not has_positive:
        violations.append(
            "%s: description missing positive trigger clause ('Use when/for/before/after...')"
            % label
        )
    if not has_negative:
        violations.append(
            "%s: description missing negative boundary clause ('Do not use/invoke...')"
            % label
        )
    return violations


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
    skills_root = root / ".claude" / "skills"
    for expected_skill in EXPECTED_CLAUDE_SKILLS:
        skill_file = skills_root / expected_skill / "SKILL.md"
        if not skill_file.is_file():
            violations.append(
                "INV-1: .claude/skills/%s/SKILL.md: missing expected skill"
                % expected_skill
            )
    for skill_file in sorted(skills_root.glob("*/SKILL.md")):
        label = _rel(root, skill_file)
        raw = skill_file.read_bytes()
        lines = raw.decode("utf-8", errors="replace").split("\n")
        if len(lines) > SKILL_MD_MAX_LINES:
            violations.append(
                "INV-1: %s: exceeds %d-line cap (%d lines)"
                % (label, SKILL_MD_MAX_LINES, len(lines))
            )
        mapping, errors = parse_frontmatter(raw, label)
        violations.extend("INV-1: %s" % e for e in errors)
        if mapping and mapping.get("name", skill_file.parent.name) != skill_file.parent.name:
            violations.append(
                "INV-1: %s: name %r does not match directory %r"
                % (label, mapping["name"], skill_file.parent.name)
            )
        if mapping and "description" in mapping:
            for trig_err in check_skill_description_triggers(mapping["description"], label):
                violations.append("INV-1: %s" % trig_err)

    for rel_script in (
        ("comprehend-problem", "scripts", "structural_graph_polyfill.py"),
        ("comprehend-problem", "scripts", "logical_z3_polyfill.py"),
        ("comprehend-problem", "scripts", "rubric_grade_gate.py"),
        ("coherence-bake", "scripts", "coherence_bake_gate.py"),
    ):
        pf_path = skills_root.joinpath(*rel_script)
        pf_label = _rel(root, pf_path)
        if not pf_path.is_file():
            violations.append("INV-1: %s: missing skill script" % pf_label)
            continue
        try:
            ast.parse(pf_path.read_bytes().decode("utf-8"))
        except (UnicodeDecodeError, SyntaxError) as exc:
            violations.append("INV-1: %s: invalid Python syntax (%s)" % (pf_label, exc))
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


def _extract_relative_md_links(text):
    cleaned = re.sub(r"```[\s\S]*?```", "", text)
    cleaned = re.sub(r"`[^`\n]+`", "", cleaned)
    links = []
    for match in re.finditer(
        r"\[[^\]]+\]\((?!https?:|mailto:|file:|sidecar:|customization:|conversation:|#)([^)#\s]+)",
        cleaned,
    ):
        target = match.group(1).strip()
        if not target or "<" in target or ">" in target or "[" in target:
            continue
        links.append(target)
    return sorted(set(links))


def check_inv2_json(root):
    violations = []
    required = (root / ".claude" / "settings.json", root / ".mcp.json")
    for path in required:
        label = _rel(root, path)
        if not path.is_file():
            violations.append("INV-2: %s: missing" % label)
            continue
        try:
            data = _load_json(path)
            if path.name == ".mcp.json":
                servers = data.get("mcpServers") if isinstance(data, dict) else None
                if not isinstance(servers, dict) or not servers:
                    violations.append("INV-2: %s: 'mcpServers' must be a non-empty object" % label)
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
    agents_dir = root / ".claude" / "agents"
    for agent_stem in EXPECTED_CLAUDE_AGENTS:
        if not (agents_dir / ("%s.md" % agent_stem)).is_file():
            violations.append(
                "INV-2: .claude/agents/%s.md: missing custom agent markdown" % agent_stem
            )
    for agent_md in sorted(agents_dir.glob("*.md")) if agents_dir.is_dir() else ():
        agent_stem = agent_md.stem
        a_label = _rel(root, agent_md)
        a_text = agent_md.read_bytes().decode("utf-8", errors="replace")
        a_lines = a_text.split("\n")
        if not a_lines or a_lines[0].strip() != "---":
            violations.append("INV-2: %s: missing opening frontmatter fence" % a_label)
            continue
        end_idx = next(
            (i for i in range(1, len(a_lines)) if a_lines[i].strip() == "---"),
            None,
        )
        if end_idx is None:
            violations.append("INV-2: %s: missing closing frontmatter fence" % a_label)
            continue
        a_map = {}
        for ln in a_lines[1:end_idx]:
            m = FM_LINE_RE.fullmatch(ln.rstrip("\r"))
            if m:
                a_map[m.group(1)] = m.group(2).strip()
        if a_map.get("name") != agent_stem:
            violations.append(
                "INV-2: %s: frontmatter name %r must equal %r"
                % (a_label, a_map.get("name"), agent_stem)
            )
        for trig_err in check_skill_description_triggers(a_map.get("description", ""), a_label):
            violations.append("INV-2: %s" % trig_err)
        tools_val = a_map.get("tools", "")
        if not tools_val or any(
            bad_t in tools_val for bad_t in ("Bash", "Write", "Edit", "MultiEdit")
        ):
            violations.append(
                "INV-2: %s: read-only agent tools %r must not include write/shell tools"
                % (a_label, tools_val)
            )
    md_targets = (
        [root / "CLAUDE.md"]
        + sorted((root / ".claude" / "skills").rglob("*.md"))
        + sorted((root / ".claude" / "rules").glob("*.md"))
    )
    for md_path in md_targets:
        if not md_path.is_file():
            continue
        m_label = _rel(root, md_path)
        m_text = md_path.read_bytes().decode("utf-8", errors="replace")
        for rel_link in _extract_relative_md_links(m_text):
            if not (md_path.parent / rel_link).resolve().exists():
                violations.append(
                    "INV-2: %s: relative link %r does not exist" % (m_label, rel_link)
                )
    return violations


def check_inv3_hooks(root):
    violations = []
    settings = root / ".claude" / "settings.json"
    label = _rel(root, settings)
    try:
        config = _load_json(settings)
    except (OSError, ValueError, UnicodeDecodeError):
        return ["INV-3: %s unparseable; hook references unverifiable"
                % label]
    hooks_map = config.get("hooks") or {}
    for req_ev in ("PreToolUse", "Stop", "SubagentStop"):
        if req_ev not in hooks_map:
            violations.append("INV-3: %s: missing required event %r" % (label, req_ev))
    refs = {}
    total_timeout = 0
    for entries in hooks_map.values():
        for entry in entries:
            for hook in entry.get("hooks", []):
                t_val = int(hook.get("timeout", 30))
                if t_val <= 0 or t_val > 10:
                    violations.append(
                        "INV-3: %s: hook handler timeout %ds must be between 1s and 10s"
                        % (label, t_val)
                    )
                total_timeout += t_val
                command = hook.get("command", "")
                gated = extract_hook_refs(command)
                if "$CLAUDE_PROJECT_DIR" in command and not gated:
                    violations.append(
                        "INV-3: hook command %r contains no gate-passing "
                        ".claude/hooks reference" % command
                    )
                for g_ref in gated:
                    refs.setdefault(g_ref, []).append(command)
    if total_timeout > 30:
        violations.append(
            "INV-3: %s: total hook timeout %ds exceeds 30s cap" % (label, total_timeout)
        )
    if not refs:
        violations.append("INV-3: %s: no hook scripts referenced" % label)
    hooks_dir = (root / ".claude" / "hooks").resolve()
    for ref in sorted(refs):
        target = root / ref
        if not target.is_file():
            violations.append("INV-3: %s: referenced hook missing" % ref)
        elif not str(target.resolve()).startswith(str(hooks_dir)):
            violations.append("INV-3: %s: resolves outside .claude/hooks" % ref)
        else:
            script_text = target.read_bytes().decode("utf-8", errors="replace")
            if script_text.strip().startswith("# mock"):
                continue
            for cmd in refs[ref]:
                if "-NoProfile" not in cmd or "-NonInteractive" not in cmd:
                    violations.append(
                        "INV-3: %s: hook command %r must include -NoProfile and -NonInteractive"
                        % (label, cmd)
                    )
            if target.name == "brc-guard.ps1":
                for rule_id in REQUIRED_BRC_GUARD_RULES:
                    if rule_id not in script_text:
                        violations.append(
                            "INV-3: %s: missing required rule ID %r"
                            % (ref, rule_id)
                        )
                if "[chain:" not in script_text:
                    violations.append(
                        "INV-3: %s: missing SHA-256 telemetry chain tag" % ref
                    )
            elif target.name == "telemetry-append.ps1":
                for marker in REQUIRED_TELEMETRY_MARKERS:
                    if marker not in script_text:
                        violations.append(
                            "INV-3: %s: missing causal marker %r" % (ref, marker)
                        )
                if "[chain:" not in script_text:
                    violations.append(
                        "INV-3: %s: missing SHA-256 telemetry chain tag" % ref
                    )
    return violations


def check_inv4_pipeline_table(root):
    violations = []
    claude_md = root / "CLAUDE.md"
    if not claude_md.is_file():
        return ["INV-4: CLAUDE.md missing"]
    raw = claude_md.read_bytes()
    if len(raw) > CLAUDE_MD_MAX_BYTES:
        violations.append(
            "INV-4: CLAUDE.md size %d bytes exceeds %d-byte cap"
            % (len(raw), CLAUDE_MD_MAX_BYTES)
        )
    if raw.startswith(b"---"):
        violations.append(
            "INV-4: CLAUDE.md must not start with a YAML frontmatter fence '---'"
        )
    text = raw.decode("utf-8", errors="replace")
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
    ps1_files = sorted((root / ".claude" / "hooks").glob("*.ps1"))
    if not ps1_files:
        violations.append("INV-5: no .ps1 hook scripts found in .claude/hooks")
    for path in ps1_files:
        label = _rel(root, path)
        data = path.read_bytes()
        try:
            ps_text = data.decode("ascii")
        except UnicodeDecodeError:
            violations.append("INV-5: %s: must be strict 7-bit ASCII" % label)
            continue
        if FORBIDDEN_PS1_CALL in ps_text:
            violations.append(
                "INV-5: %s: contains forbidden %s call" % (label, FORBIDDEN_PS1_CALL)
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
    seen_targets = {str(p.resolve()) for p in targets if p.exists()}
    for dirpath, dirnames, filenames in os.walk(root / ".claude"):
        dirnames[:] = [d for d in dirnames if d not in {"__pycache__", "node_modules"}]
        for filename in sorted(filenames):
            p = Path(dirpath) / filename
            if p.suffix in SCAN_EXTENSIONS and str(p.resolve()) not in seen_targets:
                targets.append(p)
                seen_targets.add(str(p.resolve()))
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
        if b"\r" in data:
            violations.append("INV-6: %s: CRLF or bare CR byte present" % label)
        if has_forbidden_control_bytes(data):
            violations.append("INV-6: %s: forbidden ASCII control byte present" % label)
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
    skills_dir = root / ".claude" / "skills"
    for skill in (
        "coherence-bake",
        "comprehend-problem",
        "debate",
        "iterative-implement",
        "markdown-style-expert",
        "security-auditor",
        "style-cpp",
        "style-go",
        "style-java",
        "style-js",
        "style-python",
        "style-rust",
    ):
        s_dir = skills_dir / skill
        if (s_dir / "SKILL.md").is_file() and not (s_dir / (skill + suffix)).is_file():
            violations.append(
                "INV-7: %s: missing companion %s%s" % (_rel(root, s_dir), skill, suffix)
            )
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
        text = path.read_bytes().decode("utf-8", errors="replace").lstrip()
        lines = text.splitlines()
        if len(lines) > 150:
            violations.append(
                "INV-7: %s: %d lines exceeds 150-line ACE compaction cap"
                % (label, len(lines))
            )
        expected_h1 = "# Edge Cases & Heuristics: %s" % stem
        if not lines or lines[0].strip() != expected_h1:
            violations.append(
                "INV-7: %s: must begin with canonical H1 %r" % (label, expected_h1)
            )
        bullets = [ln for ln in lines[1:] if ln.startswith("- ")]
        subheadings = [ln for ln in lines[1:] if ln.startswith("#")]
        if subheadings:
            violations.append(
                "INV-7: %s: must use flat top-level bullets without H2/H3 subheadings"
                % label
            )
        if len(bullets) < 1:
            violations.append(
                "INV-7: %s: must contain at least 1 flat '- ' heuristic bullet" % label
            )
        if len(bullets) > 10:
            violations.append(
                "INV-7: %s: contains %d heuristics (exceeds 10-heuristic cap)"
                % (label, len(bullets))
            )
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


def verify_telemetry_chain(text, label):
    """Verify rolling SHA-256 hash chain on telemetry lines containing [chain:<8hex>]."""
    violations = []
    prev_chain = "00000000"
    for line_no, raw_line in enumerate((text or "").splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped:
            continue
        match = TELEMETRY_CHAIN_RE.match(stripped)
        if not match:
            continue
        body, claimed = match.group(1), match.group(2).lower()
        digest = hashlib.sha256(
            ("%s|%s" % (prev_chain, body)).encode("utf-8")
        ).hexdigest()[:8]
        if digest != claimed:
            violations.append(
                "%s: line %d telemetry hash chain mismatch (expected [chain:%s], got [chain:%s])"
                % (label, line_no, digest, claimed)
            )
        prev_chain = claimed
    return violations


def scan_test_integrity(source_text, label):
    """Verify test_*.py methods contain real assertions, zero skips, and no tautologies."""
    violations = []
    try:
        tree = ast.parse(source_text)
    except SyntaxError as exc:
        return ["%s: SyntaxError in test file (%s)" % (label, exc)]
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test_"):
            continue
        for dec in node.decorator_list:
            if "skip" in ast.dump(dec).lower():
                violations.append(
                    "%s: %s uses forbidden skip decorator (reward-hacking guard)"
                    % (label, node.name)
                )
        assert_count = 0
        for child in ast.walk(node):
            if isinstance(child, ast.Assert):
                assert_count += 1
                if isinstance(child.test, ast.Constant) and bool(child.test.value) is True:
                    violations.append(
                        "%s: %s contains tautological assert True"
                        % (label, node.name)
                    )
                elif (
                    isinstance(child.test, ast.Compare)
                    and len(child.test.comparators) == 1
                    and ast.dump(child.test.left) == ast.dump(child.test.comparators[0])
                ):
                    violations.append(
                        "%s: %s contains reflexive assert comparison on identical expressions"
                        % (label, node.name)
                    )
            elif isinstance(child, ast.Call):
                func = child.func
                attr_name = getattr(func, "attr", getattr(func, "id", ""))
                if attr_name == "skipTest":
                    violations.append(
                        "%s: %s calls skipTest (reward-hacking guard)"
                        % (label, node.name)
                    )
                if (
                    attr_name.startswith("assert")
                    or attr_name.startswith("_assert")
                    or attr_name.startswith("check_")
                    or attr_name == "fail"
                ):
                    assert_count += 1
                if (
                    attr_name in {"assertEqual", "assertIs"}
                    and len(child.args) >= 2
                    and ast.dump(child.args[0]) == ast.dump(child.args[1])
                ):
                    violations.append(
                        "%s: %s contains tautological %s on identical expressions"
                        % (label, node.name, attr_name)
                    )
                if (
                    attr_name == "assertTrue"
                    and len(child.args) >= 1
                    and isinstance(child.args[0], ast.Constant)
                    and child.args[0].value is True
                ):
                    violations.append(
                        "%s: %s contains tautological assertTrue(True)"
                        % (label, node.name)
                    )
                if (
                    attr_name == "assertFalse"
                    and len(child.args) >= 1
                    and isinstance(child.args[0], ast.Constant)
                    and child.args[0].value is False
                ):
                    violations.append(
                        "%s: %s contains tautological assertFalse(False)"
                        % (label, node.name)
                    )
                if (
                    attr_name == "assertIsNone"
                    and len(child.args) >= 1
                    and isinstance(child.args[0], ast.Constant)
                    and child.args[0].value is None
                ):
                    violations.append(
                        "%s: %s contains tautological assertIsNone(None)"
                        % (label, node.name)
                    )
            elif isinstance(child, ast.Try):
                body_has_assert = any(
                    isinstance(stmt_node, ast.Assert)
                    or (
                        isinstance(stmt_node, ast.Call)
                        and getattr(
                            stmt_node.func,
                            "attr",
                            getattr(stmt_node.func, "id", ""),
                        ).startswith("assert")
                    )
                    for stmt in child.body
                    for stmt_node in ast.walk(stmt)
                )
                if body_has_assert:
                    for handler in child.handlers:
                        exc_name = ""
                        if handler.type is None:
                            exc_name = "bare"
                        elif isinstance(handler.type, ast.Name):
                            exc_name = handler.type.id
                        elif isinstance(handler.type, ast.Tuple):
                            names = [
                                elt.id
                                for elt in handler.type.elts
                                if isinstance(elt, ast.Name)
                            ]
                            if any(
                                n in {"Exception", "BaseException", "AssertionError"}
                                for n in names
                            ):
                                exc_name = "broad"
                        if exc_name in {
                            "bare",
                            "broad",
                            "Exception",
                            "BaseException",
                            "AssertionError",
                        } and all(isinstance(s, ast.Pass) for s in handler.body):
                            violations.append(
                                "%s: %s swallows assertion failure in bare/broad except-pass block (reward-hacking guard)"
                                % (label, node.name)
                            )
        if assert_count == 0:
            violations.append(
                "%s: %s contains zero assertions (reward-hacking guard)"
                % (label, node.name)
            )
    return violations



def _compute_func_mccabe(func_node):
    complexity = 1
    branch_types = (
        ast.If,
        ast.For,
        ast.AsyncFor,
        ast.While,
        ast.ExceptHandler,
        ast.With,
        ast.AsyncWith,
        ast.IfExp,
        ast.comprehension,
    )
    for child in ast.walk(func_node):
        if isinstance(child, branch_types):
            complexity += 1
        elif isinstance(child, ast.BoolOp):
            complexity += max(0, len(child.values) - 1)
    return complexity


def _find_unused_upper_constants(tree):
    defined = set()
    loaded = set()
    for stmt in tree.body:
        targets = []
        if isinstance(stmt, ast.Assign):
            targets = stmt.targets
        elif isinstance(stmt, ast.AnnAssign):
            targets = [stmt.target]
        for t in targets:
            if isinstance(t, ast.Name) and re.fullmatch(r"[A-Z][A-Z0-9_]{2,}", t.id):
                defined.add(t.id)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            loaded.add(node.id)
    return sorted(defined - loaded)


def _check_rubric_schema_and_script_parity(root):
    violations = []
    shared_scripts = (
        "skills/coherence-bake/scripts/coherence_bake_gate.py",
        "skills/comprehend-problem/scripts/logical_z3_polyfill.py",
        "skills/comprehend-problem/scripts/rubric_grade_gate.py",
        "skills/comprehend-problem/scripts/structural_graph_polyfill.py",
    )
    cl_dir = "." + "claude"
    peer_trees = ("." + "agents", "." + "codex")
    for rel_script in shared_scripts:
        base_path = root / cl_dir / rel_script
        if not base_path.is_file():
            continue
        base_sha = hashlib.sha256(base_path.read_bytes()).hexdigest()
        for tree_name in peer_trees:
            peer_path = root / tree_name / rel_script
            if peer_path.is_file():
                peer_sha = hashlib.sha256(peer_path.read_bytes()).hexdigest()
                if peer_sha != base_sha:
                    violations.append(
                        "INV-10: %s/%s: SHA-256 drift vs %s/%s"
                        % (tree_name, rel_script, cl_dir, rel_script)
                    )
    prod_py_files = list((root / cl_dir / "skills").glob("*/scripts/*.py"))
    all_py_files = prod_py_files + list((root / cl_dir / "tests").glob("*.py"))
    for py_path in sorted(set(all_py_files)):
        if not py_path.is_file():
            continue
        try:
            tree = ast.parse(py_path.read_bytes().decode("utf-8", errors="replace"))
        except SyntaxError:
            continue
        for unused_const in _find_unused_upper_constants(tree):
            violations.append(
                "INV-10: %s: unused module-level constant %s"
                % (_rel(root, py_path), unused_const)
            )
        if py_path in prod_py_files:
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    comp = _compute_func_mccabe(node)
                    if comp > 9:
                        violations.append(
                            "INV-10: %s: function %s has McCabe complexity %d > 9"
                            % (_rel(root, py_path), node.name, comp)
                        )
    return violations


def _check_constitutional_qualitative_rubric_rule(root):
    cl_md = root / "CLAUDE.md"
    if not cl_md.is_file():
        return []
    txt = cl_md.read_bytes().decode("utf-8", errors="replace").lower()
    req = ("qualitative judgment", "<rubric_score>", "0..3", "architectural", "curation")
    if any(token not in txt for token in req):
        return [
            "INV-10: CLAUDE.md: missing Universal Rubric-Graded Qualitative Judgment (<RUBRIC_SCORE> 0..3 BARS) rule"
        ]
    return []


def check_inv10_skill_security(root):
    violations = []
    skills_dir = root / ".claude" / "skills"
    targets = (
        list(skills_dir.rglob("SKILL.md"))
        + list(skills_dir.rglob("*-edge-cases.md"))
        + list(skills_dir.glob("*/references/*.md"))
        + [root / "CLAUDE.md"]
    )
    agents_dir = root / ".claude" / "agents"
    if agents_dir.is_dir():
        targets.extend(agents_dir.glob("*.md"))
    rules_dir = root / ".claude" / "rules"
    if rules_dir.is_dir():
        targets.extend(rules_dir.glob("*.md"))
    for path in sorted(set(targets)):
        if not path.is_file():
            continue
        label = _rel(root, path)
        text = path.read_bytes().decode("utf-8", errors="replace")
        for err in scan_skill_security(text, label):
            violations.append("INV-10: %s" % err)
        if path.name == "SKILL.md" and path.parent.name in (
            "style-cpp",
            "style-go",
            "style-java",
            "style-js",
            "style-python",
            "style-rust",
            "security-auditor",
            "markdown-style-expert",
        ):
            if "<RUBRIC_SCORE>" not in text:
                violations.append(
                    "INV-10: %s: Stage 4 auditor skill missing <RUBRIC_SCORE> contract"
                    % label
                )
            if "<REJECTION_EVIDENCE>" not in text:
                violations.append(
                    "INV-10: %s: Stage 4 auditor skill missing <REJECTION_EVIDENCE> contract"
                    % label
                )
            for k in ('"stage"', '"role"', '"verdict"', '"criteria"', '"id"', '"evidence"', '"score"'):
                if k not in text:
                    violations.append(
                        "INV-10: %s: Stage 4 auditor skill missing schema key %s"
                        % (label, k)
                    )
    for agent_name in ("stage3-design-reviewer.md", "stage4-code-auditor.md"):
        ag_path = root / ".claude" / "agents" / agent_name
        if ag_path.is_file():
            ag_txt = ag_path.read_bytes().decode("utf-8", errors="replace")
            for k in ('"stage"', '"role"', '"verdict"', '"criteria"', '"id"', '"evidence"', '"score"'):
                if k not in ag_txt:
                    violations.append("INV-10: %s: missing required <RUBRIC_SCORE> schema key %s" % (_rel(root, ag_path), k))
    violations.extend(_check_constitutional_qualitative_rubric_rule(root))
    violations.extend(_check_rubric_schema_and_script_parity(root))
    for test_py in sorted((root / ".claude" / "tests").glob("test_*.py")):
        t_label = _rel(root, test_py)
        t_text = test_py.read_bytes().decode("utf-8", errors="replace")
        for t_err in scan_test_integrity(t_text, t_label):
            violations.append("INV-10: %s" % t_err)
    tel_file = root / ".claude" / "telemetry" / "agentic_telemetry.md"
    if tel_file.is_file():
        tel_label = _rel(root, tel_file)
        tel_text = tel_file.read_bytes().decode("utf-8", errors="replace")
        for c_err in verify_telemetry_chain(tel_text, tel_label):
            violations.append("INV-10: %s" % c_err)
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
    ("INV-10", check_inv10_skill_security),
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
