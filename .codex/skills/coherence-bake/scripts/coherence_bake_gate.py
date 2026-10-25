"""Deterministic Diminishing-Returns & Full-System Coherence Bake Gate.

Evaluates cross-layer AST producer-consumer audits, formal Z3/SMT state
proofs, whole-repository file coverage ledgers, generative surface audits,
and candidate findings across four first-class dimensions:
1. COHERENCE_CONTRACT (cross-layer producer-consumer seams & schema fidelity)
2. SYSTEM_DESIGN (modularity, concurrency, bulkhead & complexity hotspots)
3. OPTIMIZATION (asymptotic complexity, query plans, vectorization & I/O)
4. SOTA_BENCHMARK (peer-reviewed literature & production OSS benchmarks)

Emits a tri-state verdict:
- `INCOMPLETE_AUDIT_RETRY` (exit code 2): audit manifest, file coverage ledger,
  or unreported surface gaps are incomplete.
- `PROCEED_FIX` (exit code 0): 100% file coverage ledger verified and >= 1
  verified finding requires remediation.
- `AIRTIGHT_HALT` (exit code 0): 0 verified findings, 0 AST/surface gaps, Z3
  SAT, 100% CLEAN file coverage ledger, fixed-point wave_history, and valid
  on-disk Phase 5 red-team receipt and transcript.

Usage:
    python coherence_bake_gate.py <ast> <z3> <findings> <out> --repo-root <d>
    python coherence_bake_gate.py --build-ledger <repo_root> <out_json>
    python coherence_bake_gate.py --audit-repo <repo_root>
    python coherence_bake_gate.py --self-test
"""
import argparse
import ast
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

VALID_CATEGORIES: Tuple[str, ...] = (
    "COHERENCE_CONTRACT",
    "SYSTEM_DESIGN",
    "OPTIMIZATION",
    "SOTA_BENCHMARK",
)
REQUIRED_AUDIT_SURFACES: Tuple[str, ...] = (
    "config_to_runtime_hooks",
    "prompt_to_gate_schemas",
    "single_to_multi_composition",
    "cross_tree_and_doc_parity",
)
EXCLUDED_WALK_DIRS: Set[str] = {
    ".git",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "scratch",
    "chroma_db",
    "chroma_data",
    "fpcalc_dir",
    ".next",
    "dist",
    "build",
    "coverage",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".claude",
}
BINARY_EXTENSIONS: Set[str] = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".pyc",
    ".db",
    ".sqlite",
    ".sqlite3",
}

_FILE_LINE_RE = re.compile(r"^(?P<path>.+?):(?P<start>\d+)(?:-(?P<end>\d+))?$")
_MD_IMAGE_EXFIL_RE = re.compile(r"!\[[^\]]*\]\(\s*https?://", re.IGNORECASE)
_INVISIBLE_CHAR_RE = re.compile(
    r"[\u200b-\u200d\u202a-\u202e\u2060-\u2064\ufeff\U000e0000-\U000e007f]"
)
_REL_MD_LINK_RE = re.compile(
    r"\[[^\]]+\]\((?!https?:|mailto:|file:|sidecar:|customization:|conversation:|#)([^)#\s]+)"
)
_JS_EXEC_INTERP_RE = re.compile(
    r"\bexec(?:Sync)?\s*\(\s*(?:`[^`]*\$\{|['\"][^'\"]*['\"]\s*\+)"
)
_RUBRIC_BLOCK_RE = re.compile(
    r"<RUBRIC_SCORE>\s*(\{[\s\S]*?\})\s*</RUBRIC_SCORE>"
)


def contains_smuggled_content(text: str) -> bool:
    """Return True if text has invisible Unicode or image exfiltration."""
    return bool(
        _MD_IMAGE_EXFIL_RE.search(text) or _INVISIBLE_CHAR_RE.search(text)
    )


def _inspect_strings_recursive(value: Any) -> bool:
    """Return True if any nested string inside value has smuggled content."""
    if isinstance(value, str):
        return contains_smuggled_content(value)
    if isinstance(value, Mapping):
        return any(
            _inspect_strings_recursive(k) or _inspect_strings_recursive(v)
            for k, v in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_inspect_strings_recursive(item) for item in value)
    return False


def _load_file_lines(
    resolved_target: Path,
    line_cache: Optional[Dict[Path, List[str]]] = None,
) -> Optional[List[str]]:
    """Load and cache UTF-8 lines for resolved_target, or None on OSError."""
    if line_cache is not None and resolved_target in line_cache:
        return line_cache[resolved_target]
    try:
        content = resolved_target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    lines = content.splitlines()
    if line_cache is not None:
        line_cache[resolved_target] = lines
    return lines


def compute_slice_sha256(
    file_path: Path,
    start_line: int,
    end_line: int,
    line_cache: Optional[Dict[Path, List[str]]] = None,
) -> str:
    """Compute SHA-256 hex digest of 1-indexed lines [start_line..end_line]."""
    lines = _load_file_lines(file_path, line_cache=line_cache) or []
    selected = "\n".join(lines[start_line - 1 : end_line])
    return hashlib.sha256(selected.encode("utf-8")).hexdigest()


def _parse_line_spec(
    file_and_line: Any,
) -> Tuple[Optional[Tuple[str, int, int]], str]:
    """Parse `<path>:<start>[-<end>]` into `(raw_path, start, end)`."""
    if not isinstance(file_and_line, str) or not file_and_line.strip():
        return None, "missing_file_and_line"
    match = _FILE_LINE_RE.match(file_and_line.strip())
    if not match:
        return None, "invalid_file_and_line_format"
    raw_path = match.group("path").strip()
    start_line = int(match.group("start"))
    end_grp = match.group("end")
    end_line = int(end_grp) if end_grp else start_line
    if start_line < 1 or end_line < start_line:
        return None, "invalid_line_range"
    return (raw_path, start_line, end_line), "ok"


def _resolve_repo_file(
    raw_path: str,
    repo_root: Path,
) -> Tuple[Optional[Path], str]:
    """Resolve raw_path strictly inside repo_root and verify it is a file."""
    resolved_root = repo_root.resolve()
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = resolved_root / candidate
    try:
        resolved_target = candidate.resolve(strict=True)
        resolved_target.relative_to(resolved_root)
    except (OSError, ValueError):
        return None, "path_outside_repo_or_missing"
    if not resolved_target.is_file():
        return None, "target_not_a_file"
    return resolved_target, "ok"


def validate_file_and_line(
    file_and_line: str,
    repo_root: Path,
    sha256_anchor: Optional[str] = None,
    line_cache: Optional[Dict[Path, List[str]]] = None,
) -> Tuple[bool, str]:
    """Validate `<path>:<start>[-<end>]` containment inside repo_root."""
    parsed, reason = _parse_line_spec(file_and_line)
    if parsed is None:
        return False, reason
    raw_path, start_line, end_line = parsed

    resolved_target, path_reason = _resolve_repo_file(raw_path, repo_root)
    if resolved_target is None:
        return False, path_reason

    lines = _load_file_lines(resolved_target, line_cache=line_cache)
    if lines is None:
        return False, "target_unreadable"
    if end_line > len(lines):
        return False, "line_range_out_of_bounds"

    if sha256_anchor is not None and sha256_anchor != "":
        expected = compute_slice_sha256(
            resolved_target, start_line, end_line, line_cache=line_cache
        )
        if sha256_anchor.strip().lower() != expected.lower():
            return False, "sha256_anchor_mismatch"
    return True, "ok"


def _is_nonempty_str(value: Any) -> bool:
    """Return True if value is a non-empty, non-whitespace string."""
    return isinstance(value, str) and bool(value.strip())


def _check_finding_flags(normalized: Dict[str, Any]) -> Optional[str]:
    """Validate scalar flags and required string fields on a finding dict."""
    if not _is_nonempty_str(normalized.get("id")):
        return "missing_finding_id"
    is_spec = normalized.get("is_speculative")
    if not isinstance(is_spec, bool) or is_spec is not False:
        return "speculative_or_missing_flag"
    gain_eps = normalized.get("measurable_gain_above_epsilon")
    if not isinstance(gain_eps, bool) or gain_eps is not True:
        return "below_diminishing_returns_epsilon"
    category = str(normalized.get("category", "COHERENCE_CONTRACT")).strip()
    if category not in VALID_CATEGORIES:
        return "invalid_category"
    normalized["category"] = category
    if not _is_nonempty_str(normalized.get("reproducible_check")):
        return "missing_reproducible_check"
    if not _is_nonempty_str(normalized.get("falsifiable_fix")):
        return "missing_falsifiable_fix"
    return None


def _check_sota_fields(normalized: Mapping[str, Any]) -> Optional[str]:
    """Validate mandatory citation and https:// URL on SOTA_BENCHMARK items."""
    if normalized.get("category") != "SOTA_BENCHMARK":
        return None
    citation = normalized.get("citation_author_year") or normalized.get(
        "sota_citation"
    )
    if not _is_nonempty_str(citation):
        return "missing_sota_citation"
    url = normalized.get("verified_url")
    if not _is_nonempty_str(url) or not str(url).strip().startswith(
        "https://"
    ):
        return "invalid_sota_verified_url"
    return None


def _is_valid_bars_int(val: Any) -> bool:
    """Return True if val is an integer in 0..3 and not a boolean."""
    return not isinstance(val, bool) and isinstance(val, int) and 0 <= val <= 3


def _check_rubric_scores(normalized: Mapping[str, Any]) -> Optional[str]:
    """Validate optional BARS rubric_scores on a candidate finding."""
    rubric = normalized.get("rubric_scores")
    if rubric is None:
        return None
    if not isinstance(rubric, Mapping) or len(rubric) < 3:
        return "finding_rubric_below_threshold"
    values = list(rubric.values())
    if not all(_is_valid_bars_int(val) for val in values):
        return "finding_rubric_below_threshold"
    scores = [int(val) for val in values]
    min_req = int(math.ceil(0.75 * 3.0 * len(scores)))
    if min(scores) < 2 or sum(scores) < min_req:
        return "finding_rubric_below_threshold"
    return None


def _check_all_finding_constraints(
    normalized: Dict[str, Any],
) -> Optional[str]:
    """Run smuggled content, flag, SOTA, and rubric checks on a finding."""
    if _inspect_strings_recursive(normalized):
        return "smuggled_unicode_or_markdown_exfil"
    err = _check_finding_flags(normalized)
    if err is not None:
        return err
    err = _check_sota_fields(normalized)
    if err is not None:
        return err
    err = _check_rubric_scores(normalized)
    if err is not None:
        return err
    sha_anchor = normalized.get("sha256_anchor")
    if sha_anchor is not None and not isinstance(sha_anchor, str):
        return "invalid_sha256_anchor_type"
    return None


def validate_finding(
    item: Any,
    repo_root: Path,
    line_cache: Optional[Dict[Path, List[str]]] = None,
) -> Tuple[bool, str, Dict[str, Any]]:
    """Validate a candidate finding against the Diminishing-Returns Gate."""
    if not isinstance(item, Mapping):
        return False, "finding_not_an_object", {"raw": str(item)}

    normalized = dict(item)
    err = _check_all_finding_constraints(normalized)
    if err is not None:
        return False, err, normalized

    ok_loc, loc_reason = validate_file_and_line(
        str(normalized.get("file_and_line", "")),
        repo_root=repo_root,
        sha256_anchor=normalized.get("sha256_anchor"),
        line_cache=line_cache,
    )
    if not ok_loc:
        return False, loc_reason, normalized
    return True, "ok", normalized


def _non_negative_count(value: Any) -> int:
    """Coerce an AST gap metric to a non-negative integer."""
    if isinstance(value, bool):
        return 1
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 1
    return abs(parsed)


def _is_test_rel_path(rel_path: str) -> bool:
    """Return True if rel_path is inside a tests directory or is a test module."""
    norm = str(rel_path).replace("\\", "/")
    path_obj = Path(norm)
    name = path_obj.name
    return (
        "tests" in path_obj.parts
        or name.startswith("test_")
        or name.endswith("_test.py")
        or name.endswith(".test.js")
    )


def _count_non_test_high_complexity(ast_data: Mapping[str, Any]) -> int:
    """Count non-test entries in ast_data['high_complexity_functions']."""
    items = ast_data.get("high_complexity_functions", [])
    if not isinstance(items, (list, tuple)):
        return 0
    count = 0
    for item in items:
        if isinstance(item, Mapping) and not _is_test_rel_path(
            str(item.get("file", ""))
        ):
            count += 1
    return count


def _matches_scope(rel_path: str, scope_prefix: str) -> bool:
    """Return True if rel_path is inside scope_prefix (empty or '.' matches 100% of repo)."""
    norm = scope_prefix.strip().replace("\\", "/").strip("/")
    if not norm or norm == ".":
        return True
    return rel_path == norm or rel_path.startswith(f"{norm}/")


def build_file_coverage_ledger(
    repo_root: Path,
    scope_prefix: str = "",
) -> Dict[str, Dict[str, str]]:
    """Walk repo_root and build a 100% SHA-256 ledger of scannable repo or feature files."""
    resolved_root = repo_root.resolve()
    ledger: Dict[str, Dict[str, str]] = {}
    for dirpath, dirnames, filenames in os.walk(resolved_root):
        dirnames[:] = sorted(
            d for d in dirnames if d not in EXCLUDED_WALK_DIRS
        )
        for fname in sorted(filenames):
            fpath = Path(dirpath) / fname
            if fpath.suffix.lower() in BINARY_EXTENSIONS or not fpath.is_file():
                continue
            rel = str(fpath.relative_to(resolved_root)).replace("\\", "/")
            if not _matches_scope(rel, scope_prefix):
                continue
            digest = hashlib.sha256(fpath.read_bytes()).hexdigest()
            ledger[rel] = {"sha256": digest, "status": "CLEAN"}
    return ledger


