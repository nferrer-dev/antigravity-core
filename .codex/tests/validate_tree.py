"""OpenAI Codex harness tree validator (read-only).

Validates the invariants of the OpenAI Codex SOP tree (root CODEX.md plus
the .codex/ directory) per Addendum 10 of the adjudicated implementation plan:
- INV-1: SKILL.md frontmatter spec (17 skills), <= 500 line cap, 10 mandatory
         agents/openai.yaml (allow_implicit_invocation: false) policies, and
         Stage 0 comprehend-problem/scripts/*.py AST integrity
- INV-2: JSON (.codex/hooks.json), TOML (.codex/config.toml, .codex/agents/*.toml),
         and Starlark (.codex/rules/antigravity.rules) syntax & structural integrity
- INV-3: Hook references, <= 15s total timeout, 26 BRC/MAC rules, and telemetry markers
- INV-4: CODEX.md (<= 18,000 bytes, no frontmatter) pipeline table skill resolution
- INV-5: CODEX.md rules-module cross-references and PowerShell 7-bit ASCII / no IEX safety
- INV-6: Encoding & control-byte hygiene (UTF-8 no BOM, LF line endings, no NUL/control bytes)
- INV-7: Edge-cases companion file structure (*-edge-cases.md)
- INV-8: Vocabulary hygiene (zero stale Antigravity-only or Claude-only identifiers)
- INV-9: Root-anchor integrity (repo-self-contained junction check)
- INV-10: Skill security (invisible Unicode/injection), test integrity, and telemetry hash chain

Exit code 0 when all invariants hold; 1 otherwise, one violation per line.
Stdlib only; runnable from any cwd; never writes.
"""
import ast
import hashlib
import json
import os
import re
import sys
import tomllib
from pathlib import Path

# --------------------------------------------------------------------------
# CONSTANTS
# --------------------------------------------------------------------------

# Forbidden Antigravity-only and Claude-only vocabulary, assembled from
# fragments so this file's own bytes never contain the contraband forms
# (split-literal invariant).
FORBIDDEN_TOKENS = (
    "grep_" + "search",
    "view_" + "file",
    "invoke_" + "subagent",
    "define_" + "subagent",
    "manage_" + "subagents",
    "manage_" + "task",
    "moma_" + "search",
    "CLAUDE" + ".md",
    ".claude" + "/",
    ".agents" + "/",
)

FORBIDDEN_PS1_CALL = "Invoke-" + "Expression"

SCAN_EXTENSIONS = {".md", ".json", ".toml", ".rules", ".yaml", ".ps1", ".py"}
INV8_EXCLUDED_RELPATHS = {".codex/config.toml"}
INV8_EXCLUDED_DIRS = {"tests", "__pycache__"}

FORBIDDEN_CONTROL_BYTES = (
    set(range(0x00, 0x09)) | {0x0B, 0x0C, 0x0D} | set(range(0x0E, 0x20))
)

CODEX_MD_MAX_BYTES = 18000
SKILL_MD_MAX_LINES = 500
PIPELINE_HEADING = "## Stage 0-4 Pipeline"
RULES_BULLET_RE = re.compile(r"^- \*\*([a-z-]+)\*\* \u2014 ", re.MULTILINE)
BACKTICK_RE = re.compile(r"`([^`]+)`")
NAME_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
XML_TAG_RE = re.compile(r"<\s*[A-Za-z/!][^>]*>")
FM_LINE_RE = re.compile(r"([a-z][a-z0-9_-]*): (.*)")
HOOK_SCRIPT_RE = re.compile(r"(?:\./\.codex/hooks|\.codex/hooks)/([A-Za-z0-9._-]+\.ps1)")
DELIMITER_CELL_RE = re.compile(r":?-{3,}:?")
TELEMETRY_CHAIN_RE = re.compile(r"^(.*)\s\[chain:([0-9a-fA-F]{8})\]$")

