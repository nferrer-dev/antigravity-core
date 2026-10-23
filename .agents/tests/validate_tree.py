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

NAME_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
XML_TAG_RE = re.compile(r"<\s*[A-Za-z/!][^>]*>")
FM_LINE_RE = re.compile(r"([a-z][a-z0-9_-]*):(?:\s+(.*))?")
HOOK_SCRIPT_RE = re.compile(r"(?:\./hooks|\.agents/hooks)/([A-Za-z0-9._-]+\.ps1)")
CONCRETE_PATH_RE = re.compile(
    r"(?:^|[\s(`\"'])(?:(\.agents/[A-Za-z0-9._/-]+)|file:///C:/Projects/antigravity-core/(\.agents/[A-Za-z0-9._/-]+))"
)
RELATIVE_MD_LINK_RE = re.compile(
    r"\[[^\]]+\]\((?!https?:|mailto:|file:|sidecar:|customization:|conversation:|#)([^)#\s]+)"
)
TELEMETRY_CHAIN_RE = re.compile(r"^(.*)\s\[chain:([0-9a-fA-F]{8})\]$")

REQUIRED_BRC_GUARD_RULES = (
    "secret-file-access",
    "harness-config-self-tampering",
    "generated-output-write-guard",
    "stage0-comprehend-problem-gate",
    "stage3-premature-execution-lock",
    "stage1-candidate-solutions-gate",
    "rubric-score-threshold-gate",
    "untrusted-web-markdown-image-exfil",
    "subagent-mvc-prompt-cap",
    "subagent-message-injection-guard",
    "subagent-role-least-privilege",
    "subagent-taint-delegation-guard",
    "schedule-patience-timer-condition",
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
    "[GLOBAL VERDICT: REJECT]",
    "[GLOBAL VERDICT: PROCEED]",
    "<BLAST_RADIUS>",
    "BLOCKING:",
)

GROUPED_HOOK_EVENTS = {"PreToolUse", "PostToolUse"}
FLAT_HOOK_EVENTS = {"SessionStart", "PreInvocation", "PostInvocation", "Stop"}
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
    "harness-scaffold",
    "reverse-engineer-anything",
    "restart-phone-ui",
    "cortex-librarian",
    "coherence-bake",
)

AGENTS_MD_MAX_BYTES = 18000
RULE_FILE_MAX_BYTES = 24000
VALID_RULE_TRIGGERS = {"always_on", "model_decision", "glob", "manual"}
REQUIRED_RULE_FM_KEYS = {"trigger"}
OPTIONAL_RULE_FM_KEYS = {"description", "globs", "glob"}

INTERNAL_COMMITTEE_SKILLS = (
    "style-python",
    "style-go",
    "style-js",
    "style-cpp",
    "style-java",
    "style-rust",
    "markdown-style-expert",
    "security-auditor",
    "skill-evolve",
    "cortex-librarian",
)

REQUIRED_FM_KEYS = {"name", "description"}
OPTIONAL_FM_KEYS = {
    "disable-slash-command",
    "metadata",
    "compatibility",
    "license",
    "allowed-tools",
}


ALLOWED_PLUGIN_FIELDS = {
    "$schema",
    "name",
    "description",
    "logo",
    "suggestedPrompts",
    "displayName",
    "version",
    "disabled",
}
PLUGIN_SCHEMA_URL = "https://antigravity.google/schemas/v1/plugin.json"

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
    missing = REQUIRED_FM_KEYS - keys
    unknown = keys - (REQUIRED_FM_KEYS | OPTIONAL_FM_KEYS)
    if missing or unknown:
        violations.append(
            "%s: frontmatter keys must be {name, description} (+ optional disable-slash-command), got %s"
            % (label, sorted(keys))
        )
    if "disable-slash-command" in mapping and mapping["disable-slash-command"] not in {
        "true",
        "false",
    }:
        violations.append(
            "%s: disable-slash-command must be 'true' or 'false', got %r"
            % (label, mapping["disable-slash-command"])
        )
    name = mapping.get("name", "")
    if "name" in mapping and (len(name) > 64 or not NAME_RE.fullmatch(name)):
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