def _compute_ast_mccabe(func_node: ast.AST) -> int:
    """Compute McCabe cyclomatic complexity for an AST function node."""
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


def _extract_py_loaded_names(py_path: Path) -> Set[str]:
    """Return all AST Name load identifiers from a single Python file."""
    try:
        tree = ast.parse(py_path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError):
        return set()
    return {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }


def _collect_repo_loaded_names(repo_root: Path) -> Set[str]:
    """Collect all AST Name load identifiers across Python files in repo_root."""
    loaded: Set[str] = set()
    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_WALK_DIRS]
        for fname in filenames:
            if fname.endswith(".py"):
                loaded.update(_extract_py_loaded_names(Path(dirpath) / fname))
    return loaded


def _unused_upper_consts(
    tree: ast.Module,
    extra_loaded: Optional[Set[str]] = None,
) -> List[str]:
    """Return module-level UPPER_CASE constants never loaded in tree or extra_loaded."""
    defined: Set[str] = set()
    loaded: Set[str] = set(extra_loaded or ())
    for stmt in tree.body:
        targets = getattr(stmt, "targets", [getattr(stmt, "target", None)])
        for t_node in targets:
            if isinstance(t_node, ast.Name) and re.fullmatch(
                r"[A-Z][A-Z0-9_]{2,}", t_node.id
            ):
                defined.add(t_node.id)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            loaded.add(node.id)
    return sorted(defined - loaded)


def _audit_single_py_file(
    py_path: Path,
    rel_path: str,
    extra_loaded: Optional[Set[str]] = None,
) -> List[str]:
    """Audit a Python file for syntax, unused constants, and McCabe <= 9."""
    try:
        source = py_path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [f"{rel_path}: SyntaxError ({exc})"]
    gaps = [
        f"{rel_path}: unused constant {cname}"
        for cname in _unused_upper_consts(tree, extra_loaded=extra_loaded)
    ]
    if _is_test_rel_path(rel_path):
        return gaps
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            score = _compute_ast_mccabe(node)
            if score > 9:
                gaps.append(
                    f"{rel_path}: function {node.name} McCabe {score} > 9"
                )
    return gaps


def _audit_single_js_file(js_path: Path, rel_path: str) -> List[str]:
    """Audit a JS/TS file for CWE-78 shell command string interpolation."""
    if _is_test_rel_path(rel_path):
        return []
    text = js_path.read_text(encoding="utf-8", errors="replace")
    if _JS_EXEC_INTERP_RE.search(text):
        return [f"{rel_path}: CWE-78 interpolated exec/execSync call"]
    return []


def _check_md_phase_monotonicity(cleaned: str, rel_path: str) -> List[str]:
    """Verify Phase N headings inside a Markdown file are monotonically non-decreasing."""
    last_phase = 0
    for ln in cleaned.splitlines():
        if ln.startswith("#"):
            match = re.search(r"\bPhase\s+(\d+)\b", ln)
            if match:
                cur = int(match.group(1))
                if cur < last_phase:
                    return [f"{rel_path}: non-monotonic Phase heading {cur} < {last_phase}"]
                last_phase = cur
    return []


def _check_md_stale_claims(text: str, rel_path: str) -> List[str]:
    """Verify Markdown file does not contain stale pre-config paths or false exclusions."""
    stale_tokens = (
        "~/.gemini/GEMINI.md",
        "~/.gemini/antigravity/skills",
        "~/.gemini/antigravity/mcp_config.json",
        "omitted to avoid the Antigravity moma_" + "search",
    )
    return [
        f"{rel_path}: stale claim {tok}"
        for tok in stale_tokens
        if tok in text
    ]


def _audit_single_md_file(md_path: Path, rel_path: str) -> List[str]:
    """Audit a Markdown file for broken relative links, phase order, and stale claims."""
    text = md_path.read_text(encoding="utf-8", errors="replace")
    cleaned_fenced = re.sub(r"```[\s\S]*?```", "", text)
    cleaned = re.sub(r"`[^`\n]+`", "", cleaned_fenced)
    gaps: List[str] = []
    for match in _REL_MD_LINK_RE.finditer(cleaned):
        target = match.group(1).strip()
        if not target or "<" in target or ">" in target or "[" in target:
            continue
        if not (md_path.parent / target).resolve().exists():
            gaps.append(f"{rel_path}: broken relative link {target}")
    gaps.extend(_check_md_phase_monotonicity(cleaned_fenced, rel_path))
    gaps.extend(_check_md_stale_claims(text, rel_path))
    return gaps


def _extract_md_h2_headings(md_path: Path) -> List[str]:
    """Extract `## ` H2 headings outside fenced code blocks."""
    text = md_path.read_text(encoding="utf-8", errors="replace")
    cleaned = re.sub(r"```[\s\S]*?```", "", text)
    return [
        ln.strip()
        for ln in cleaned.splitlines()
        if ln.startswith("## ")
    ]


def _count_md_bullets(md_path: Path) -> int:
    """Count top-level `- ` bullet lines in a Markdown file."""
    return sum(
        1
        for ln in md_path.read_text(encoding="utf-8", errors="replace").splitlines()
        if ln.startswith("- ")
    )


def _compare_edge_case_pair(
    ag_ec: Path,
    peer_ec: Path,
    peer_label: str,
    ec_name: str,
) -> List[str]:
    """Compare companion edge-cases existence and bullet count across trees."""
    if ag_ec.is_file() != peer_ec.is_file():
        return [f"{peer_label}/{ec_name}: companion edge-cases drift"]
    if ag_ec.is_file() and _count_md_bullets(ag_ec) != _count_md_bullets(peer_ec):
        return [f"{peer_label}/{ec_name}: companion bullet-count drift"]
    return []


def _compare_skill_pair(
    ag_skill_dir: Path,
    peer_skill_dir: Path,
    peer_label: str,
) -> List[str]:
    """Compare H2 headings and companion files between two skill directories."""
    gaps: List[str] = []
    ag_md = ag_skill_dir / "SKILL.md"
    peer_md = peer_skill_dir / "SKILL.md"
    if not ag_md.is_file() or not peer_md.is_file():
        return gaps
    if _extract_md_h2_headings(ag_md) != _extract_md_h2_headings(peer_md):
        gaps.append(f"{peer_label}/SKILL.md: H2 heading drift vs canonical")
    ec_name = f"{ag_skill_dir.name}-edge-cases.md"
    gaps.extend(
        _compare_edge_case_pair(
            ag_skill_dir / ec_name,
            peer_skill_dir / ec_name,
            peer_label,
            ec_name,
        )
    )
    script_dir = ag_skill_dir / "scripts"
    for script_p in sorted(script_dir.glob("*.py")) if script_dir.is_dir() else ():
        peer_sp = peer_skill_dir / "scripts" / script_p.name
        if not peer_sp.is_file() or peer_sp.read_bytes() != script_p.read_bytes():
            gaps.append(f"{peer_label}/scripts/{script_p.name}: script SHA-256 drift")
    return gaps


def _audit_cross_tree_skill_parity(repo_root: Path) -> List[str]:
    """Audit shared skills across .agents, .claude, and .codex for structural parity."""
    ag_skills = repo_root / ("." + "agents") / "skills"
    if not ag_skills.is_dir():
        return []
    gaps: List[str] = []
    for tree_name in ("." + "claude", "." + "codex"):
        peer_skills = repo_root / tree_name / "skills"
        if not peer_skills.is_dir():
            continue
        for s_dir in sorted(ag_skills.iterdir()):
            peer_dir = peer_skills / s_dir.name
            if s_dir.is_dir() and peer_dir.is_dir():
                gaps.extend(
                    _compare_skill_pair(
                        s_dir, peer_dir, f"{tree_name}/skills/{s_dir.name}"
                    )
                )
    return gaps


def _check_agents_hook_surface(repo_root: Path) -> int:
    """Check present Antigravity hooks.json for mandatory subagent and search matchers."""
    ag_hooks = repo_root / ("." + "agents") / "hooks.json"
    if not ag_hooks.is_file():
        return 0
    txt = ag_hooks.read_text(encoding="utf-8", errors="replace")
    req = ("define_" + "subagent", "grep_" + "search", "manage_" + "task", "-NonInteractive")
    return _missing_token_count(txt, req)


def _check_claude_hook_surface(repo_root: Path) -> int:
    """Check present Claude settings.json for mandatory Grep and NonInteractive flags."""
    cl_settings = repo_root / ("." + "claude") / "settings.json"
    if not cl_settings.is_file():
        return 0
    txt = cl_settings.read_text(encoding="utf-8", errors="replace")
    return _missing_token_count(txt, ("Grep", "-NonInteractive", "spawn_agent"))


def _missing_token_count(text: str, required_tokens: Sequence[str]) -> int:
    """Return the count of required_tokens not present in text."""
    missing = 0
    for tok in required_tokens:
        if tok not in text:
            missing += 1
    return missing


def _check_single_tree_scripts(tree_root: Path) -> int:
    """Check brc-guard.ps1, telemetry-append.ps1, and validate_tree.py if present."""
    gaps = 0
    brc = tree_root / "hooks" / "brc-guard.ps1"
    if brc.is_file():
        gaps += _missing_token_count(
            brc.read_text(encoding="utf-8", errors="replace"),
            (
                "SearchPath",
                "SearchDirectory",
                "ReplacementChunks",
                "Get-WriteContentString",
                "AIRTIGHT_HALT",
                "PROCEED_FIX",
                "subagent-role-least-privilege",
                "explorer|research",
            ),
        )
    tel = tree_root / "hooks" / "telemetry-append.ps1"
    if tel.is_file():
        gaps += _missing_token_count(
            tel.read_text(encoding="utf-8", errors="replace"),
            (
                "Get-TranscriptAssistantText",
                "Remove-BacktickCodeSpans",
                "[VERDICT: PROCEED_FIX]",
            ),
        )
    vt_py = tree_root / "tests" / "validate_tree.py"
    if vt_py.is_file():
        gaps += _missing_token_count(
            vt_py.read_text(encoding="utf-8", errors="replace"),
            (
                "_compute_func_mccabe",
                "_check_rubric_schema_and_script_parity",
                "rules_dir",
                "[VERDICT: PROCEED_FIX]",
                "FORBIDDEN_PS1_CALL",
                "FORBIDDEN_CONTROL_BYTES",
            ),
        )
    return gaps


def _check_inventory_and_ci_surface(repo_root: Path) -> int:
    """Verify cross-tree cortex-librarian parity and CI self-test coverage when present."""
    gaps = 0
    ag_agents = repo_root / ("." + "agents") / "agents"
    if ag_agents.is_dir() and not (ag_agents / "cortex-librarian.md").is_file():
        gaps += 1
    cl_skills = repo_root / ("." + "claude") / "skills"
    if (
        cl_skills.is_dir()
        and not (cl_skills / "cortex-librarian" / "SKILL.md").is_file()
    ):
        gaps += 1
    ci_yml = repo_root / ".github" / "workflows" / "ci.yml"
    has_harness_tree = (
        repo_root / ("." + "agents") / "tests" / "validate_tree.py"
    ).is_file()
    if ci_yml.is_file() and has_harness_tree:
        gaps += _missing_token_count(
            ci_yml.read_text(encoding="utf-8", errors="replace"),
            (
                "coherence_bake_gate.py --self-test",
                "coherence_bake_gate.py --audit-repo .",
                "rubric_grade_gate.py --self-test",
                "mcp_keyring_launcher.py --self-test",
                "cortex_ingest.test.js",
            ),
        )
    return gaps


def _check_shared_script_parity(repo_root: Path) -> int:
    """Verify Stage 5 rubric verdicts and SHA-256 parity across harness trees."""
    ag_rgg = (
        repo_root
        / ("." + "agents")
        / "skills/comprehend-problem/scripts/rubric_grade_gate.py"
    )
    if not ag_rgg.is_file():
        return 0
    rgg_txt = ag_rgg.read_text(encoding="utf-8", errors="replace")
    gaps = _missing_token_count(rgg_txt, ("AIRTIGHT_HALT", "PROCEED_FIX"))
    for tree_name in ("." + "claude", "." + "codex"):
        peer = (
            repo_root
            / tree_name
            / "skills/comprehend-problem/scripts/rubric_grade_gate.py"
        )
        if peer.is_file() and peer.read_bytes() != ag_rgg.read_bytes():
            gaps += 1
    return gaps


def _legacy_hook_and_ci_gaps(repo_root: Path) -> List[str]:
    """Collect hook/CI/script token parity gaps across harness trees."""
    count = (
        _check_agents_hook_surface(repo_root)
        + _check_claude_hook_surface(repo_root)
        + _check_shared_script_parity(repo_root)
        + _check_inventory_and_ci_surface(repo_root)
    )
    for tree_name in ("." + "agents", "." + "claude", "." + "codex"):
        count += _check_single_tree_scripts(repo_root / tree_name)
    return [f"harness_surface_gap_{i}" for i in range(count)]