EXPECTED_CODEX_SKILLS = (
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

INTERNAL_COMMITTEE_SKILLS = (
    "cortex-librarian",
    "markdown-style-expert",
    "security-auditor",
    "skill-evolve",
    "style-cpp",
    "style-go",
    "style-java",
    "style-js",
    "style-python",
    "style-rust",
)

EXPECTED_CODEX_AGENTS = (
    "cortex-librarian",
    "stage3-design-reviewer",
    "stage4-code-auditor",
)

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
    """NUL bytes mark BOM-less UTF-16 masquerading as UTF-8."""
    return b"\x00" in data


def has_forbidden_control_bytes(data):
    """Return True if data contains forbidden ASCII control characters."""
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
    non_trailing_lines = lines[:-1] if lines and lines[-1] == "" else lines
    if len(non_trailing_lines) > SKILL_MD_MAX_LINES:
        violations.append(
            "%s: %d lines exceeds %d-line progressive-disclosure cap"
            % (label, len(non_trailing_lines), SKILL_MD_MAX_LINES)
        )
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
    """Extract skill names from the pipeline table."""
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
            continue
        if len(cells) > 1 and all(
            DELIMITER_CELL_RE.fullmatch(c) for c in cells[1:-1] if c
        ):
            continue
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
    """Extract rules-module stems from the CODEX.md pointer bullets."""
    return RULES_BULLET_RE.findall(text)


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
    """Root-anchor integrity: refuse junction/symlink deployments."""
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
    if not (root / "CODEX.md").is_file() or not (root / ".codex").is_dir():
        violations.append(
            "INV-9: repository root %s lacks CODEX.md or .codex/ — refusing "
            "to guess a root" % root
        )
    return violations


def check_inv1_frontmatter(root):
    violations = []
    skills_root = root / ".codex" / "skills"
    for expected_skill in EXPECTED_CODEX_SKILLS:
        skill_file = skills_root / expected_skill / "SKILL.md"
        if not skill_file.is_file():
            violations.append(
                "INV-1: .codex/skills/%s/SKILL.md: missing expected skill"
                % expected_skill
            )
    for skill_file in sorted(skills_root.glob("*/SKILL.md")):
        label = _rel(root, skill_file)
        mapping, errors = parse_frontmatter(skill_file.read_bytes(), label)
        violations.extend("INV-1: %s" % e for e in errors)
        if mapping and mapping.get("name", skill_file.parent.name) != skill_file.parent.name:
            violations.append(
                "INV-1: %s: name %r does not match directory %r"
                % (label, mapping["name"], skill_file.parent.name)
            )
        if mapping and "description" in mapping:
            for trig_err in check_skill_description_triggers(mapping["description"], label):
                violations.append("INV-1: %s" % trig_err)

    for internal_name in INTERNAL_COMMITTEE_SKILLS:
        yaml_path = skills_root / internal_name / "agents" / "openai.yaml"
        yaml_label = _rel(root, yaml_path)
        if not yaml_path.is_file():
            violations.append(
                "INV-1: %s: missing mandatory agents/openai.yaml for internal committee skill"
                % yaml_label
            )
            continue
        yaml_text = yaml_path.read_bytes().decode("utf-8", errors="replace")
        if not re.search(
            r"(?m)^policy:\s*\n\s+allow_implicit_invocation:\s*false\s*$",
            yaml_text,
        ):
            violations.append(
                "INV-1: %s: must set policy.allow_implicit_invocation: false"
                % yaml_label
            )

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


def check_inv2_json_toml_rules(root):
    violations = []
    hooks_json = root / ".codex" / "hooks.json"
    hj_label = _rel(root, hooks_json)
    if not hooks_json.is_file():
        violations.append("INV-2: %s: missing" % hj_label)
    else:
        try:
            _load_json(hooks_json)
        except (ValueError, UnicodeDecodeError) as exc:
            violations.append("INV-2: %s: %s" % (hj_label, exc))

    cfg_toml = root / ".codex" / "config.toml"
    cfg_label = _rel(root, cfg_toml)
    if not cfg_toml.is_file():
        violations.append("INV-2: %s: missing" % cfg_label)
    else:
        try:
            parsed_cfg = tomllib.loads(cfg_toml.read_bytes().decode("utf-8"))
            if parsed_cfg.get("project_doc_fallback_filenames") != ["CODEX.md"]:
                violations.append(
                    "INV-2: %s: root-level project_doc_fallback_filenames must be ['CODEX.md']"
                    % cfg_label
                )
            if parsed_cfg.get("project_doc_max_bytes") != 65536:
                violations.append(
                    "INV-2: %s: root-level project_doc_max_bytes must be 65536"
                    % cfg_label
                )
            features = parsed_cfg.get("features") or {}
            if features.get("codex_hooks") is not True:
                violations.append(
                    "INV-2: %s: [features].codex_hooks must be true" % cfg_label
                )
            mcp_servers = parsed_cfg.get("mcp_servers") or {}
            for srv in ("code-graph-context",):
                if srv not in mcp_servers:
                    violations.append(
                        "INV-2: %s: missing [mcp_servers.%s]" % (cfg_label, srv)
                    )
            skills_cfg = (parsed_cfg.get("skills") or {}).get("config") or []
            disabled_paths = {
                entry.get("path")
                for entry in skills_cfg
                if isinstance(entry, dict) and entry.get("enabled") is False
            }
            if len(disabled_paths) < 20:
                violations.append(
                    "INV-2: %s: [[skills.config]] must disable all 20 duplicate repo skills, got %d"
                    % (cfg_label, len(disabled_paths))
                )
        except (ValueError, UnicodeDecodeError) as exc:
            violations.append("INV-2: %s: %s" % (cfg_label, exc))

    agents_dir = root / ".codex" / "agents"
    for agent_stem in EXPECTED_CODEX_AGENTS:
        agent_toml = agents_dir / ("%s.toml" % agent_stem)
        a_label = _rel(root, agent_toml)
        if not agent_toml.is_file():
            violations.append("INV-2: %s: missing custom agent TOML" % a_label)
            continue
        try:
            a_data = tomllib.loads(agent_toml.read_bytes().decode("utf-8"))
            if a_data.get("name") != agent_stem:
                violations.append(
                    "INV-2: %s: root-level name %r must equal %r"
                    % (a_label, a_data.get("name"), agent_stem)
                )
            if not a_data.get("description") or not a_data.get("developer_instructions"):
                violations.append(
                    "INV-2: %s: missing root-level description or developer_instructions"
                    % a_label
                )
            if a_data.get("sandbox_mode") != "read-only":
                violations.append(
                    "INV-2: %s: sandbox_mode must be 'read-only'" % a_label
                )
            a_feat = a_data.get("features") or {}
            if a_feat.get("shell_tool") is not False:
                violations.append(
                    "INV-2: %s: [features].shell_tool must be false" % a_label
                )
            if a_feat.get("request_permissions_tool") is not False:
                violations.append(
                    "INV-2: %s: [features].request_permissions_tool must be false"
                    % a_label
                )
        except (ValueError, UnicodeDecodeError) as exc:
            violations.append("INV-2: %s: %s" % (a_label, exc))

    rules_file = root / ".codex" / "rules" / "antigravity.rules"
    r_label = _rel(root, rules_file)
    if not rules_file.is_file():
        violations.append("INV-2: %s: missing Starlark execution policy file" % r_label)
    else:
        try:
            r_text = rules_file.read_bytes().decode("utf-8")
            r_tree = ast.parse(r_text)
            prefix_calls = [
                n
                for n in ast.walk(r_tree)
                if isinstance(n, ast.Call)
                and getattr(n.func, "id", "") == "prefix_rule"
            ]
            if len(prefix_calls) < 5:
                violations.append(
                    "INV-2: %s: expected at least 5 prefix_rule(...) declarations, got %d"
                    % (r_label, len(prefix_calls))
                )
        except (UnicodeDecodeError, SyntaxError) as exc:
            violations.append("INV-2: %s: invalid Starlark syntax (%s)" % (r_label, exc))

    return violations


def check_inv3_hooks(root):
    violations = []
    hooks_json = root / ".codex" / "hooks.json"
    label = _rel(root, hooks_json)
    if not hooks_json.is_file():
        return ["INV-3: %s: missing" % label]
    try:
        config = _load_json(hooks_json)
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        return ["INV-3: %s unparseable (%s)" % (label, exc)]

    hooks_map = config.get("hooks")
    if not isinstance(hooks_map, dict):
        return ["INV-3: %s: missing top-level 'hooks' object" % label]

    for req_ev in ("PreToolUse", "Stop"):
        if req_ev not in hooks_map:
            violations.append("INV-3: %s: missing required event %r" % (label, req_ev))

    total_timeout = 0
    referenced_scripts = set()
    for event_name, entries in hooks_map.items():
        if not isinstance(entries, list) or not entries:
            violations.append(
                "INV-3: %s: event %r must map to a non-empty list" % (label, event_name)
            )
            continue
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("hooks"), list):
                violations.append(
                    "INV-3: %s: event %r entry missing 'hooks' array" % (label, event_name)
                )
                continue
            for h in entry["hooks"]:
                t_val = int(h.get("timeout", 30))
                if t_val <= 0 or t_val > 5:
                    violations.append(
                        "INV-3: %s: hook handler timeout %ds must be between 1s and 5s"
                        % (label, t_val)
                    )
                total_timeout += t_val
                cmd = h.get("command", "")
                if '"' in cmd:
                    violations.append(
                        "INV-3: %s: hook command %r must not contain inner double quotes"
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
        target = root / ".codex" / "hooks" / script_name
        if not target.is_file():
            violations.append(
                "INV-3: .codex/hooks/%s: referenced hook script missing" % script_name
            )
            continue
        script_text = target.read_bytes().decode("utf-8", errors="replace")
        if script_text.strip().startswith("# mock"):
            continue
        if script_name == "brc-guard.ps1":
            for rule_id in REQUIRED_BRC_GUARD_RULES:
                if rule_id not in script_text:
                    violations.append(
                        "INV-3: .codex/hooks/%s: missing required rule ID %r"
                        % (script_name, rule_id)
                    )
            if "[chain:" not in script_text:
                violations.append(
                    "INV-3: .codex/hooks/%s: missing SHA-256 telemetry chain tag"
                    % script_name
                )
        elif script_name == "telemetry-append.ps1":
            for marker in REQUIRED_TELEMETRY_MARKERS:
                if marker not in script_text:
                    violations.append(
                        "INV-3: .codex/hooks/%s: missing causal marker %r"
                        % (script_name, marker)
                    )
            if "[chain:" not in script_text:
                violations.append(
                    "INV-3: .codex/hooks/%s: missing SHA-256 telemetry chain tag"
                    % script_name
                )
    return violations


def check_inv4_pipeline_table(root):
    violations = []
    codex_md = root / "CODEX.md"
    if not codex_md.is_file():
        return ["INV-4: CODEX.md missing"]
    raw = codex_md.read_bytes()
    if len(raw) > CODEX_MD_MAX_BYTES:
        violations.append(
            "INV-4: CODEX.md size %d bytes exceeds %d-byte cap"
            % (len(raw), CODEX_MD_MAX_BYTES)
        )
    if raw.startswith(b"---"):
        violations.append(
            "INV-4: CODEX.md must not start with a YAML frontmatter fence '---'"
        )
    text = raw.decode("utf-8", errors="replace")
    names, row_violations = extract_pipeline_skills(text)
    violations.extend("INV-4: %s" % v for v in row_violations)
    if not names:
        violations.append("INV-4: pipeline table yielded zero data rows")
    for name in names:
        if not (root / ".codex" / "skills" / name / "SKILL.md").is_file():
            violations.append(
                "INV-4: pipeline table names %r but "
                ".codex/skills/%s/SKILL.md is missing" % (name, name)
            )
    return violations


def check_inv5_rules_and_ps1(root):
    violations = []
    codex_md = root / "CODEX.md"
    if not codex_md.is_file():
        return ["INV-5: CODEX.md missing"]
    text = codex_md.read_bytes().decode("utf-8", errors="replace")
    stems = extract_rules_modules(text)
    if not stems:
        violations.append("INV-5: rules pointer list yielded zero modules")
    for stem in stems:
        if not (root / ".codex" / "rules" / (stem + ".md")).is_file():
            violations.append(
                "INV-5: CODEX.md points at rules module %r but "
                ".codex/rules/%s.md is missing" % (stem, stem)
            )

    ps1_files = sorted((root / ".codex" / "hooks").glob("*.ps1"))
    if not ps1_files:
        violations.append("INV-5: no .ps1 hook scripts found in .codex/hooks")
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
    targets = [root / "CODEX.md"]
    for dirpath, dirnames, filenames in os.walk(root / ".codex"):
        dirnames[:] = [d for d in dirnames if d not in {"__pycache__"}]
        for filename in sorted(filenames):
            path = Path(dirpath) / filename
            if path.suffix in SCAN_EXTENSIONS:
                targets.append(path)
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
    skills_dir = root / ".codex" / "skills"
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
    for path in sorted((root / ".codex").rglob("*" + suffix)):
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
    targets = [root / "CODEX.md"]
    for dirpath, dirnames, filenames in os.walk(root / ".codex"):
        dirnames[:] = [d for d in dirnames if d not in INV8_EXCLUDED_DIRS]
        for filename in sorted(filenames):
            targets.append(Path(dirpath) / filename)
    for path in targets:
        if not path.is_file():
            continue
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


def _check_rubric_schema_and_script_parity(root):
    violations = []
    shared_scripts = (
        "skills/coherence-bake/scripts/coherence_bake_gate.py",
        "skills/comprehend-problem/scripts/logical_z3_polyfill.py",
        "skills/comprehend-problem/scripts/rubric_grade_gate.py",
        "skills/comprehend-problem/scripts/structural_graph_polyfill.py",
    )
    cx_dir = "." + "codex"
    peer_trees = ("." + "agents", "." + "claude")
    for rel_script in shared_scripts:
        base_path = root / cx_dir / rel_script
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
                        % (tree_name, rel_script, cx_dir, rel_script)
                    )
    prod_py_files = list((root / cx_dir / "skills").glob("*/scripts/*.py"))
    for py_path in sorted(set(prod_py_files)):
        if not py_path.is_file():
            continue
        try:
            tree = ast.parse(py_path.read_bytes().decode("utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                comp = _compute_func_mccabe(node)
                if comp > 9:
                    violations.append(
                        "INV-10: %s: function %s has McCabe complexity %d > 9"
                        % (_rel(root, py_path), node.name, comp)
                    )
    return violations


def check_inv10_skill_security(root):
    violations = []
    skills_dir = root / ".codex" / "skills"
    targets = list(skills_dir.rglob("SKILL.md")) + list(
        skills_dir.rglob("*-edge-cases.md")
    )
    rules_dir = root / ".codex" / "rules"
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
    for agent_name in ("stage3-design-reviewer.toml", "stage4-code-auditor.toml"):
        ag_path = root / ".codex" / "agents" / agent_name
        if ag_path.is_file():
            ag_txt = ag_path.read_bytes().decode("utf-8", errors="replace")
            for k in ('"stage"', '"role"', '"verdict"', '"criteria"', '"id"', '"evidence"', '"score"'):
                if k not in ag_txt:
                    violations.append("INV-10: %s: missing required <RUBRIC_SCORE> schema key %s" % (_rel(root, ag_path), k))
    violations.extend(_check_rubric_schema_and_script_parity(root))
    for test_py in sorted((root / ".codex" / "tests").glob("test_*.py")):
        t_label = _rel(root, test_py)
        t_text = test_py.read_bytes().decode("utf-8", errors="replace")
        for t_err in scan_test_integrity(t_text, t_label):
            violations.append("INV-10: %s" % t_err)
    tel_file = root / ".codex" / "telemetry" / "agentic_telemetry.md"
    if tel_file.is_file():
        tel_label = _rel(root, tel_file)
        tel_text = tel_file.read_bytes().decode("utf-8", errors="replace")
        for c_err in verify_telemetry_chain(tel_text, tel_label):
            violations.append("INV-10: %s" % c_err)
    return violations


CHECKS = (
    ("INV-9", check_inv9_junction),
    ("INV-1", check_inv1_frontmatter),
    ("INV-2", check_inv2_json_toml_rules),
    ("INV-3", check_inv3_hooks),
    ("INV-4", check_inv4_pipeline_table),
    ("INV-5", check_inv5_rules_and_ps1),
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