def parse_rule_frontmatter(data, label):
    """Parse a modular .agents/rules/*.md byte payload. Returns (mapping_or_None, violations)."""
    violations = []
    kind = bom_kind(data)
    if kind:
        return None, ["%s: leading %s" % (label, kind)]
    if b"\r" in data:
        violations.append("%s: CRLF line endings (canonical form is LF)" % label)
    if len(data) > RULE_FILE_MAX_BYTES:
        violations.append(
            "%s: size %d bytes exceeds %d-byte rule file cap"
            % (label, len(data), RULE_FILE_MAX_BYTES)
        )
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
        stripped = line.rstrip("\r")
        match = FM_LINE_RE.fullmatch(stripped)
        if not match:
            violations.append("%s: malformed frontmatter line %r" % (label, line))
            continue
        key, raw_value = match.group(1), (match.group(2) or "").strip()
        if key in mapping:
            violations.append("%s: duplicate frontmatter key %r" % (label, key))
        if key in {"globs", "glob"} and raw_value.startswith("*"):
            violations.append(
                "%s: %s pattern starting with '*' must be quoted in YAML frontmatter, got %r"
                % (label, key, raw_value)
            )
        if (
            len(raw_value) >= 2
            and raw_value[0] in {'"', "'"}
            and raw_value[-1] == raw_value[0]
        ):
            raw_value = raw_value[1:-1]
        mapping[key] = raw_value

    keys = set(mapping)
    missing = REQUIRED_RULE_FM_KEYS - keys
    unknown = keys - (REQUIRED_RULE_FM_KEYS | OPTIONAL_RULE_FM_KEYS)
    if missing or unknown:
        violations.append(
            "%s: rule frontmatter keys must include 'trigger' (+ optional description, globs, glob), got %s"
            % (label, sorted(keys))
        )
    trigger = mapping.get("trigger", "")
    if "trigger" in mapping and trigger not in VALID_RULE_TRIGGERS:
        violations.append(
            "%s: invalid trigger %r (must be one of %s)"
            % (label, trigger, sorted(VALID_RULE_TRIGGERS))
        )
    desc = mapping.get("description", "")
    if trigger == "model_decision" and not desc:
        violations.append(
            "%s: trigger 'model_decision' requires a non-empty description" % label
        )
    if "description" in mapping:
        if not desc:
            violations.append("%s: empty description" % label)
        if len(desc) > 1024:
            violations.append("%s: description exceeds 1024 chars" % label)
        if XML_TAG_RE.search(desc):
            violations.append("%s: description contains an XML tag" % label)
    if trigger == "glob":
        glob_val = mapping.get("globs") or mapping.get("glob") or ""
        if not glob_val.strip():
            violations.append(
                "%s: trigger 'glob' requires a non-empty 'globs' or 'glob' pattern"
                % label
            )
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
        if candidate in {
            ".agents/skills",
            ".agents/hooks",
            ".agents/tests",
            ".agents/scripts",
            ".agents/rules",
        }:
            continue
        results.append(candidate)
    return sorted(set(results))


def extract_relative_md_links(text):
    """Extract relative Markdown file links from skill documentation."""
    links = []
    for match in RELATIVE_MD_LINK_RE.finditer(text):
        target = match.group(1).strip()
        if not target or "<" in target or ">" in target or "[" in target:
            continue
        links.append(target)
    return sorted(set(links))


MCP_SECRET_KEY_RE = re.compile(
    r"(?i)(?:api[_-]?key|secret|token|password|passwd|auth|credential)"
)
MCP_SECRET_VALUE_RE = re.compile(
    r"(?:sk-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AIzaSy[A-Za-z0-9_-]{20,}|GOCSPX-[A-Za-z0-9_-]{16,}|fc-[a-f0-9]{20,}|tvly-[A-Za-z0-9_-]{16,})"
)
MCP_URL_SECRET_RE = re.compile(
    r"(?i)[?&](?:[a-z0-9_]*(?:key|token|secret|password|auth)[a-z0-9_]*)=([^&#\s]+)"
)
MCP_USER_PATH_RE = re.compile(r"(?i)(?:[A-Z]:\\Users\\|/Users/|/home/)")