def _run_repo_ruff_check(repo_root: Path, pyproj_text: str) -> List[str]:
    """Run ruff check across 100% of repo_root when configured in pyproject.toml."""
    if "[tool.ruff" not in pyproj_text:
        return []
    cmd = [
        sys.executable,
        "-m",
        "ruff",
        "check",
        "--quiet",
        "--extend-exclude",
        "scratch",
        ".",
    ]
    try:
        proc = subprocess.run(
            cmd, cwd=str(repo_root), capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if proc.returncode == 0:
        return []
    return [
        f"ruff: {ln.strip()}"
        for ln in proc.stdout.splitlines()
        if ln.strip()
    ][:50]


def _get_git_tracked_files(
    repo_root: Path,
    extra_args: Sequence[str] = (),
) -> List[str]:
    """Return git ls-files relative paths when repo_root is a git repository."""
    if not (repo_root / ".git").exists():
        return []
    cmd = ["git", "-C", str(repo_root), "ls-files"] + list(extra_args)
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if proc.returncode != 0:
        return []
    return [
        ln.strip().replace("\\", "/")
        for ln in proc.stdout.splitlines()
        if ln.strip()
    ]


_ROOT_SCRATCH_ARTIFACTS: Set[str] = {
    "diff.txt",
    "test_output.txt",
    "preflight_test_output.txt",
    "compact_disk.txt",
    "stage0_rubric.md",
    "candidate_solutions_A_R.md",
}


def _audit_git_index_hygiene(repo_root: Path) -> List[str]:
    """Flag gitignored files and root scratch logs still tracked in git index."""
    ignored_tracked = set(
        _get_git_tracked_files(repo_root, ("-i", "--exclude-standard"))
    )
    gaps: List[str] = []
    for rel in _get_git_tracked_files(repo_root):
        if (
            rel in ignored_tracked
            or rel in _ROOT_SCRATCH_ARTIFACTS
            or rel.startswith(("scratch/", "chroma_db/"))
        ):
            gaps.append(f"{rel}: scratch or runtime artifact tracked in git index")
    return gaps


def _is_historical_plan_doc(rel: str) -> bool:
    """Return True if rel is an archived task log or invariant test fixture."""
    prefixes = (
        "docs/architecture/task.md",
        "tests/admin/test_cli.py",
    )
    return any(rel == p or rel.startswith(p) for p in prefixes)


def _has_stale_recommender_token(text: str) -> bool:
    """Return True if text contains stale references to deleted recommender/pp-api."""
    tokens = (
        "recommender.",
        "from recommender",
        "import recommender",
        '"pp-api"',
        "recommend digest",
        "/home/nigelf/",
        "POST /auth/register",
        "song-recommender",
        "RECOMMEND_SPOTIFY",
        "RECOMMEND_DATA_DIR",
        "src.admin.cli:",
        "--max-cycles",
    )
    return any(tok in text for tok in tokens)


def _audit_single_tracked_text_file(
    repo_root: Path,
    rel: str,
    forbid_recommender: bool,
) -> List[str]:
    """Scan one git-tracked file for hardcoded brain paths and deleted package refs."""
    fpath = repo_root / rel
    if not fpath.is_file() or fpath.suffix.lower() in BINARY_EXTENSIONS:
        return []
    text = fpath.read_text(encoding="utf-8", errors="replace")
    gaps: List[str] = []
    win_tok = ".gemini\\" + "antigravity\\brain\\"
    pos_tok = ".gemini/" + "antigravity/brain/"
    if win_tok in text or pos_tok in text:
        gaps.append(f"{rel}: hardcoded conversation brain path")
    if (
        forbid_recommender
        and not _is_historical_plan_doc(rel)
        and _has_stale_recommender_token(text)
    ):
        gaps.append(f"{rel}: stale reference to deleted recommender/pp-api package")
    return gaps


def _audit_all_git_tracked_files(repo_root: Path) -> List[str]:
    """Audit 100% of git-tracked files for index hygiene, brain paths, and stale packages."""
    gaps = _audit_git_index_hygiene(repo_root)
    forbid_rec = (repo_root / "pyproject.toml").is_file() and not _has_package_target(
        repo_root, "recommender"
    )
    for rel in _get_git_tracked_files(repo_root):
        gaps.extend(_audit_single_tracked_text_file(repo_root, rel, forbid_rec))
    return gaps


def _extract_toml_list(pyproj_text: str, key: str) -> List[str]:
    """Extract string items from a TOML array assignment `key = [...]`."""
    match = re.search(
        rf"(?m)^\s*{re.escape(key)}\s*=\s*\[([\s\S]*?)\]", pyproj_text
    )
    if not match:
        return []
    return [m.group(1).strip("/") for m in re.finditer(r'"([^"]+)"', match.group(1))]


def _is_covered_by_testpaths(rel_path: str, testpaths: Sequence[str]) -> bool:
    """Return True if rel_path matches or is inside at least one entry in testpaths."""
    return any(
        rel_path == tp or rel_path.startswith(f"{tp}/") for tp in testpaths
    )


def _audit_pyproject_testpaths(repo_root: Path, pyproj_text: str) -> List[str]:
    """Verify every tests/**/test_*.py file is covered by pyproject.toml testpaths."""
    testpaths = _extract_toml_list(pyproj_text, "testpaths")
    tests_dir = repo_root / "tests"
    if not testpaths or not tests_dir.is_dir():
        return []
    gaps: List[str] = []
    for dirpath, dirnames, filenames in os.walk(tests_dir):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDED_WALK_DIRS)
        for fname in sorted(filenames):
            if fname.startswith("test_") and fname.endswith(".py"):
                rel = str((Path(dirpath) / fname).relative_to(repo_root)).replace("\\", "/")
                if not _is_covered_by_testpaths(rel, testpaths):
                    gaps.append(f"{rel}: orphaned test file outside pyproject.toml testpaths")
    return gaps


def _has_package_target(repo_root: Path, pkg: str) -> bool:
    """Return True if pkg exists at repo_root/<pkg> or repo_root/src/<pkg>."""
    return (repo_root / pkg).exists() or (repo_root / "src" / pkg).exists()


def _audit_ci_and_entrypoints(repo_root: Path) -> List[str]:
    """Verify CI --cov targets and Docker/config module entrypoints exist in repo_root."""
    gaps: List[str] = []
    ci_yml = repo_root / ".github" / "workflows" / "ci.yml"
    if ci_yml.is_file():
        ci_txt = ci_yml.read_text(encoding="utf-8", errors="replace")
        for match in re.finditer(r"--cov=([A-Za-z0-9_]+)", ci_txt):
            pkg = match.group(1)
            if not _has_package_target(repo_root, pkg):
                gaps.append(f".github/workflows/ci.yml: --cov={pkg} targets missing package")
    if not _has_package_target(repo_root, "recommender"):
        for rel in ("Dockerfile", "docker-compose.yml", "alembic/env.py", "scripts/daily-digest.sh"):
            fp = repo_root / rel
            if fp.is_file() and "recommender." in fp.read_text(encoding="utf-8", errors="replace"):
                gaps.append(f"{rel}: stale entrypoint reference to deleted package recommender")
    return gaps


def _extract_web_route_prefixes(repo_root: Path) -> Set[str]:
    """Extract top-level /<prefix> route segments and router prefixes from src/web/*.py."""
    routes_py = repo_root / "src" / "web" / "routes.py"
    if not routes_py.is_file():
        return set()
    prefixes: Set[str] = set()
    pat = re.compile(
        r'(?:@(?:router|app)\.[a-z]+\(\s*"/([A-Za-z0-9_-]+)'
        r'|include_router\([^)]*prefix\s*=\s*"/([A-Za-z0-9_-]+)"'
        r'|app\.mount\(\s*"/([A-Za-z0-9_-]+)")'
    )
    for name in ("routes.py", "server.py"):
        fp = repo_root / "src" / "web" / name
        if fp.is_file():
            txt = fp.read_text(encoding="utf-8", errors="replace")
            for m in pat.finditer(txt):
                prefixes.add(m.group(1) or m.group(2) or m.group(3))
    return prefixes


def _audit_frontend_api_parity(repo_root: Path, prefixes: Set[str]) -> List[str]:
    """Verify frontend /api/<seg> calls and next.config.js rewrite tests match backend routes."""
    gaps: List[str] = []
    next_cfg = repo_root / "frontend" / "next.config.js"
    cfg_test = repo_root / "frontend" / "__tests__" / "config.test.ts"
    if next_cfg.is_file() and cfg_test.is_file():
        c_txt = next_cfg.read_text(encoding="utf-8", errors="replace")
        t_txt = cfg_test.read_text(encoding="utf-8", errors="replace")
        if ("127.0.0.1:5000" in c_txt) != ("127.0.0.1:5000" in t_txt):
            gaps.append(
                "frontend/__tests__/config.test.ts: rewrite destination host mismatch vs next.config.js"
            )
    fe_src = repo_root / "frontend" / "src"
    if not fe_src.is_dir():
        return gaps
    for fp in sorted(fe_src.rglob("*.ts*")):
        rel = str(fp.relative_to(repo_root)).replace("\\", "/")
        txt = fp.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r'["\'`]/api/([A-Za-z0-9_-]+)', txt):
            if m.group(1) not in prefixes:
                gaps.append(f"{rel}: frontend calls unmounted route /api/{m.group(1)}")
    return gaps


def _run_frontend_npm_cmd(
    fe_dir: Path, args: Sequence[str], label: str
) -> List[str]:
    """Execute one npm command in frontend/ and flag non-zero exit or JSDOM media errors."""
    npm_bin = shutil.which("npm")
    if npm_bin is None:
        return []
    try:
        proc = subprocess.run(
            [npm_bin, *args],
            cwd=str(fe_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return [f"frontend/package.json: {label} execution error ({exc})"]
    out = f"{proc.stdout or ''}\n{proc.stderr or ''}"
    gaps: List[str] = []
    if proc.returncode != 0:
        gaps.append(f"frontend/package.json: {label} failed (exit {proc.returncode})")
    if "Not implemented: HTMLMediaElement" in out:
        gaps.append(
            "frontend/jest.setup.js: unpolyfilled JSDOM HTMLMediaElement error in tests"
        )
    return gaps


def _audit_frontend_execution(repo_root: Path) -> List[str]:
    """Verify frontend node_modules/.bin exists and npm lint + jest pass in git repos."""
    fe_dir = repo_root / "frontend"
    if not (fe_dir / "package.json").is_file() or not (repo_root / ".git").exists():
        return []
    bin_dir = fe_dir / "node_modules" / ".bin"
    if not bin_dir.is_dir() or not any(bin_dir.iterdir()):
        return ["frontend/package.json: frontend/node_modules/.bin is missing or empty"]
    gaps = _run_frontend_npm_cmd(fe_dir, ("run", "lint"), "npm run lint")
    gaps.extend(
        _run_frontend_npm_cmd(fe_dir, ("test", "--", "--watchAll=false"), "npm test")
    )
    return gaps


def _audit_chroma_collection_parity(repo_root: Path) -> List[str]:
    """Flag legacy ChromaDB collection names or paths in scripts/*.py."""
    scripts_dir = repo_root / "scripts"
    if _has_package_target(repo_root, "recommender") or not scripts_dir.is_dir():
        return []
    gaps: List[str] = []
    for fp in sorted(scripts_dir.glob("*.py")):
        rel = str(fp.relative_to(repo_root)).replace("\\", "/")
        txt = fp.read_text(encoding="utf-8", errors="replace")
        if "promo_collection" in txt or "D:/Archive/chroma_data" in txt or "./chroma_data" in txt:
            gaps.append(
                f"{rel}: legacy ChromaDB promo_collection or chroma_data path in script"
            )
    return gaps


_DEAD_LEGACY_PYPROJECT_PKGS: Tuple[str, ...] = (
    "spotipy",
    "flask>=",
    "spotifyscraper",
    "tidalapi",
    "deezer-python",
    "implicit>=",
    "arq>=",
    "authlib>=",
    "python-jose",
    "passlib",
)
_CLI_OR_RUNNER_PKGS: Set[str] = {
    "uvicorn",
    "pytest",
    "pytest-asyncio",
    "pytest-cov",
    "ruff",
    "alembic",
    "hatchling",
    "locust",
    "bandit",
    "pip-audit",
}
_DIST_TO_IMPORT_MAP: Dict[str, str] = {
    "beautifulsoup4": "bs4",
    "sqlite-vec": "sqlite_vec",
    "pydantic-settings": "pydantic_settings",
    "pyyaml": "yaml",
    "scikit-learn": "sklearn",
    "prometheus-client": "prometheus_client",
}
_DECLARED_DEP_RE = re.compile(
    r'"([a-zA-Z0-9_.-]+)(?:\[[a-zA-Z0-9_,-]+\])?\s*(?:>=|==|~=|<=)'
)


def _extract_py_import_roots(py_path: Path) -> Set[str]:
    """Return top-level imported module names from a single Python file."""
    try:
        tree = ast.parse(py_path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError):
        return set()
    roots: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def _collect_repo_ast_import_roots(repo_root: Path) -> Set[str]:
    """Collect top-level imported module roots across Python files in repo_root."""
    imported: Set[str] = set()
    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_WALK_DIRS]
        for fname in filenames:
            if fname.endswith(".py"):
                imported.update(_extract_py_import_roots(Path(dirpath) / fname))
    return imported


def _extract_declared_dep_names(text: str) -> List[Tuple[str, str]]:
    """Extract (dist_name, import_root) pairs from pinned dependency strings."""
    pairs: List[Tuple[str, str]] = []
    for match in _DECLARED_DEP_RE.finditer(text):
        dist = match.group(1).lower()
        if dist in _CLI_OR_RUNNER_PKGS:
            continue
        mod = _DIST_TO_IMPORT_MAP.get(dist, dist.replace("-", "_"))
        pairs.append((dist, mod))
    return pairs


def _audit_unimported_declared_deps(repo_root: Path) -> List[str]:
    """Flag pinned dependencies in pyproject.toml and Dockerfiles never imported in repo."""
    if not (repo_root / "src").is_dir():
        return []
    imported = _collect_repo_ast_import_roots(repo_root)
    if not ({"fastapi", "pydantic", "numpy"} & imported):
        return []
    gaps: List[str] = []
    targets = (
        "pyproject.toml",
        "Dockerfile",
        "Dockerfile.backend",
        "Dockerfile.railway",
    )
    for rel in targets:
        fp = repo_root / rel
        if not fp.is_file():
            continue
        for dist, mod in _extract_declared_dep_names(
            fp.read_text(encoding="utf-8", errors="replace")
        ):
            if mod not in imported:
                gaps.append(f"{rel}: unimported dependency {dist}")
    return gaps


def _audit_pyproject_deps(repo_root: Path) -> List[str]:
    """Flag dead legacy and unimported dependencies in pyproject.toml and Dockerfiles."""
    pyproj = repo_root / "pyproject.toml"
    if _has_package_target(repo_root, "recommender") or not pyproj.is_file():
        return []
    txt = pyproj.read_text(encoding="utf-8", errors="replace")
    gaps = [
        f"pyproject.toml: dead legacy dependency {pkg}"
        for pkg in _DEAD_LEGACY_PYPROJECT_PKGS
        if pkg in txt
    ]
    gaps.extend(_audit_unimported_declared_deps(repo_root))
    return gaps


def _audit_nginx_route_parity(repo_root: Path, prefixes: Set[str]) -> List[str]:
    """Verify nginx proxy location blocks target existing FastAPI route prefixes."""
    gaps: List[str] = []
    for rel in ("nginx.conf", "nginx.prod.conf"):
        fp = repo_root / rel
        if not fp.is_file():
            continue
        txt = fp.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"location\s+/([A-Za-z0-9_-]+)\s*\{([^}]*)\}", txt):
            seg, body = m.group(1), m.group(2)
            if "proxy_pass" in body and seg not in prefixes:
                gaps.append(f"{rel}: nginx proxies non-existent route /{seg}")
        if "static" in prefixes and "location /static" not in txt:
            gaps.append(f"{rel}: nginx missing location /static proxy for mounted StaticFiles")
    return gaps


