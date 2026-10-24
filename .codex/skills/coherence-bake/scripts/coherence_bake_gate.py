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


def build_file_coverage_ledger(
    repo_root: Path,
) -> Dict[str, Dict[str, str]]:
    """Walk repo_root and build a deterministic SHA-256 ledger of scannable files."""
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


def _unused_upper_consts(tree: ast.Module) -> List[str]:
    """Return module-level UPPER_CASE constants never loaded in tree."""
    defined: Set[str] = set()
    loaded: Set[str] = set()
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


def _audit_single_py_file(py_path: Path, rel_path: str) -> List[str]:
    """Audit a Python file for syntax, unused constants, and McCabe <= 9."""
    try:
        source = py_path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
    except SyntaxError as exc:
        return [f"{rel_path}: SyntaxError ({exc})"]
    gaps = [
        f"{rel_path}: unused constant {cname}"
        for cname in _unused_upper_consts(tree)
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


def _audit_single_md_file(md_path: Path, rel_path: str) -> List[str]:
    """Audit a Markdown file for broken relative links outside code blocks."""
    text = md_path.read_text(encoding="utf-8", errors="replace")
    cleaned = re.sub(r"```[\s\S]*?```", "", text)
    cleaned = re.sub(r"`[^`\n]+`", "", cleaned)
    gaps: List[str] = []
    for match in _REL_MD_LINK_RE.finditer(cleaned):
        target = match.group(1).strip()
        if not target or "<" in target or ">" in target or "[" in target:
            continue
        if not (md_path.parent / target).resolve().exists():
            gaps.append(f"{rel_path}: broken relative link {target}")
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
    if (ag_skill_dir / ec_name).is_file() != (peer_skill_dir / ec_name).is_file():
        gaps.append(f"{peer_label}/{ec_name}: companion edge-cases drift")
    for script_p in sorted((ag_skill_dir / "scripts").glob("*.py")) if (ag_skill_dir / "scripts").is_dir() else ():
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
    if ci_yml.is_file():
        gaps += _missing_token_count(
            ci_yml.read_text(encoding="utf-8", errors="replace"),
            (
                "coherence_bake_gate.py --self-test",
                "rubric_grade_gate.py --self-test",
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


def audit_repo_surfaces(repo_root: Path) -> List[str]:
    """Generatively scan 100% of repo files and cross-tree surfaces for defects."""
    resolved_root = repo_root.resolve()
    gaps: List[str] = []
    for dirpath, dirnames, filenames in os.walk(resolved_root):
        dirnames[:] = sorted(
            d for d in dirnames if d not in EXCLUDED_WALK_DIRS
        )
        for fname in sorted(filenames):
            fpath = Path(dirpath) / fname
            rel = str(fpath.relative_to(resolved_root)).replace("\\", "/")
            if fpath.suffix == ".py":
                gaps.extend(_audit_single_py_file(fpath, rel))
            elif fpath.suffix in {".js", ".ts"}:
                gaps.extend(_audit_single_js_file(fpath, rel))
            elif fpath.suffix == ".md":
                gaps.extend(_audit_single_md_file(fpath, rel))
    gaps.extend(_audit_cross_tree_skill_parity(resolved_root))
    gaps.extend(_legacy_hook_and_ci_gaps(resolved_root))
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
) -> bool:
    """Verify 100% repository file coverage and SHA-256 digests on disk."""
    if not isinstance(ledger, Mapping):
        return False
    expected = build_file_coverage_ledger(repo_root)
    if set(ledger.keys()) != set(expected.keys()):
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
    )


def _check_redteam_transcript_file(raw_path: Any, repo_root: Path) -> bool:
    """Verify on-disk red-team .jsonl transcript has >=1 line and 0 errors/blocks."""
    target = _resolve_proof_path(raw_path, repo_root)
    if target is None:
        return False
    lines = [
        ln.strip()
        for ln in target.read_text(encoding="utf-8", errors="replace").splitlines()
        if ln.strip()
    ]
    if not lines:
        return False
    for ln in lines:
        if (
            '"status": "ERROR"' in ln
            or '"status":"ERROR"' in ln
            or "BLOCKED by BRC" in ln
        ):
            return False
    return True


def _check_disk_closure_proofs(
    manifest: Mapping[str, Any],
    repo_root: Path,
    verified_ids: Set[str],
) -> bool:
    """Enforce mandatory on-disk file coverage ledger and closure proofs."""
    if not _check_file_coverage_ledger(
        manifest.get("file_coverage_ledger"), repo_root, verified_ids
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
    return parser


def _execute_cli_gate(args: argparse.Namespace) -> int:
    """Load JSON inputs, run evaluate_bake_inputs, and write output JSON."""
    try:
        ast_data = _load_json_file(Path(args.ast_json))
        z3_data = _load_json_file(Path(args.z3_json))
        findings_data = _load_json_file(Path(args.findings_json))
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
        _write_json_file(out_p, build_file_coverage_ledger(root_p))
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