def validate_mcp_config(data, label, allow_user_paths=False):
    """Validate mcp_config.json schema, portability, and absence of plaintext secrets."""
    violations = []
    if not isinstance(data, dict):
        return ["INV-2: %s: top-level JSON value must be an object" % label]
    unknown_top = sorted(set(data.keys()) - {"mcpServers"})
    if unknown_top:
        violations.append(
            "INV-2: %s: unsupported top-level keys %s" % (label, unknown_top)
        )
    servers = data.get("mcpServers")
    if not isinstance(servers, dict) or not servers:
        violations.append(
            "INV-2: %s: 'mcpServers' must be a non-empty object" % label
        )
        return violations
    if "chiasmus" in servers:
        violations.append(
            "INV-2: %s: contains broken 'chiasmus' MCP server entry" % label
        )
    for srv_name, cfg in servers.items():
        if len(srv_name) > 64 or not NAME_RE.fullmatch(srv_name):
            violations.append(
                "INV-2: %s: invalid server name %r" % (label, srv_name)
            )
        if not isinstance(cfg, dict):
            violations.append(
                "INV-2: %s: server %r config must be an object" % (label, srv_name)
            )
            continue
        has_cmd = isinstance(cfg.get("command"), str) and bool(cfg["command"].strip())
        url_val = cfg.get("serverUrl") or cfg.get("url")
        has_url = isinstance(url_val, str) and bool(url_val.strip())
        if has_cmd == has_url:
            violations.append(
                "INV-2: %s: server %r must specify exactly one of 'command' or 'serverUrl'/'url'"
                % (label, srv_name)
            )
        if has_cmd and not allow_user_paths and MCP_USER_PATH_RE.search(cfg["command"]):
            violations.append(
                "INV-2: %s: server %r command contains hardcoded user path"
                % (label, srv_name)
            )
        if has_url:
            if MCP_URL_SECRET_RE.search(url_val) or MCP_SECRET_VALUE_RE.search(url_val):
                violations.append(
                    "INV-2: %s: server %r URL contains plaintext secret"
                    % (label, srv_name)
                )
        if "args" in cfg:
            args_val = cfg["args"]
            if not isinstance(args_val, list) or not all(
                isinstance(a, str) for a in args_val
            ):
                violations.append(
                    "INV-2: %s: server %r 'args' must be a list of strings"
                    % (label, srv_name)
                )
            else:
                for a in args_val:
                    if not allow_user_paths and MCP_USER_PATH_RE.search(a):
                        violations.append(
                            "INV-2: %s: server %r arg contains hardcoded user path"
                            % (label, srv_name)
                        )
                    if MCP_SECRET_VALUE_RE.search(a):
                        violations.append(
                            "INV-2: %s: server %r arg contains plaintext secret"
                            % (label, srv_name)
                        )
                if has_cmd and cfg["command"].strip().lower() in {
                    "npx",
                    "npx.cmd",
                    "uvx",
                    "pipx",
                }:
                    pkg_args = [
                        a.strip()
                        for a in args_val
                        if a.strip() and not a.strip().startswith("-") and a.strip() != "run"
                    ]
                    if not pkg_args or (
                        pkg_args[0].rfind("@") <= 0 and "==" not in pkg_args[0]
                    ):
                        violations.append(
                            "INV-2: %s: server %r uses unpinned supply-chain package %r (mcp-unpinned-supply-chain)"
                            % (label, srv_name, pkg_args[0] if pkg_args else "")
                        )
        for map_key in ("env", "headers"):
            if map_key not in cfg:
                continue
            env_map = cfg[map_key]
            if not isinstance(env_map, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in env_map.items()
            ):
                violations.append(
                    "INV-2: %s: server %r %r must map strings to strings"
                    % (label, srv_name, map_key)
                )
                continue
            for k, v in env_map.items():
                if v == "__REDACTED_IN_WINVAULT__" or v.startswith("${") or v.startswith("{{"):
                    continue
                if not allow_user_paths and MCP_USER_PATH_RE.search(v):
                    violations.append(
                        "INV-2: %s: server %r %s[%r] contains hardcoded user path"
                        % (label, srv_name, map_key, k)
                    )
                if MCP_SECRET_VALUE_RE.search(v) or (
                    MCP_SECRET_KEY_RE.search(k) and len(v.strip()) >= 8
                ):
                    violations.append(
                        "INV-2: %s: server %r %s[%r] contains plaintext secret"
                        % (label, srv_name, map_key, k)
                    )
    return violations