def _audit_locust_route_parity(repo_root: Path, prefixes: Set[str]) -> List[str]:
    """Verify loadtest/locustfile.py client calls, query params, and response shapes."""
    fp = repo_root / "loadtest" / "locustfile.py"
    if not fp.is_file():
        return []
    txt = fp.read_text(encoding="utf-8", errors="replace")
    gaps: List[str] = []
    for m in re.finditer(r'self\.client\.[a-z]+\(\s*f?"/([A-Za-z0-9_-]+)', txt):
        seg = m.group(1)
        if seg not in prefixes:
            gaps.append(f"loadtest/locustfile.py: loadtest targets non-existent route /{seg}")
    if "isinstance(data, list)" in txt and "/catalog/top" in txt:
        gaps.append(
            "loadtest/locustfile.py: /catalog/top returns dict {'count', 'tracks'}, not list"
        )
    if "?tab=" in txt:
        gaps.append(
            "loadtest/locustfile.py: /catalog/feed does not accept ?tab= query parameter"
        )
    return gaps


def _extract_exported_metrics(repo_root: Path) -> Set[str]:
    """Extract Prometheus metric names declared via # TYPE in src/web/routes.py."""
    routes_py = repo_root / "src" / "web" / "routes.py"
    if not routes_py.is_file():
        return set()
    txt = routes_py.read_text(encoding="utf-8", errors="replace")
    return set(re.findall(r"#\s*TYPE\s+([a-zA-Z0-9_]+)\s+", txt))


def _collect_metric_consumer_files(repo_root: Path) -> List[Path]:
    """Collect Grafana JSON/YAML files and docs/API.md for metric parity checks."""
    files: List[Path] = []
    graf = repo_root / "grafana"
    if graf.is_dir():
        files.extend(sorted(graf.rglob("*.json")))
        files.extend(sorted(graf.rglob("*.yml")))
    api_md = repo_root / "docs" / "API.md"
    if api_md.is_file():
        files.append(api_md)
    return files


def _audit_metrics_consumers(repo_root: Path, metrics: Set[str]) -> List[str]:
    """Verify Grafana dashboards/alerts and docs/API.md reference exported metrics."""
    if not metrics:
        return []
    gaps: List[str] = []
    pat = re.compile(
        r"\b(private_press_[a-z0-9_]+|track_processing_total|sync_runs_total"
        r"|export_operations_total|websocket_connections_active)\b"
    )
    for fp in _collect_metric_consumer_files(repo_root):
        rel = str(fp.relative_to(repo_root)).replace("\\", "/")
        txt = fp.read_text(encoding="utf-8", errors="replace")
        for m in pat.finditer(txt):
            if m.group(1) not in metrics:
                gaps.append(f"{rel}: unexported Prometheus metric {m.group(1)}")
    return gaps


def _audit_nextjs_docker_contracts(repo_root: Path) -> List[str]:
    """Flag Vite dist/ directory references when frontend/package.json uses Next.js."""
    fe_pkg = repo_root / "frontend" / "package.json"
    if not fe_pkg.is_file() or '"next"' not in fe_pkg.read_text(encoding="utf-8", errors="replace"):
        return []
    gaps: List[str] = []
    for rel in ("Dockerfile", "Dockerfile.railway", "docker-compose.yml"):
        fp = repo_root / rel
        if fp.is_file():
            txt = fp.read_text(encoding="utf-8", errors="replace")
            if "/app/dist" in txt or "./frontend/dist" in txt:
                gaps.append(f"{rel}: references Vite dist/ directory for Next.js frontend")
    return gaps


def _audit_alembic_schema_contracts(repo_root: Path) -> List[str]:
    """Flag legacy recommender tables in alembic/versions/*.py when recommender is absent."""
    vers_dir = repo_root / "alembic" / "versions"
    if _has_package_target(repo_root, "recommender") or not vers_dir.is_dir():
        return []
    gaps: List[str] = []
    for fp in sorted(vers_dir.glob("*.py")):
        rel = str(fp.relative_to(repo_root)).replace("\\", "/")
        txt = fp.read_text(encoding="utf-8", errors="replace")
        if "recommendation_sets" in txt or "candidate_matches" in txt:
            gaps.append(f"{rel}: legacy recommender schema in Alembic migration")
    return gaps


def _audit_e2e_route_parity(repo_root: Path, prefixes: Set[str]) -> List[str]:
    """Verify e2e/*.ts files do not target deleted /login or /auth OAuth routes."""
    e2e_dir = repo_root / "e2e"
    if not e2e_dir.is_dir() or "auth" in prefixes:
        return []
    gaps: List[str] = []
    for fp in sorted(e2e_dir.rglob("*.ts")):
        rel = str(fp.relative_to(repo_root)).replace("\\", "/")
        txt = fp.read_text(encoding="utf-8", errors="replace")
        if "/auth/" in txt or "'/login'" in txt:
            gaps.append(f"{rel}: e2e test targets non-existent /auth or /login route")
    return gaps


_COMPOSE_ONLY_PP_VARS: Set[str] = {
    "PP_PROMETHEUS_PORT",
    "PP_GRAFANA_PORT",
    "PP_GRAFANA_ADMIN_USER",
    "PP_GRAFANA_ADMIN_PASSWORD",
    "PP_LOCUST_PORT",
    "PP_LOCUST_WORKERS",
}


def _collect_declared_pp_env_vars(repo_root: Path) -> Set[str]:
    """Extract PP_* env vars from .env.example, Dockerfiles, and loadtest compose."""
    declared: Set[str] = set()
    rels = (
        ".env.example",
        "Dockerfile",
        "Dockerfile.railway",
        "docker-compose.loadtest.yml",
    )
    for rel in rels:
        fp = repo_root / rel
        if fp.is_file():
            txt = fp.read_text(encoding="utf-8", errors="replace")
            declared.update(re.findall(r"\b(PP_[A-Z0-9_]+)\b", txt))
    return declared - _COMPOSE_ONLY_PP_VARS