VALID_AGENT_MODELS = {"inherit", "flash", "flash_lite", "pro"}
VALID_AGENT_EXEC_POLICIES = {"off", "auto", "eager", "sandbox"}
KNOWN_AGENT_TOOLS = {
    "view_file",
    "write_to_file",
    "replace_file_content",
    "run_command",
    "manage_task",
    "send_message",
    "invoke_subagent",
    "define_subagent",
    "manage_subagents",
    "schedule",
    "search_web",
    "read_url_content",
    "ask_question",
    "call_mcp_tool",
    "list_resources",
    "read_resource",
    "grep_search",
    "find_by_name",
}


def validate_custom_agent_frontmatter(data, label, expected_name=None):
    """Validate declarative .agents/agents/<name>.md YAML frontmatter against subagents.md."""
    violations = []
    if data.startswith(b"\xef\xbb\xbf"):
        violations.append("%s: UTF-8 BOM detected" % label)
    if b"\r\n" in data:
        violations.append("%s: CRLF line endings detected" % label)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        return ["%s: invalid UTF-8 (%s)" % (label, exc)]
    lines = text.split("\n")
    if len(lines) < 3 or lines[0] != "---":
        return ["%s: missing opening --- frontmatter fence" % label]
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i] == "---":
            end_idx = i
            break
    if end_idx is None:
        return ["%s: missing closing --- frontmatter fence" % label]

    mapping = {}
    for line in lines[1:end_idx]:
        if not line.strip():
            continue
        m = re.match(r"([A-Za-z][A-Za-z0-9_-]*):(?:\s+(.*))?", line)
        if not m:
            violations.append("%s: malformed frontmatter line %r" % (label, line))
            continue
        k, v = m.group(1), (m.group(2) or "").strip()
        if k in mapping:
            violations.append("%s: duplicate frontmatter key %r" % (label, k))
        mapping[k] = v

    for req_k in ("name", "description"):
        if not mapping.get(req_k):
            violations.append("%s: missing required frontmatter key %r" % (label, req_k))

    name_val = mapping.get("name", "")
    if name_val:
        if len(name_val) > 64 or not NAME_RE.fullmatch(name_val):
            violations.append("%s: invalid agent name %r" % (label, name_val))
        if expected_name and name_val != expected_name:
            violations.append(
                "%s: agent name %r != expected %r" % (label, name_val, expected_name)
            )

    if "model" in mapping and mapping["model"] not in VALID_AGENT_MODELS:
        violations.append(
            "%s: invalid model %r (must be one of %s)"
            % (label, mapping["model"], sorted(VALID_AGENT_MODELS))
        )

    if (
        "commandExecutionPolicy" in mapping
        and mapping["commandExecutionPolicy"] not in VALID_AGENT_EXEC_POLICIES
    ):
        violations.append(
            "%s: invalid commandExecutionPolicy %r (must be one of %s)"
            % (
                label,
                mapping["commandExecutionPolicy"],
                sorted(VALID_AGENT_EXEC_POLICIES),
            )
        )

    if "tools" in mapping:
        raw_tools = mapping["tools"].strip()
        if raw_tools.startswith("[") and raw_tools.endswith("]"):
            inner = raw_tools[1:-1].strip()
            tool_items = (
                [t.strip().strip("\"'") for t in inner.split(",") if t.strip()]
                if inner
                else []
            )
            for t_name in tool_items:
                if t_name == "moma_search":
                    violations.append(
                        "%s: forbidden internal tool 'moma_search' in tools list"
                        % label
                    )
                elif t_name not in KNOWN_AGENT_TOOLS:
                    violations.append(
                        "%s: unmapped tool %r in tools list (risks subagent hang per subagents.md)"
                        % (label, t_name)
                    )
        else:
            violations.append(
                "%s: 'tools' must be an inline YAML list [...]" % label
            )
    return violations