def _collect_env_consumer_text(repo_root: Path) -> str:
    """Concatenate source text from src/, scripts/, alembic/, and frontend/next.config.js."""
    chunks: List[str] = []
    for folder in ("src", "scripts", "alembic"):
        base = repo_root / folder
        if base.is_dir():
            for fp in sorted(base.rglob("*")):
                if fp.is_file() and fp.suffix in {".py", ".sh"}:
                    chunks.append(fp.read_text(encoding="utf-8", errors="replace"))
    next_cfg = repo_root / "frontend" / "next.config.js"
    if next_cfg.is_file():
        chunks.append(next_cfg.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(chunks)


def _audit_env_var_parity(repo_root: Path) -> List[str]:
    """Flag declared PP_* application env vars never read in runtime or scripts."""
    if not (repo_root / ".env.example").is_file() and not (repo_root / "Dockerfile").is_file():
        return []
    declared = _collect_declared_pp_env_vars(repo_root)
    if not declared:
        return []
    consumed_text = _collect_env_consumer_text(repo_root)
    return [
        f".env.example: unread application env var {var}"
        for var in sorted(declared)
        if var not in consumed_text
    ]


def _extract_optional_dep_extras(pyproj_text: str) -> Set[str]:
    """Extract extra key names from [project.optional-dependencies] in pyproject.toml."""
    match = re.search(
        r"(?m)^\[project\.optional-dependencies\]\s*\n([\s\S]*?)(?=^\[[A-Za-z]|\Z)",
        pyproj_text,
    )
    if not match:
        return set()
    return set(re.findall(r"(?m)^\s*([A-Za-z0-9_-]+)\s*=", match.group(1)))


def _scan_file_pip_extras(
    fpath: Path, rel: str, valid_extras: Set[str]
) -> List[str]:
    """Scan pip install lines in fpath for undefined .[extra] specifiers."""
    if not fpath.is_file():
        return []
    gaps: List[str] = []
    txt = fpath.read_text(encoding="utf-8", errors="replace")
    for match in re.finditer(r"pip\s+install[^\n]*?\.(\[[A-Za-z0-9_,\s]+\])", txt):
        raw_list = match.group(1).strip("[]").split(",")
        for extra in (item.strip() for item in raw_list if item.strip()):
            if extra not in valid_extras:
                gaps.append(
                    f"{rel}: pip install references undefined extra [{extra}]"
                )
    return gaps


def _audit_pip_extras_parity(repo_root: Path) -> List[str]:
    """Verify pip install .[extra] references in Dockerfiles and CI exist in pyproject.toml."""
    pyproj = repo_root / "pyproject.toml"
    if not pyproj.is_file():
        return []
    valid = _extract_optional_dep_extras(
        pyproj.read_text(encoding="utf-8", errors="replace")
    )
    targets = (
        "Dockerfile",
        "Dockerfile.backend",
        "Dockerfile.backfill",
        "Dockerfile.railway",
        ".github/workflows/ci.yml",
    )
    gaps: List[str] = []
    for rel in targets:
        gaps.extend(_scan_file_pip_extras(repo_root / rel, rel, valid))
    return gaps


def _check_dockerfile_worker_watch(repo_root: Path) -> List[str]:
    """Verify Dockerfile worker stage ENTRYPOINT pp-feed includes --watch and COPY src order."""
    df = repo_root / "Dockerfile"
    if not df.is_file():
        return []
    txt = df.read_text(encoding="utf-8", errors="replace")
    gaps: List[str] = []
    if re.search(
        r'RUN\s+pip\s+install[^\n]*\.\[?[A-Za-z0-9_,-]*\]?["\']?\s*\n+\s*COPY\s+src',
        txt,
    ):
        gaps.append("Dockerfile: pip install local package before COPY src/")
    match = re.search(
        r"(?im)^FROM\s+\S+\s+AS\s+worker\b([\s\S]*?)(?=^FROM\s|\Z)", txt
    )
    if match and 'ENTRYPOINT ["pp-feed"]' in match.group(1) and "--watch" not in match.group(1):
        gaps.append("Dockerfile: worker stage ENTRYPOINT pp-feed missing --watch")
    return gaps


def _check_compose_redis(repo_root: Path) -> List[str]:
    """Flag unused redis services in docker-compose manifests when redis is not in pyproject.toml."""
    pyproj = repo_root / "pyproject.toml"
    if not pyproj.is_file():
        return []
    if "redis" in pyproj.read_text(encoding="utf-8", errors="replace").lower():
        return []
    gaps: List[str] = []
    for rel in ("docker-compose.yml", "docker-compose.prod.yml"):
        fp = repo_root / rel
        if fp.is_file() and "redis:" in fp.read_text(encoding="utf-8", errors="replace"):
            gaps.append(f"{rel}: unused redis service in compose manifest")
    return gaps


def _check_compose_nginx_mount(repo_root: Path) -> List[str]:
    """Flag ./frontend/public nginx mount when frontend/public/index.html is missing."""
    dc = repo_root / "docker-compose.yml"
    if not dc.is_file() or (repo_root / "frontend" / "public" / "index.html").is_file():
        return []
    if "./frontend/public:/usr/share/nginx/html" in dc.read_text(
        encoding="utf-8", errors="replace"
    ):
        return [
            "docker-compose.yml: nginx mounts frontend/public without frontend/public/index.html"
        ]
    return []


def _check_backfill_dockerfile(repo_root: Path) -> List[str]:
    """Verify Dockerfile.backfill has no legacy TensorFlow/python3.11 and copies src before pip install."""
    fp = repo_root / "Dockerfile.backfill"
    if not fp.is_file():
        return []
    txt = fp.read_text(encoding="utf-8", errors="replace")
    legacy = ("essentia-tensorflow", "tensorflow==", "python3.11", "musicnn.pb")
    if any(tok in txt for tok in legacy) or "COPY src" not in txt.partition("pip install")[0]:
        return [
            "Dockerfile.backfill: legacy TensorFlow/python3.11 or pip install before COPY src"
        ]
    return []


def _audit_docker_and_compose_contracts(repo_root: Path) -> List[str]:
    """Audit Dockerfile worker CMD, backfill chroma_data paths, and compose contracts."""
    gaps = _check_dockerfile_worker_watch(repo_root)
    gaps.extend(_check_backfill_dockerfile(repo_root))
    for rel in ("Dockerfile.backfill", "docker-compose.backfill.yml"):
        fp = repo_root / rel
        if fp.is_file() and "chroma_data" in fp.read_text(encoding="utf-8", errors="replace"):
            gaps.append(f"{rel}: stale chroma_data path")
    gaps.extend(_check_compose_redis(repo_root))
    gaps.extend(_check_compose_nginx_mount(repo_root))
    return gaps


def _has_alembic_001_drift(schema_txt: str) -> bool:
    """Return True if 001_initial_schema.py drifts from SingleWriterDB columns/tables."""
    required = ("super_vector_json", "metadata_blob", "event_id", "archive_tracks")
    if not all(tok in schema_txt for tok in required):
        return True
    return "source_url" in schema_txt


def _check_alembic_index_parity(repo_root: Path) -> List[str]:
    """Check if alembic/versions/002_add_indexes.py index names match SingleWriterDB."""
    idx_py = repo_root / "alembic" / "versions" / "002_add_indexes.py"
    db_py = repo_root / "src" / "orchestration" / "db.py"
    if not idx_py.is_file() or not db_py.is_file():
        return []
    idx_a = set(
        re.findall(
            r"\bidx_[a-zA-Z0-9_]+\b",
            idx_py.read_text(encoding="utf-8", errors="replace"),
        )
    )
    idx_b = set(
        re.findall(
            r"\bidx_[a-zA-Z0-9_]+\b",
            db_py.read_text(encoding="utf-8", errors="replace"),
        )
    )
    if idx_a != idx_b:
        return [
            "alembic/versions/002_add_indexes.py: index set drift vs SingleWriterDB"
        ]
    return []


def _audit_alembic_vs_runtime_schema(repo_root: Path) -> List[str]:
    """Audit alembic/env.py fallback URL and 001/002 migrations vs SingleWriterDB."""
    gaps: List[str] = []
    env_py = repo_root / "alembic" / "env.py"
    if env_py.is_file():
        env_txt = env_py.read_text(encoding="utf-8", errors="replace")
        if "sqlite:///data/api.db" in env_txt:
            gaps.append("alembic/env.py: stale fallback sqlite:///data/api.db")
        if "PP_DB_PATH" in env_txt and "DB_PATH" not in env_txt.replace(
            "PP_DB_PATH", ""
        ):
            gaps.append(
                "alembic/env.py: PP_DB_PATH read without DB_PATH fallback parity"
            )
    init_py = repo_root / "alembic" / "versions" / "001_initial_schema.py"
    db_py = repo_root / "src" / "orchestration" / "db.py"
    if init_py.is_file() and db_py.is_file():
        if _has_alembic_001_drift(
            init_py.read_text(encoding="utf-8", errors="replace")
        ):
            gaps.append(
                "alembic/versions/001_initial_schema.py: schema drift vs SingleWriterDB"
            )
    gaps.extend(_check_alembic_index_parity(repo_root))
    return gaps


def _audit_api_doc_parity(repo_root: Path) -> List[str]:
    """Flag stale route parameter and response documentation in docs/API.md."""
    api_md = repo_root / "docs" / "API.md"
    if not api_md.is_file() or _has_package_target(repo_root, "recommender"):
        return []
    txt = api_md.read_text(encoding="utf-8", errors="replace")
    stale_tokens = (
        "SingleWriterDB.compact_database()",
        "DatabaseCompactor",
        "LiveStoreFeedPoller",
        "SingleWriterDB.enqueue_track",
        "store_candidate",
        "thumbs_up",
        "thumbs_down",
        "cursor/offset pagination",
    )
    gaps = [
        f"docs/API.md: stale API contract token {tok}"
        for tok in stale_tokens
        if tok in txt
    ]
    routes_py = repo_root / "src" / "web" / "routes.py"
    if (
        routes_py.is_file()
        and "/catalog/store-redirect/" in routes_py.read_text(encoding="utf-8", errors="replace")
        and "/catalog/store-redirect/" not in txt
    ):
        gaps.append(
            "docs/API.md: undocumented route /catalog/store-redirect/{track_id}"
        )
    return gaps


def _audit_doc_ast_and_path_parity(repo_root: Path) -> List[str]:
    """Flag stale AST symbols and case-mismatched paths in architecture docs."""
    if _has_package_target(repo_root, "recommender"):
        return []
    doc_rels = (
        "README.md",
        "docs/API.md",
        "docs/ARCHITECTURE.md",
        "docs/architecture/task.md",
        "docs/architecture/high_level_architecture.md",
    )
    stale_tokens = (
        "StorePollerService",
        "AtomicRCURegistry",
        "RCUArbiter",
        "RCUWrapper",
        "TrackQueue.push",
        "apply_anti_medoid_repulsion",
        "resolve_track_audio_path",
        "_resolve_stream_file_path",
        "docs/architecture.md",
        "xxHash",
    )
    gaps: List[str] = []
    for rel in doc_rels:
        fp = repo_root / rel
        if not fp.is_file():
            continue
        txt = fp.read_text(encoding="utf-8", errors="replace")
        gaps.extend(
            f"{rel}: stale AST symbol or case-mismatched path {tok}"
            for tok in stale_tokens
            if tok in txt
        )
    return gaps


def _collect_tests_blob(repo_root: Path) -> str:
    """Return concatenated text of tests/**/*.py when src/, tests/, and .git exist."""
    if (
        not (repo_root / "src").is_dir()
        or not (repo_root / "tests").is_dir()
        or not (repo_root / ".git").exists()
    ):
        return ""
    return "\n".join(
        fp.read_text(encoding="utf-8", errors="replace")
        for fp in sorted((repo_root / "tests").rglob("*.py"))
        if fp.is_file()
    )


def _audit_src_module_reachability(repo_root: Path) -> List[str]:
    """Flag src/**/*.py modules (excluding __init__.py and cli.py) unreferenced in tests."""
    test_blob = _collect_tests_blob(repo_root)
    if not test_blob.strip():
        return []
    gaps: List[str] = []
    for py_file in sorted((repo_root / "src").rglob("*.py")):
        if py_file.name in {"__init__.py", "cli.py"}:
            continue
        rel = str(py_file.relative_to(repo_root)).replace("\\", "/")
        dotted = rel[:-3].replace("/", ".")
        short_dotted = dotted[4:]
        stem = py_file.stem
        if dotted not in test_blob and short_dotted not in test_blob and stem not in test_blob:
            gaps.append(f"{rel}: unreferenced src module missing test coverage")
    return gaps


def _dockerfile_has_static_public(repo_root: Path) -> bool:
    """Return True if Dockerfile or Dockerfile.railway references /static/public."""
    for rel in ("Dockerfile", "Dockerfile.railway"):
        fp = repo_root / rel
        if fp.is_file() and "/static/public" in fp.read_text(encoding="utf-8", errors="replace"):
            return True
    return False


def _audit_container_static_serving(repo_root: Path) -> List[str]:
    """Verify src/web/server.py mounts StaticFiles when Dockerfiles copy /static/public."""
    srv = repo_root / "src" / "web" / "server.py"
    if not srv.is_file() or not _dockerfile_has_static_public(repo_root):
        return []
    if "StaticFiles" not in srv.read_text(encoding="utf-8", errors="replace"):
        return [
            "src/web/server.py: Dockerfile copies /static/public but server.py does not mount StaticFiles"
        ]
    return []


def _has_backend_dockerfile_drift(repo_root: Path) -> bool:
    """Return True if Dockerfile.backend has python:3.11 or stale scipy/sqlite-vec pins."""
    fp = repo_root / "Dockerfile.backend"
    if not fp.is_file():
        return False
    txt = fp.read_text(encoding="utf-8", errors="replace")
    return any(
        tok in txt
        for tok in ("python:3.11", "scipy>=1.10.0", "sqlite-vec>=0.1.0")
    )


def _audit_dockerfile_pin_parity(repo_root: Path) -> List[str]:
    """Flag base-image/version pin drift in Dockerfiles and stale watchdog DB path."""
    gaps: List[str] = []
    if _has_backend_dockerfile_drift(repo_root):
        gaps.append(
            "Dockerfile.backend: base image or dependency version pin drift vs pyproject.toml"
        )
    fe_df = repo_root / "frontend" / "Dockerfile"
    if fe_df.is_file() and "node:20" in fe_df.read_text(encoding="utf-8", errors="replace"):
        gaps.append("frontend/Dockerfile: node:20 base image drift vs node:22")
    wd = repo_root / "src" / "orchestration" / "watchdog.py"
    if wd.is_file() and "db.sqlite" in wd.read_text(encoding="utf-8", errors="replace"):
        gaps.append("src/orchestration/watchdog.py: stale db.sqlite default path")
    return gaps


def _has_bare_infra_import(txt: str) -> bool:
    """Return True if txt contains bare infrastructure imports or mock patches."""
    tokens = (
        "from infrastructure.",
        'patch("infrastructure.',
        'patch(\n    "infrastructure.',
    )
    return any(tok in txt for tok in tokens)


def _audit_test_import_prefixes(repo_root: Path) -> List[str]:
    """Flag test files using bare infrastructure.* imports instead of src.infrastructure.*."""
    tests_dir = repo_root / "tests"
    if not tests_dir.is_dir() or not (repo_root / "src" / "infrastructure").is_dir():
        return []
    gaps: List[str] = []
    for fp in sorted(tests_dir.rglob("*.py")):
        rel = str(fp.relative_to(repo_root)).replace("\\", "/")
        if _has_bare_infra_import(fp.read_text(encoding="utf-8", errors="replace")):
            gaps.append(f"{rel}: bare infrastructure import missing src. prefix")
    return gaps


def _audit_scripts_and_chroma_env_parity(repo_root: Path) -> List[str]:
    """Check scripts and chroma_client for DB_PATH/PP_DB_PATH and CHROMA_DB_DIR/PP_CHROMA_DIR parity."""
    checks = (
        (
            "scripts/run_e2e_pipeline.py",
            "DB_PATH",
            "PP_DB_PATH",
            "scripts/run_e2e_pipeline.py: DB_PATH set without PP_DB_PATH parity",
        ),
        (
            "scripts/verify_db.py",
            "CHROMA_DB_DIR",
            "PP_CHROMA_DIR",
            "scripts/verify_db.py: CHROMA_DB_DIR read without PP_CHROMA_DIR parity",
        ),
        (
            "src/scoring/chroma_client.py",
            "PP_CHROMA_DIR",
            "CHROMA_DB_DIR",
            "src/scoring/chroma_client.py: PP_CHROMA_DIR read without CHROMA_DB_DIR fallback parity",
        ),
    )
    gaps: List[str] = []
    for rel, present_tok, required_tok, msg in checks:
        fp = repo_root / rel
        if fp.is_file():
            txt = fp.read_text(encoding="utf-8", errors="replace")
            if present_tok in txt and required_tok not in txt:
                gaps.append(msg)
    return gaps


def _audit_db_path_env_parity(repo_root: Path) -> List[str]:
    """Flag src/**/*.py and scripts reading DB_PATH/Chroma env vars without fallback parity."""
    src_dir = repo_root / "src"
    if not src_dir.is_dir():
        return []
    gaps: List[str] = []
    for fp in sorted(src_dir.rglob("*.py")):
        rel = str(fp.relative_to(repo_root)).replace("\\", "/")
        txt = fp.read_text(encoding="utf-8", errors="replace")
        if 'os.environ.get("DB_PATH"' in txt and "PP_DB_PATH" not in txt:
            gaps.append(f"{rel}: DB_PATH read without PP_DB_PATH fallback parity")
    gaps.extend(_audit_scripts_and_chroma_env_parity(repo_root))
    return gaps


def _audit_daemon_cuda_fallback(daemon_py: Path) -> List[str]:
    """Check src/gpu_pipeline/daemon.py for Windows expandable_segments and CPU fallback."""
    if not daemon_py.is_file():
        return []
    d_txt = daemon_py.read_text(encoding="utf-8", errors="replace")
    gaps: List[str] = []
    if "expandable_segments:True" in d_txt and 'platform.system() == "Windows"' not in d_txt:
        gaps.append(
            "src/gpu_pipeline/daemon.py: unconditional expandable_segments on Windows"
        )
    if (
        "set_per_process_memory_fraction" in d_txt
        and "except (AssertionError, RuntimeError)" not in d_txt
    ):
        gaps.append(
            "src/gpu_pipeline/daemon.py: unguarded CUDA memory fraction without CPU fallback"
        )
    return gaps


def _audit_model_wrapper_contracts(models_py: Path) -> List[str]:
    """Check src/gpu_pipeline/models.py for device alignment, 3D DAC unsqueeze, and pooling."""
    if not models_py.is_file():
        return []
    m_txt = models_py.read_text(encoding="utf-8", errors="replace")
    if "class DACModel" in m_txt and (
        "unsqueeze" not in m_txt
        or "quantized_representation" not in m_txt
        or ".to(" not in m_txt
    ):
        return [
            "src/gpu_pipeline/models.py: DACModel/MERTModel missing device alignment, 3D unsqueeze, or quantized_representation pooling"
        ]
    return []


def _audit_cuda_cpu_fallback_parity(repo_root: Path) -> List[str]:
    """Flag unguarded CUDA device/memory calls in src/gpu_pipeline without CPU fallback."""
    gaps: List[str] = []
    models_py = repo_root / "src" / "gpu_pipeline" / "models.py"
    if models_py.is_file():
        m_txt = models_py.read_text(encoding="utf-8", errors="replace")
        if 'device="cuda"' in m_txt and "except (AssertionError, RuntimeError)" not in m_txt:
            gaps.append(
                "src/gpu_pipeline/models.py: unguarded CUDA allocation without CPU fallback"
            )
    gaps.extend(_audit_model_wrapper_contracts(models_py))
    gaps.extend(
        _audit_daemon_cuda_fallback(repo_root / "src" / "gpu_pipeline" / "daemon.py")
    )
    return gaps


def _audit_cross_surface_contracts(repo_root: Path) -> List[str]:
    """Audit routes vs nginx/locust/e2e/frontend, metrics, Docker, Alembic, scripts, and deps."""
    gaps: List[str] = []
    prefixes = _extract_web_route_prefixes(repo_root)
    if prefixes:
        gaps.extend(_audit_nginx_route_parity(repo_root, prefixes))
        gaps.extend(_audit_locust_route_parity(repo_root, prefixes))
        gaps.extend(_audit_e2e_route_parity(repo_root, prefixes))
        gaps.extend(_audit_frontend_api_parity(repo_root, prefixes))
    metrics = _extract_exported_metrics(repo_root)
    gaps.extend(_audit_metrics_consumers(repo_root, metrics))
    gaps.extend(_audit_nextjs_docker_contracts(repo_root))
    gaps.extend(_audit_alembic_schema_contracts(repo_root))
    gaps.extend(_audit_chroma_collection_parity(repo_root))
    gaps.extend(_audit_pyproject_deps(repo_root))
    gaps.extend(_audit_frontend_execution(repo_root))
    gaps.extend(_audit_env_var_parity(repo_root))
    gaps.extend(_audit_pip_extras_parity(repo_root))
    gaps.extend(_audit_docker_and_compose_contracts(repo_root))
    gaps.extend(_audit_alembic_vs_runtime_schema(repo_root))
    gaps.extend(_audit_api_doc_parity(repo_root))
    gaps.extend(_audit_test_import_prefixes(repo_root))
    gaps.extend(_audit_src_module_reachability(repo_root))
    gaps.extend(_audit_container_static_serving(repo_root))
    gaps.extend(_audit_doc_ast_and_path_parity(repo_root))
    gaps.extend(_audit_dockerfile_pin_parity(repo_root))
    gaps.extend(_audit_db_path_env_parity(repo_root))
    gaps.extend(_audit_cuda_cpu_fallback_parity(repo_root))
    return gaps


def _audit_pyproject_and_ci(repo_root: Path) -> List[str]:
    """Audit pyproject.toml ruff cleanliness, testpaths coverage, and all git-tracked files."""
    gaps = _audit_ci_and_entrypoints(repo_root)
    gaps.extend(_audit_all_git_tracked_files(repo_root))
    gaps.extend(_audit_cross_surface_contracts(repo_root))
    pyproj = repo_root / "pyproject.toml"
    if not pyproj.is_file():
        return gaps
    pyproj_text = pyproj.read_text(encoding="utf-8", errors="replace")
    gaps.extend(_run_repo_ruff_check(repo_root, pyproj_text))
    gaps.extend(_audit_pyproject_testpaths(repo_root, pyproj_text))
    return gaps


def audit_repo_surfaces(repo_root: Path) -> List[str]:
    """Generatively scan 100% of repo files and cross-tree surfaces for defects."""
    resolved_root = repo_root.resolve()
    repo_loaded = _collect_repo_loaded_names(resolved_root)
    gaps: List[str] = []
    for dirpath, dirnames, filenames in os.walk(resolved_root):
        dirnames[:] = sorted(
            d for d in dirnames if d not in EXCLUDED_WALK_DIRS
        )
        for fname in sorted(filenames):
            fpath = Path(dirpath) / fname
            rel = str(fpath.relative_to(resolved_root)).replace("\\", "/")
            if fpath.suffix == ".py":
                gaps.extend(
                    _audit_single_py_file(fpath, rel, extra_loaded=repo_loaded)
                )
            elif fpath.suffix in {".js", ".ts", ".jsx", ".tsx"}:
                gaps.extend(_audit_single_js_file(fpath, rel))
            elif fpath.suffix == ".md":
                gaps.extend(_audit_single_md_file(fpath, rel))
    gaps.extend(_audit_cross_tree_skill_parity(resolved_root))
    gaps.extend(_legacy_hook_and_ci_gaps(resolved_root))
    gaps.extend(_audit_pyproject_and_ci(resolved_root))
    return gaps


def _audit_repo_surface_gaps(repo_root: Path) -> int:
    """Return total count of generative whole-repo surface gaps."""
    return len(audit_repo_surfaces(repo_root))


def _count_unconstrained_vars(z3_data: Mapping[str, Any]) -> int:
    """Return the count of unconstrained Z3 state variables."""
    unconstrained = z3_data.get("unconstrained_variables", [])
    if isinstance(unconstrained, (list, tuple)):
        return len(unconstrained)
    return 0 if unconstrained is None else 1


def _has_valid_audit_surfaces(surfaces: Any) -> bool:
    """Return True if surfaces maps all 4 required audit surfaces to True."""
    if not isinstance(surfaces, Mapping):
        return False
    return all(surfaces.get(key) is True for key in REQUIRED_AUDIT_SURFACES)


def _check_redteam_rubric(redteam_rubric: Any) -> bool:
    """Return True if optional redteam_rubric_score is None or valid Stage 5 BARS."""
    if redteam_rubric is None:
        return True
    if not isinstance(redteam_rubric, Mapping):
        return False
    scores: List[int] = []
    for surface in REQUIRED_AUDIT_SURFACES:
        val = redteam_rubric.get(surface)
        if not _is_valid_bars_int(val) or int(val) < 2:
            return False
        scores.append(int(val))
    return sum(scores) >= int(math.ceil(0.75 * 3.0 * len(scores)))


def _has_valid_manifest_flags(manifest: Mapping[str, Any]) -> bool:
    """Return True if required boolean flags, audit surfaces, and redteam rubric hold."""
    req_bools = (
        "uncapped_discovery",
        "full_suite_executed",
        "closed_loop_reaudit",
        "independent_redteam_reaudit",
    )
    for key in req_bools:
        if manifest.get(key) is not True:
            return False
    if not _has_valid_audit_surfaces(manifest.get("surfaces_audited")):
        return False
    return _check_redteam_rubric(manifest.get("redteam_rubric_score"))


def _is_valid_ledger_entry(
    item: Any,
    exp_sha: str,
    verified_ids: Set[str],
) -> bool:
    """Verify one file_coverage_ledger entry against on-disk SHA-256 and status."""
    if not isinstance(item, Mapping) or item.get("sha256") != exp_sha:
        return False
    status = str(item.get("status", ""))
    if not verified_ids:
        return status == "CLEAN"
    if status == "CLEAN":
        return True
    if status.startswith("FINDING:"):
        fid = status.split(":", 1)[1].strip()
        return fid in verified_ids
    return False


def _check_file_coverage_ledger(
    ledger: Any,
    repo_root: Path,
    verified_ids: Set[str],
    scope_prefix: str = "",
) -> bool:
    """Verify 100% repo or feature file coverage and SHA-256 digests on disk."""
    if not isinstance(ledger, Mapping):
        return False
    expected = build_file_coverage_ledger(repo_root, scope_prefix=scope_prefix)
    if not expected or set(ledger.keys()) != set(expected.keys()):
        return False
    return all(
        _is_valid_ledger_entry(
            ledger.get(rel_p), meta["sha256"], verified_ids
        )
        for rel_p, meta in expected.items()
    )


def _check_wave_history(wave_history: Any) -> bool:
    """Verify wave_history ends with a clean fixed-point wave (files_modified == 0)."""
    if not isinstance(wave_history, list) or not wave_history:
        return False
    if not all(isinstance(w, Mapping) for w in wave_history):
        return False
    last = wave_history[-1]
    return (
        last.get("findings_count") == 0
        and last.get("files_modified") == 0
    )


def _resolve_proof_path(raw_path: Any, repo_root: Path) -> Optional[Path]:
    """Resolve a receipt or transcript path on disk."""
    if not _is_nonempty_str(raw_path):
        return None
    cand = Path(str(raw_path).strip())
    if not cand.is_absolute():
        cand = repo_root.resolve() / cand
    return cand if cand.is_file() else None


def _matches_receipt_repo(obj: Mapping[str, Any], repo_root: Path) -> bool:
    """Verify red-team receipt repo_name matches repo_root when present or inside git repo."""
    expected = repo_root.resolve().name
    declared = obj.get("repo_name")
    if _is_nonempty_str(declared):
        return str(declared).strip() == expected
    return not (repo_root.resolve() / ".git").exists()


def _check_redteam_receipt_file(raw_path: Any, repo_root: Path) -> bool:
    """Verify on-disk Phase 5 red-team receipt contains Stage 5 AIRTIGHT_HALT rubric."""
    target = _resolve_proof_path(raw_path, repo_root)
    if target is None:
        return False
    text = target.read_text(encoding="utf-8", errors="replace")
    match = _RUBRIC_BLOCK_RE.search(text)
    if not match:
        return False
    try:
        obj = json.loads(match.group(1))
    except ValueError:
        return False
    return (
        isinstance(obj, Mapping)
        and obj.get("stage") == 5
        and obj.get("verdict") == "AIRTIGHT_HALT"
        and _matches_receipt_repo(obj, repo_root)
    )


def _is_clean_transcript_line(ln: str) -> bool:
    """Return True if a JSONL transcript line is valid JSON with non-ERROR status."""
    try:
        obj = json.loads(ln)
    except ValueError:
        return False
    if not isinstance(obj, Mapping):
        return False
    return str(obj.get("status", "DONE")).upper() != "ERROR"


def _check_redteam_transcript_file(raw_path: Any, repo_root: Path) -> bool:
    """Verify on-disk red-team .jsonl transcript has >=1 line and 0 errors/blocks."""
    target = _resolve_proof_path(raw_path, repo_root)
    if target is None:
        return False
    raw_txt = target.read_text(encoding="utf-8", errors="replace")
    lines = [ln.strip() for ln in raw_txt.splitlines() if ln.strip()]
    if not lines or not all(_is_clean_transcript_line(ln) for ln in lines):
        return False
    if (repo_root.resolve() / ".git").exists():
        return len(lines) >= 2 and '"tool_calls"' in raw_txt
    return True


def _check_disk_closure_proofs(
    manifest: Mapping[str, Any],
    repo_root: Path,
    verified_ids: Set[str],
) -> bool:
    """Enforce mandatory on-disk file coverage ledger and closure proofs."""
    scope_str = str(manifest.get("scope_prefix", ""))
    if not _check_file_coverage_ledger(
        manifest.get("file_coverage_ledger"), repo_root, verified_ids, scope_str
    ):
        return False
    if verified_ids:
        return True
    return (
        _check_wave_history(manifest.get("wave_history"))
        and _check_redteam_receipt_file(
            manifest.get("redteam_receipt_path"), repo_root
        )
        and _check_redteam_transcript_file(
            manifest.get("redteam_transcript_path"), repo_root
        )
    )


def _has_zero_failure_counts(manifest: Mapping[str, Any]) -> bool:
    """Return True if test_failures, invariant_violations, and transcript errors are 0."""
    keys = (
        "test_failures",
        "invariant_violations",
        "redteam_transcript_errors",
    )
    return all(_non_negative_count(manifest.get(k, 0)) == 0 for k in keys)


def _is_valid_manifest_dict(manifest: Any) -> bool:
    """Return True if manifest is a Mapping with valid flags and zero failure counts."""
    if not isinstance(manifest, Mapping):
        return False
    if not _has_valid_manifest_flags(manifest):
        return False
    return _has_zero_failure_counts(manifest)


def _needs_disk_closure_fail(
    manifest: Mapping[str, Any],
    require_manifest: bool,
    repo_root: Optional[Path],
    verified_ids: Optional[Set[str]],
) -> bool:
    """Return True if disk closure proofs are required and fail validation."""
    if repo_root is None or not require_manifest:
        return False
    v_ids = set() if verified_ids is None else verified_ids
    return not _check_disk_closure_proofs(manifest, repo_root, v_ids)


def _check_exhaustiveness_manifest(
    manifest: Any,
    require_manifest: bool = False,
    repo_root: Optional[Path] = None,
    verified_ids: Optional[Set[str]] = None,
) -> str:
    """Validate exhaustiveness_manifest dict for 4-surface and disk-grounded closure."""
    if manifest is None:
        return "incomplete_exhaustiveness_manifest" if require_manifest else "ok"
    if not _is_valid_manifest_dict(manifest):
        return "incomplete_exhaustiveness_manifest"
    if _needs_disk_closure_fail(
        manifest, require_manifest, repo_root, verified_ids
    ):
        return "incomplete_exhaustiveness_manifest"
    return "ok"


def _extract_raw_findings_and_manifest(
    ast_data: Mapping[str, Any],
    findings_payload: Any,
) -> Tuple[List[Any], Any, bool]:
    """Return `(raw_list, manifest_obj, require_manifest)` from inputs."""
    manifest = ast_data.get("exhaustiveness_manifest")
    if isinstance(findings_payload, Mapping):
        if manifest is None:
            manifest = findings_payload.get("exhaustiveness_manifest")
        items = findings_payload.get(
            "findings",
            findings_payload.get("candidate_items", []),
        )
        raw_list = list(items) if isinstance(items, list) else []
        return raw_list, manifest, True
    if isinstance(findings_payload, list):
        return list(findings_payload), manifest, False
    return [], manifest, False


def _partition_findings(
    raw_items: Sequence[Any],
    repo_root: Path,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, int]]:
    """Partition raw_items into verified and rejected lists with caching."""
    verified: List[Dict[str, Any]] = []
    rejected: List[Dict[str, Any]] = []
    by_category: Dict[str, int] = {cat: 0 for cat in VALID_CATEGORIES}
    line_cache: Dict[Path, List[str]] = {}
    seen_ids: Set[str] = set()

    for item in raw_items:
        ok, reason, norm = validate_finding(
            item, repo_root=repo_root, line_cache=line_cache
        )
        raw_id = norm.get("id")
        finding_id = str(raw_id).strip() if isinstance(raw_id, str) else ""
        if ok and finding_id:
            if finding_id in seen_ids:
                ok = False
                reason = "duplicate_finding_id"
            else:
                seen_ids.add(finding_id)
        if ok:
            verified.append(norm)
            by_category[norm["category"]] += 1
        else:
            rejected_entry = dict(norm)
            rejected_entry["rejection_reason"] = reason
            rejected.append(rejected_entry)
    return verified, rejected, by_category