ALLOWED_SIDECAR_FIELDS = {
    "command",
    "builtin",
    "args",
    "restart_policy",
    "display_name",
    "description",
    "env",
    "agent_permissions",
    "has_web_ui",
    "ui_config",
}
VALID_SIDECAR_RESTART_POLICIES = {"always", "on-failure", "never"}
FORBIDDEN_SIDECAR_GRANTS = {
    "command(*)",
    "read_file(*)",
    "read_file(/)",
    "write_file(*)",
    "write_file(/)",
    "mcp(*)",
    "read_url(*)",
    "allow(*)",
}


def validate_sidecar_manifest(data, label):
    """Validate a sidecar.json manifest against Antigravity sidecar & automation specs."""
    violations = []
    if not isinstance(data, dict):
        return ["INV-2: %s: sidecar.json root must be a JSON object" % label]
    unknown = sorted(set(data.keys()) - ALLOWED_SIDECAR_FIELDS)
    if unknown:
        violations.append(
            "INV-2: %s: unsupported or non-snake_case top-level fields %s"
            % (label, unknown)
        )
    has_cmd = bool(data.get("command"))
    has_builtin = bool(data.get("builtin"))
    if has_cmd == has_builtin:
        violations.append(
            "INV-2: %s: 'command' and 'builtin' are mutually exclusive (specify exactly one)"
            % label
        )
    if (
        "restart_policy" in data
        and data["restart_policy"] not in VALID_SIDECAR_RESTART_POLICIES
    ):
        violations.append(
            "INV-2: %s: invalid restart_policy %r"
            % (label, data["restart_policy"])
        )
    if data.get("builtin") == "schedule":
        args = data.get("args")
        if (
            not isinstance(args, list)
            or len(args) < 5
            or not str(args[0]).startswith("CRON_TZ=")
            or "--" not in args
        ):
            violations.append(
                "INV-2: %s: builtin 'schedule' args must start with 'CRON_TZ=<IANA_Zone>' and include '--'"
                % label
            )
    if "agent_permissions" in data:
        perms = data["agent_permissions"]
        grants = perms.get("access_grants", []) if isinstance(perms, dict) else []
        for grant in grants:
            g_str = str(grant).strip()
            if (
                g_str in FORBIDDEN_SIDECAR_GRANTS
                or g_str.startswith("allow(")
                or "(*)" in g_str
            ):
                violations.append(
                    "INV-2: %s: forbidden wildcard or wrapper in access_grants: %r"
                    % (label, grant)
                )
    if data.get("has_web_ui") is True:
        ui_cfg = data.get("ui_config")
        views = ui_cfg.get("views", []) if isinstance(ui_cfg, dict) else []
        if not views or not all(
            isinstance(v, dict)
            and v.get("entrypoint") == "SIDECAR_UI_ENTRYPOINT_AUX_PANE"
            for v in views
        ):
            violations.append(
                "INV-2: %s: has_web_ui=true requires ui_config.views with entrypoint 'SIDECAR_UI_ENTRYPOINT_AUX_PANE'"
                % label
            )
    return violations


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
        if mapping and "description" in mapping:
            for trig_err in check_skill_description_triggers(mapping["description"], label):
                violations.append("INV-1: %s" % trig_err)
        if (
            mapping
            and skill_file.parent.name in INTERNAL_COMMITTEE_SKILLS
            and mapping.get("disable-slash-command") != "true"
        ):
            violations.append(
                "INV-1: %s: internal committee skill must set disable-slash-command: true"
                % label
            )
    agents_dir = root / ".agents" / "agents"
    if agents_dir.is_dir():
        for agent_md in sorted(agents_dir.glob("*.md")):
            label = _rel(root, agent_md)
            for err in validate_custom_agent_frontmatter(
                agent_md.read_bytes(), label, expected_name=agent_md.stem
            ):
                violations.append("INV-1: %s" % err)
    return violations


def check_inv2_json_and_paths(root):
    violations = []
    required_json = (
        root / ".agents" / "hooks.json",
        root / ".agents" / "mcp_config.json",
        root / ".agents" / "plugins" / "antigravity-core" / "plugin.json",
    )
    root_mcp = root / ".mcp.json"
    if root_mcp.is_file():
        try:
            violations.extend(
                validate_mcp_config(_load_json(root_mcp), ".mcp.json", allow_user_paths=False)
            )
        except (ValueError, UnicodeDecodeError) as exc:
            violations.append("INV-2: .mcp.json: %s" % exc)
    for path in required_json:
        label = _rel(root, path)
        if not path.is_file():
            violations.append("INV-2: %s: missing" % label)
            continue
        try:
            data = _load_json(path)
            if path.name == "mcp_config.json":
                violations.extend(
                    validate_mcp_config(data, label, allow_user_paths=False)
                )
            elif path.name == "plugin.json":
                unknown = sorted(set(data.keys()) - ALLOWED_PLUGIN_FIELDS)
                if unknown:
                    violations.append(
                        "INV-2: %s: unsupported top-level fields %s" % (label, unknown)
                    )
                if data.get("$schema") != PLUGIN_SCHEMA_URL:
                    violations.append(
                        "INV-2: %s: '$schema' must be %r"
                        % (label, PLUGIN_SCHEMA_URL)
                    )
                name_val = data.get("name", "")
                if not isinstance(name_val, str) or not NAME_RE.fullmatch(
                    name_val
                ):
                    violations.append(
                        "INV-2: %s: 'name' must be lowercase kebab-case" % label
                    )
                desc_val = data.get("description", "")
                if not isinstance(desc_val, str) or not desc_val.strip():
                    violations.append(
                        "INV-2: %s: 'description' must be a non-empty string" % label
                    )
                prompts = data.get("suggestedPrompts")
                if prompts is not None and (
                    not isinstance(prompts, list)
                    or len(prompts) == 0
                    or len(prompts) > 3
                    or not all(isinstance(p, str) and p.strip() for p in prompts)
                ):
                    violations.append(
                        "INV-2: %s: 'suggestedPrompts' must be 1..3 non-empty strings"
                        % label
                    )
                if data.get("disabled") is not True:
                    violations.append(
                        "INV-2: %s: must set disabled=true in source repo checkout"
                        % label
                    )
        except (ValueError, UnicodeDecodeError) as exc:
            violations.append("INV-2: %s: %s" % (label, exc))

    for sidecar_path in sorted((root / ".agents").rglob("sidecar.json")):
        if not sidecar_path.is_file():
            continue
        s_label = _rel(root, sidecar_path)
        try:
            s_data = _load_json(sidecar_path)
            violations.extend(validate_sidecar_manifest(s_data, s_label))
        except (ValueError, UnicodeDecodeError) as exc:
            violations.append("INV-2: %s: %s" % (s_label, exc))

    skill_md_targets = sorted((root / ".agents" / "skills").rglob("*.md"))
    md_targets = [root / ".agents" / "AGENTS.md"] + list(skill_md_targets)
    rules_dir = root / ".agents" / "rules"
    if rules_dir.is_dir():
        md_targets.extend(sorted(rules_dir.glob("*.md")))
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
        if md_path in skill_md_targets:
            for rel_link in extract_relative_md_links(text):
                resolved_target = (md_path.parent / rel_link).resolve()
                if not resolved_target.exists():
                    violations.append(
                        "INV-2: %s: relative link %r does not exist"
                        % (label, rel_link)
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
            if event_name == "enabled":
                if not isinstance(entries, bool):
                    violations.append(
                        "INV-3: %s: hook group %r 'enabled' must be a boolean"
                        % (label, group_name)
                    )
                continue
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
            continue
        script_text = target.read_bytes().decode("utf-8", errors="replace")
        if script_text.strip().startswith("# mock"):
            continue
        if script_name == "brc-guard.ps1":
            for rule_id in REQUIRED_BRC_GUARD_RULES:
                if rule_id not in script_text:
                    violations.append(
                        "INV-3: .agents/hooks/%s: missing required rule ID %r"
                        % (script_name, rule_id)
                    )
            if "[chain:" not in script_text:
                violations.append(
                    "INV-3: .agents/hooks/%s: missing SHA-256 telemetry chain tag"
                    % script_name
                )
        elif script_name == "telemetry-append.ps1":
            for marker in REQUIRED_TELEMETRY_MARKERS:
                if marker not in script_text:
                    violations.append(
                        "INV-3: .agents/hooks/%s: missing causal marker %r"
                        % (script_name, marker)
                    )
            if "[chain:" not in script_text:
                violations.append(
                    "INV-3: .agents/hooks/%s: missing SHA-256 telemetry chain tag"
                    % script_name
                )
    return violations


def check_inv4_pipeline_skills(root):
    violations = []
    agents_md = root / ".agents" / "AGENTS.md"
    if not agents_md.is_file():
        return ["INV-4: .agents/AGENTS.md missing"]
    raw_bytes = agents_md.read_bytes()
    if len(raw_bytes) > AGENTS_MD_MAX_BYTES:
        violations.append(
            "INV-4: .agents/AGENTS.md size %d bytes exceeds %d-byte non-truncation cap"
            % (len(raw_bytes), AGENTS_MD_MAX_BYTES)
        )
    if raw_bytes.startswith(b"---"):
        violations.append(
            "INV-4: .agents/AGENTS.md must not start with a YAML frontmatter fence '---'"
        )
    text = raw_bytes.decode("utf-8", errors="replace").lower()
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

    rules_dir = root / ".agents" / "rules"
    if rules_dir.is_dir():
        has_rules_json = (root / ".agents" / "rules.json").is_file()
        for child in sorted(rules_dir.iterdir()):
            if child.is_dir() and not has_rules_json:
                violations.append(
                    "INV-4: %s: nested subdirectory inside .agents/rules is ignored without .agents/rules.json"
                    % _rel(root, child)
                )
        for rule_file in sorted(rules_dir.glob("*.md")):
            label = _rel(root, rule_file)
            _, errors = parse_rule_frontmatter(rule_file.read_bytes(), label)
            violations.extend("INV-4: %s" % e for e in errors)
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
        if len(bullets) > 10:
            violations.append(
                "INV-7: %s: contains %d heuristics (exceeds 10-heuristic cap; deduplicate first)"
                % (label, len(bullets))
            )
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



def check_inv10_skill_security(root):
    violations = []
    skills_dir = root / ".agents" / "skills"
    targets = list(skills_dir.rglob("SKILL.md")) + list(
        skills_dir.rglob("*-edge-cases.md")
    )
    rules_dir = root / ".agents" / "rules"
    if rules_dir.is_dir():
        targets.extend(rules_dir.glob("*.md"))
    for path in sorted(set(targets)):
        if not path.is_file():
            continue
        label = _rel(root, path)
        text = path.read_bytes().decode("utf-8", errors="replace")
        for err in scan_skill_security(text, label):
            violations.append("INV-10: %s" % err)
    for test_py in sorted((root / ".agents" / "tests").glob("test_*.py")):
        t_label = _rel(root, test_py)
        t_text = test_py.read_bytes().decode("utf-8", errors="replace")
        for t_err in scan_test_integrity(t_text, t_label):
            violations.append("INV-10: %s" % t_err)
    tel_file = root / ".agents" / "agentic_telemetry.md"
    if tel_file.is_file():
        tel_label = _rel(root, tel_file)
        tel_text = tel_file.read_bytes().decode("utf-8", errors="replace")
        for c_err in verify_telemetry_chain(tel_text, tel_label):
            violations.append("INV-10: %s" % c_err)
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