def _has_unreported_surface_gaps(
    surface_gaps: Sequence[str],
    verified: Sequence[Mapping[str, Any]],
) -> bool:
    """Return True if any file-scoped surface gap is not covered by verified findings."""
    covered_files = {
        str(f.get("file_and_line", "")).split(":", 1)[0].replace("\\", "/")
        for f in verified
    }
    for gap in surface_gaps:
        if ": " in gap:
            gap_file = gap.split(": ", 1)[0].replace("\\", "/")
            if gap_file not in covered_files:
                return True
    return False


def _finalize_exhaustiveness_status(
    base_status: str,
    require_manifest: bool,
    verified: Sequence[Mapping[str, Any]],
    surface_gaps: Sequence[str],
) -> str:
    """Check whether file-scoped surface gaps were left unreported in findings."""
    if not require_manifest or base_status != "ok" or not verified:
        return base_status
    if _has_unreported_surface_gaps(surface_gaps, verified):
        return "unreported_surface_gaps"
    return base_status


def _is_airtight_state(
    verified_count: int,
    ast_gaps: int,
    z3_status: str,
    z3_unconstrained: int,
    exh_status: str,
) -> bool:
    """Return True if all 5 coherence closure conditions hold simultaneously."""
    if verified_count != 0 or ast_gaps != 0 or z3_unconstrained != 0:
        return False
    return z3_status == "SAT" and exh_status == "ok"


def _resolve_tri_state_status(
    require_manifest: bool,
    exhaustiveness_status: str,
    is_airtight: bool,
) -> Tuple[str, int, int]:
    """Return `(status, action_declare_airtight_halt, action_propose_invariant_fix)`."""
    if require_manifest and exhaustiveness_status != "ok":
        return "INCOMPLETE_AUDIT_RETRY", 0, 0
    if is_airtight:
        return "AIRTIGHT_HALT", 1, 0
    return "PROCEED_FIX", 0, 1


def evaluate_bake_inputs(
    ast_data: Mapping[str, Any],
    z3_data: Mapping[str, Any],
    findings_payload: Any,
    repo_root: Path,
) -> Dict[str, Any]:
    """Evaluate AST audit, Z3 proof, exhaustiveness manifest, and findings."""
    surface_gap_details = audit_repo_surfaces(repo_root)
    raw_contract_gaps = max(
        _non_negative_count(ast_data.get("contract_gaps", 0)),
        _count_non_test_high_complexity(ast_data),
    )
    ast_contract_gaps = (
        raw_contract_gaps
        + _non_negative_count(ast_data.get("unindexed_hot_paths", 0))
        + len(surface_gap_details)
    )
    z3_status = str(z3_data.get("status", "SAT")).strip().upper()
    z3_unconstrained_count = _count_unconstrained_vars(z3_data)

    raw_items, manifest, req_manifest = _extract_raw_findings_and_manifest(
        ast_data, findings_payload
    )
    verified, rejected, by_category = _partition_findings(raw_items, repo_root)
    verified_ids = {str(f["id"]) for f in verified}
    base_exh = _check_exhaustiveness_manifest(
        manifest,
        require_manifest=req_manifest,
        repo_root=repo_root,
        verified_ids=verified_ids,
    )
    exhaustiveness_status = _finalize_exhaustiveness_status(
        base_exh, req_manifest, verified, surface_gap_details
    )
    is_airtight = _is_airtight_state(
        len(verified),
        ast_contract_gaps,
        z3_status,
        z3_unconstrained_count,
        exhaustiveness_status,
    )
    status, act_halt, act_fix = _resolve_tri_state_status(
        req_manifest, exhaustiveness_status, is_airtight
    )

    cert_payload = json.dumps(
        {
            "status": status,
            "ast_contract_gaps": ast_contract_gaps,
            "z3_status": z3_status,
            "z3_unconstrained_count": z3_unconstrained_count,
            "exhaustiveness_status": exhaustiveness_status,
            "verified_findings": verified,
            "rejected_count": len(rejected),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    certificate_sha256 = hashlib.sha256(
        cert_payload.encode("utf-8")
    ).hexdigest()

    return {
        "status": status,
        "action_declare_airtight_halt": act_halt,
        "action_propose_invariant_fix": act_fix,
        "ast_contract_gaps": ast_contract_gaps,
        "surface_gap_details": surface_gap_details,
        "z3_status": z3_status,
        "z3_unconstrained_count": z3_unconstrained_count,
        "exhaustiveness_status": exhaustiveness_status,
        "verified_findings_count": len(verified),
        "rejected_speculative_count": len(rejected),
        "verified_by_category": by_category,
        "verified_findings": verified,
        "rejected_findings": rejected,
        "certificate_sha256": certificate_sha256,
    }


def _load_json_file(path: Path) -> Any:
    """Read and parse a UTF-8 JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json_file(path: Path, payload: Mapping[str, Any]) -> None:
    """Write a JSON object with UTF-8 encoding and LF newlines."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=False) + "\n"
    path.write_bytes(text.replace("\r\n", "\n").encode("utf-8"))


def _build_bad_test_findings() -> List[Dict[str, Any]]:
    """Return 7 invalid findings exercising all rejection gates."""
    return [
        {
            "id": "SPEC-1",
            "category": "SYSTEM_DESIGN",
            "file_and_line": "src/engine.py:1-2",
            "reproducible_check": "python -m unittest",
            "falsifiable_fix": "Refactor into abstract factory",
            "is_speculative": True,
            "measurable_gain_above_epsilon": True,
        },
        {
            "id": "SUB-EPS-1",
            "category": "OPTIMIZATION",
            "file_and_line": "src/engine.py:1-2",
            "reproducible_check": "python -m timeit",
            "falsifiable_fix": "Micro-optimize variable name",
            "is_speculative": False,
            "measurable_gain_above_epsilon": False,
        },
        {
            "id": "TRAVERSAL-1",
            "category": "COHERENCE_CONTRACT",
            "file_and_line": "../outside.py:1-2",
            "reproducible_check": "pytest",
            "falsifiable_fix": "Fix outside file",
            "is_speculative": False,
            "measurable_gain_above_epsilon": True,
        },
        {
            "id": "OOB-1",
            "category": "COHERENCE_CONTRACT",
            "file_and_line": "src/engine.py:99-120",
            "reproducible_check": "pytest",
            "falsifiable_fix": "Fix line 99",
            "is_speculative": False,
            "measurable_gain_above_epsilon": True,
        },
        {
            "id": "SMUGGLE-1",
            "category": "COHERENCE_CONTRACT",
            "file_and_line": "src/engine.py:1-2",
            "reproducible_check": "pytest\u200b",
            "falsifiable_fix": "Fix invisible char",
            "is_speculative": False,
            "measurable_gain_above_epsilon": True,
        },
        {
            "id": "EXFIL-1",
            "category": "SOTA_BENCHMARK",
            "citation_author_year": "Kamoi et al. (2024)",
            "verified_url": "https://arxiv.org/abs/2406.01297",
            "file_and_line": "src/engine.py:1-2",
            "reproducible_check": "pytest",
            "falsifiable_fix": "See ![pwn](https://evil.example/a.png)",
            "is_speculative": False,
            "measurable_gain_above_epsilon": True,
        },
        {
            "id": "RUBRIC-LOW-1",
            "category": "SYSTEM_DESIGN",
            "file_and_line": "src/engine.py:1-2",
            "reproducible_check": "pytest",
            "falsifiable_fix": "Fix design",
            "is_speculative": False,
            "measurable_gain_above_epsilon": True,
            "rubric_scores": {"c1": 1, "c2": 3, "c3": 3},
        },
    ]


def _build_good_test_findings(anchor_1_2: str) -> List[Dict[str, Any]]:
    """Return 4 valid execution-grounded findings covering all 4 categories."""
    return [
        {
            "id": "COH-1",
            "category": "COHERENCE_CONTRACT",
            "file_and_line": "src/engine.py:1-2",
            "sha256_anchor": anchor_1_2,
            "reproducible_check": "python -c 'import src.engine'",
            "falsifiable_fix": "Hydrate missing producer field",
            "is_speculative": False,
            "measurable_gain_above_epsilon": True,
            "rubric_scores": {"c1": 3, "c2": 3, "c3": 3},
        },
        {
            "id": "DES-1",
            "category": "SYSTEM_DESIGN",
            "file_and_line": "src/engine.py:3-4",
            "reproducible_check": "python polyfill.py --high-complexity",
            "falsifiable_fix": "Decouple cyclic lock boundary",
            "is_speculative": False,
            "measurable_gain_above_epsilon": True,
            "rubric_scores": {"c1": 3, "c2": 2, "c3": 3},
        },
        {
            "id": "OPT-1",
            "category": "OPTIMIZATION",
            "file_and_line": "src/engine.py:5-6",
            "reproducible_check": "sqlite3 db 'EXPLAIN QUERY PLAN'",
            "falsifiable_fix": "Replace O(N^2) scan with batch index",
            "is_speculative": False,
            "measurable_gain_above_epsilon": True,
            "rubric_scores": {"c1": 3, "c2": 3, "c3": 2},
        },
        {
            "id": "SOTA-1",
            "category": "SOTA_BENCHMARK",
            "citation_author_year": "Kamoi et al. (TACL 2024)",
            "verified_url": "https://arxiv.org/abs/2406.01297",
            "file_and_line": "src/engine.py:7-8",
            "reproducible_check": (
                "python coherence_bake_gate.py --self-test"
            ),
            "falsifiable_fix": "Gate refinement on deterministic verifier",
            "is_speculative": False,
            "measurable_gain_above_epsilon": True,
            "rubric_scores": {"c1": 3, "c2": 3, "c3": 3},
        },
    ]


def _verify_manifest_self_test(repo_root: Path, anchor: str) -> Optional[str]:
    """Test Tri-State Gate, file_coverage_ledger, and disk closure proofs."""
    ast_ok = {"contract_gaps": 0, "unindexed_hot_paths": 0}
    z3_ok = {"status": "SAT", "unconstrained_variables": []}
    good_items = _build_good_test_findings(anchor)
    res_inc = evaluate_bake_inputs(
        ast_ok, z3_ok, {"findings": good_items}, repo_root
    )
    if res_inc["status"] != "INCOMPLETE_AUDIT_RETRY":
        return f"Expected INCOMPLETE_AUDIT_RETRY, got {res_inc['status']}"

    rt_receipt = repo_root / "rt_receipt.md"
    rt_receipt.write_text(
        '<RUBRIC_SCORE>\n{"stage": 5, "verdict": "AIRTIGHT_HALT"}\n</RUBRIC_SCORE>\n',
        encoding="utf-8",
    )
    rt_trans = repo_root / "rt_transcript.jsonl"
    rt_trans.write_text('{"step": 1, "status": "DONE"}\n', encoding="utf-8")
    ledger = build_file_coverage_ledger(repo_root)
    manifest = {
        "uncapped_discovery": True,
        "full_suite_executed": True,
        "closed_loop_reaudit": True,
        "independent_redteam_reaudit": True,
        "surfaces_audited": {k: True for k in REQUIRED_AUDIT_SURFACES},
        "redteam_rubric_score": {k: 3 for k in REQUIRED_AUDIT_SURFACES},
        "test_failures": 0,
        "invariant_violations": 0,
        "redteam_transcript_errors": 0,
        "file_coverage_ledger": ledger,
        "wave_history": [{"wave": 1, "findings_count": 0, "files_modified": 0}],
        "redteam_receipt_path": "rt_receipt.md",
        "redteam_transcript_path": "rt_transcript.jsonl",
    }
    res_halt = evaluate_bake_inputs(
        ast_ok,
        z3_ok,
        {"findings": [], "exhaustiveness_manifest": manifest},
        repo_root,
    )
    if res_halt["status"] != "AIRTIGHT_HALT":
        return f"Expected manifest AIRTIGHT_HALT, got {res_halt}"
    return None


def _verify_manifest_parity_self_test(root: Path) -> Optional[str]:
    """Verify env-var, pip-extras, worker --watch, and Alembic drift checks in self-test."""
    (root / ".env.example").write_text("PP_UNREAD_VAR=1\n", encoding="utf-8")
    (root / "Dockerfile").write_text(
        'RUN pip install ".[ml]"\nCOPY src/ src/\nFROM runtime AS worker\nENTRYPOINT ["pp-feed"]\n',
        encoding="utf-8",
    )
    (root / "Dockerfile.backfill").write_text(
        "RUN pip install .[ml]\n", encoding="utf-8"
    )
    (root / "alembic").mkdir(parents=True, exist_ok=True)
    (root / "alembic" / "env.py").write_text(
        'url = "sqlite:///data/api.db"\n', encoding="utf-8"
    )
    (root / "loadtest").mkdir(parents=True, exist_ok=True)
    (root / "loadtest" / "locustfile.py").write_text(
        'self.client.get("/catalog/top")\nisinstance(data, list)\nself.client.get("/catalog/feed?tab=golden")\n',
        encoding="utf-8",
    )
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "API.md").write_text(
        "SingleWriterDB.compact_database()\n", encoding="utf-8"
    )
    (root / "src" / "infrastructure").mkdir(parents=True, exist_ok=True)
    (root / "tests").mkdir(parents=True, exist_ok=True)
    (root / "tests" / "test_inf.py").write_text(
        "import fastapi\nfrom infrastructure.network import foo\n",
        encoding="utf-8",
    )
    gaps = _audit_cross_surface_contracts(root)
    expected_tokens = (
        "unread application env var PP_UNREAD_VAR",
        "undefined extra [ml]",
        "pip install local package before COPY src/",
        "missing --watch",
        "stale fallback sqlite:///data/api.db",
        "unimported dependency flask",
        "/catalog/top returns dict",
        "/catalog/feed does not accept ?tab=",
        "stale API contract token SingleWriterDB.compact_database()",
        "bare infrastructure import missing src. prefix",
    )
    for tok in expected_tokens:
        if not any(tok in g for g in gaps):
            return f"Expected '{tok}' in self-test gaps, got {gaps}"
    return _verify_reachability_and_pin_self_test(root)


def _verify_reachability_and_pin_self_test(root: Path) -> Optional[str]:
    """Verify module reachability, StaticFiles mount, doc AST parity, and pin drift."""
    (root / ".git").mkdir(parents=True, exist_ok=True)
    (root / "src" / "infrastructure" / "orphan.py").write_text(
        'import os\nx = os.environ.get("DB_PATH", "/tmp/a.db")\n', encoding="utf-8"
    )
    (root / "Dockerfile.railway").write_text(
        "COPY --from=fe /out /static/public\n", encoding="utf-8"
    )
    (root / "src" / "web" / "server.py").write_text(
        'app.mount("/static", None)\n', encoding="utf-8"
    )
    (root / "README.md").write_text("StorePollerService\n", encoding="utf-8")
    (root / "Dockerfile.backend").write_text(
        "FROM python:3.11-slim\n", encoding="utf-8"
    )
    (root / "src" / "orchestration").mkdir(parents=True, exist_ok=True)
    (root / "src" / "orchestration" / "watchdog.py").write_text(
        'db_path = "db.sqlite"\n', encoding="utf-8"
    )
    (root / "src" / "gpu_pipeline").mkdir(parents=True, exist_ok=True)
    (root / "src" / "gpu_pipeline" / "models.py").write_text(
        'x = torch.zeros(1, device="cuda")\n', encoding="utf-8"
    )
    (root / "src" / "gpu_pipeline" / "daemon.py").write_text(
        'os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"\n'
        "torch.cuda.set_per_process_memory_fraction(0.85)\n",
        encoding="utf-8",
    )
    gaps = _audit_cross_surface_contracts(root)
    expected = (
        "unreferenced src module missing test coverage",
        "server.py does not mount StaticFiles",
        "nginx missing location /static proxy for mounted StaticFiles",
        "legacy TensorFlow/python3.11 or pip install before COPY src",
        "DB_PATH read without PP_DB_PATH fallback parity",
        "unguarded CUDA allocation without CPU fallback",
        "unconditional expandable_segments on Windows",
        "unguarded CUDA memory fraction without CPU fallback",
        "stale AST symbol or case-mismatched path StorePollerService",
        "base image or dependency version pin drift",
        "stale db.sqlite default path",
    )
    for tok in expected:
        if not any(tok in g for g in gaps):
            return f"Expected '{tok}' in reachability self-test, got {gaps}"
    return None


def _verify_cross_surface_self_test() -> Optional[str]:
    """Verify cross-surface route, metric, Next.js Docker, and Alembic contract checks."""
    with tempfile.TemporaryDirectory() as tmp_str:
        root = Path(tmp_str)
        routes_p = root / "src" / "web" / "routes.py"
        routes_p.parent.mkdir(parents=True, exist_ok=True)
        routes_p.write_text(
            '@router.get("/health")\n# TYPE private_press_uptime_seconds gauge\n',
            encoding="utf-8",
        )
        (root / "nginx.conf").write_text(
            "location /ghost {\n  proxy_pass http://api:8000;\n}\n",
            encoding="utf-8",
        )
        (root / "scripts").mkdir(parents=True, exist_ok=True)
        (root / "scripts" / "verify_db.py").write_text(
            'collection = client.get_collection(name="promo_collection")\n',
            encoding="utf-8",
        )
        (root / "pyproject.toml").write_text(
            '[project]\ndependencies = ["flask>=3.0.0", "spotipy>=2.23.0"]\n',
            encoding="utf-8",
        )
        gaps = _audit_cross_surface_contracts(root)
        if not any("nginx proxies non-existent route /ghost" in g for g in gaps):
            return f"Expected nginx route drift gap, got {gaps}"
        if not any("promo_collection" in g for g in gaps):
            return f"Expected scripts/verify_db.py promo_collection gap, got {gaps}"
        if not any("flask" in g for g in gaps):
            return f"Expected dead pyproject dependency gap, got {gaps}"
        return _verify_manifest_parity_self_test(root)


def run_self_test() -> Tuple[int, List[str]]:
    """Run deterministic self-tests for all acceptance and rejection gates."""
    with tempfile.TemporaryDirectory() as tmp_dir_str:
        repo_root = Path(tmp_dir_str)
        engine_py = repo_root / "src" / "engine.py"
        engine_py.parent.mkdir(parents=True, exist_ok=True)
        sample_lines = [
            f"def step_{idx}(x: int) -> int:\n    return x + {idx}\n"
            for idx in range(5)
        ]
        engine_py.write_bytes("".join(sample_lines).encode("utf-8"))

        ast_ok = {"contract_gaps": 0, "unindexed_hot_paths": 0}
        z3_ok = {"status": "SAT", "unconstrained_variables": []}

        res_empty = evaluate_bake_inputs(ast_ok, z3_ok, [], repo_root)
        if res_empty["status"] != "AIRTIGHT_HALT":
            return 1, [f"Expected AIRTIGHT_HALT, got {res_empty['status']}"]

        res_bad = evaluate_bake_inputs(
            ast_ok, z3_ok, _build_bad_test_findings(), repo_root
        )
        if res_bad["rejected_speculative_count"] != 7:
            return 1, [f"Expected 7 rejected findings, got {res_bad}"]

        anchor = compute_slice_sha256(engine_py, 1, 2)
        res_good = evaluate_bake_inputs(
            ast_ok, z3_ok, _build_good_test_findings(anchor), repo_root
        )
        if res_good["verified_findings_count"] != 4:
            return 1, [f"Expected 4 verified findings, got {res_good}"]

        err_msg = _verify_manifest_self_test(repo_root, anchor)
        if err_msg is not None:
            return 1, [err_msg]
        cs_err = _verify_cross_surface_self_test()
        if cs_err is not None:
            return 1, [cs_err]

    return 0, ["SELF_TEST_OK: coherence_bake_gate verified all 4 categories."]


def _build_arg_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser for coherence_bake_gate."""
    parser = argparse.ArgumentParser(
        description=(
            "Deterministic Diminishing-Returns & Full-System Coherence Gate."
        )
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run built-in deterministic unit tests and exit.",
    )
    parser.add_argument(
        "--build-ledger",
        nargs=2,
        metavar=("REPO_ROOT", "OUT_JSON"),
        help="Build 100% repository file_coverage_ledger JSON.",
    )
    parser.add_argument(
        "--audit-repo",
        metavar="REPO_ROOT",
        help="Run generative whole-repo surface audit and exit 0 if clean.",
    )
    parser.add_argument(
        "ast_json", nargs="?", help="Path to Stage 0 AST JSON artifact."
    )
    parser.add_argument(
        "z3_json", nargs="?", help="Path to Stage 0 Z3/SMT JSON artifact."
    )
    parser.add_argument(
        "findings_json", nargs="?", help="Path to candidate findings JSON."
    )
    parser.add_argument(
        "output_json", nargs="?", help="Path to write gate decision JSON."
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root directory for validating file containment.",
    )
    parser.add_argument(
        "--scope",
        default="",
        help="Optional feature subpath prefix (defaults to 100%% of repo_root).",
    )
    return parser


def _normalize_cli_findings_payload(
    findings_data: Any,
    scope_prefix: str,
) -> Mapping[str, Any]:
    """Enforce 100% repo/feature manifest requirement by default on CLI inputs."""
    if isinstance(findings_data, Mapping):
        payload = dict(findings_data)
    elif isinstance(findings_data, list):
        payload = {"findings": findings_data}
    else:
        payload = {"findings": []}
    if scope_prefix and isinstance(payload.get("exhaustiveness_manifest"), Mapping):
        manifest = dict(payload["exhaustiveness_manifest"])
        manifest.setdefault("scope_prefix", scope_prefix)
        payload["exhaustiveness_manifest"] = manifest
    return payload


def _execute_cli_gate(args: argparse.Namespace) -> int:
    """Load JSON inputs, run evaluate_bake_inputs, and write output JSON."""
    try:
        ast_data = _load_json_file(Path(args.ast_json))
        z3_data = _load_json_file(Path(args.z3_json))
        raw_findings = _load_json_file(Path(args.findings_json))
        findings_data = _normalize_cli_findings_payload(
            raw_findings, args.scope
        )
        result = evaluate_bake_inputs(
            ast_data=ast_data if isinstance(ast_data, Mapping) else {},
            z3_data=z3_data if isinstance(z3_data, Mapping) else {},
            findings_payload=findings_data,
            repo_root=Path(args.repo_root),
        )
        _write_json_file(Path(args.output_json), result)
    except (OSError, ValueError, KeyError) as exc:
        print(f"ERROR: coherence_bake_gate failed: {exc}", file=sys.stderr)
        return 1

    print(
        f"COHERENCE_BAKE_GATE: status={result['status']} "
        f"verified={result['verified_findings_count']} "
        f"rejected={result['rejected_speculative_count']}"
    )
    return 2 if result["status"] == "INCOMPLETE_AUDIT_RETRY" else 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point for coherence_bake_gate."""
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    if args.self_test:
        code, msgs = run_self_test()
        for msg in msgs:
            print(msg)
        return code
    if args.build_ledger:
        root_p, out_p = Path(args.build_ledger[0]), Path(args.build_ledger[1])
        _write_json_file(
            out_p, build_file_coverage_ledger(root_p, scope_prefix=args.scope)
        )
        return 0
    if args.audit_repo:
        gaps = audit_repo_surfaces(Path(args.audit_repo))
        for gap in gaps:
            print(gap)
        return 1 if gaps else 0
    if not all(
        (args.ast_json, args.z3_json, args.findings_json, args.output_json)
    ):
        parser.error(
            "ast_json, z3_json, findings_json, and output_json are required "
            "unless --self-test, --build-ledger, or --audit-repo is set."
        )
    return _execute_cli_gate(args)


if __name__ == "__main__":
    sys.exit(main())
