"""Universal Rubric-Graded Qualitative Judgment Gate for Stages 0-5.

Evaluates qualitative LLM judgments against a Behaviorally Anchored Rating
Scale (0..3 BARS) with lexical evidence-first ordering (Bagaria et al. 2026),
physical file and line span verification, and non-compensatory Cobb-Douglas
aggregation (Lee et al. 2024 CheckEval; Kim et al. 2024 Prometheus 2;
Wei et al. 2025 RocketEval).

Usage:
    python rubric_grade_gate.py <input_path> [--repo-root <dir>]
    python rubric_grade_gate.py --self-test
"""
import argparse
import ast
import hashlib
import json
import math
import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

VALID_VERDICTS: Tuple[str, ...] = (
    "APPROVE",
    "REJECT",
    "PROCEED",
    "HALT",
    "TIER_0",
    "TIER_1",
    "TIER_2",
    "AIRTIGHT_HALT",
    "PROCEED_FIX",
)
APPROVAL_VERDICTS: Tuple[str, ...] = ("APPROVE", "PROCEED", "AIRTIGHT_HALT")
REJECTION_VERDICTS: Tuple[str, ...] = ("REJECT", "PROCEED_FIX")

_RUBRIC_TAG_RE = re.compile(
    r"<RUBRIC_SCORE>\s*(?P<json>\{[\s\S]*?\})\s*</RUBRIC_SCORE>",
    re.IGNORECASE,
)
_CRITERION_OBJ_RE = re.compile(r"\{[^{}]*\}")
_FILE_SPAN_RE = re.compile(
    r"^(?P<path>[^:#\s]+)(?::|#L)(?P<start>\d+)(?:-(?:L)?(?P<end>\d+))?$"
)
_PROSE_VERDICT_RE = re.compile(
    r"\[(?:GLOBAL\s+)?VERDICT:\s*([A-Za-z0-9_]+)\]",
    re.IGNORECASE,
)
ANTI_LOOPHOLE_PATH_RE = re.compile(
    r"(?i)(?:^|[/\\])(?:\.github[/\\]workflows[/\\]|hooks[/\\]|scripts[/\\]|(?:AGENTS|CLAUDE|CODEX)\.md$|mcp_config\.json$|\.mcp\.json$|hooks\.json$|settings\.json$|config\.toml$|\.gitignore$|\.pre-commit-config\.yaml$)|(?:\.ps1|\.sh|\.bat|\.cmd)$"
)


def _is_strict_int(value: Any) -> bool:
    """Return True if value is an int and not a bool."""
    return isinstance(value, int) and not isinstance(value, bool)


def _is_nonempty_str(value: Any) -> bool:
    """Return True if value is a non-empty, non-whitespace string."""
    return isinstance(value, str) and bool(value.strip())


def extract_all_rubric_json_strs(raw_text: str) -> List[str]:
    """Extract all <RUBRIC_SCORE> JSON blocks or a single raw JSON string."""
    blocks = [m.group("json").strip() for m in _RUBRIC_TAG_RE.finditer(raw_text)]
    if blocks:
        return blocks
    stripped = raw_text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return [stripped]
    return []


def extract_rubric_json_str(raw_text: str) -> Optional[str]:
    """Extract JSON string from the first <RUBRIC_SCORE> block or raw JSON."""
    blocks = extract_all_rubric_json_strs(raw_text)
    return blocks[0] if blocks else None


def check_lexical_evidence_precedence(raw_json: str) -> Tuple[bool, str]:
    """Verify 'evidence' precedes 'score' inside each criterion object."""
    for obj_match in _CRITERION_OBJ_RE.finditer(raw_json):
        chunk = obj_match.group(0)
        if '"score"' not in chunk and '"evidence"' not in chunk:
            continue
        ev_idx = chunk.find('"evidence"')
        sc_idx = chunk.find('"score"')
        if ev_idx < 0 or sc_idx < 0:
            return False, "criterion_missing_evidence_or_score_key"
        if sc_idx < ev_idx:
            return False, "score_precedes_evidence"
    return True, "ok"


def _resolve_repo_target(
    raw_path: str,
    repo_root: Path,
) -> Tuple[Optional[Path], str]:
    """Resolve raw_path inside repo_root and verify it is a file."""
    resolved_root = repo_root.resolve()
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = resolved_root / candidate
    try:
        target = candidate.resolve(strict=True)
        target.relative_to(resolved_root)
    except (OSError, ValueError):
        return None, "evidence_path_outside_repo_or_missing"
    if not target.is_file():
        return None, "evidence_target_not_a_file"
    return target, "ok"


_HEX_ANCHOR_RE = re.compile(r"^[0-9a-f]{8,64}$")
_VALID_Z3_ENGINES: Tuple[str, ...] = ("z3-solver", "stdlib-finite-domain")
_WITNESS_KEYS: Tuple[str, ...] = (
    "sha256_anchor",
    "witness_symbol",
    "z3_receipt",
)


def _extract_file_span_slice(
    evidence_str: str,
    repo_root: Path,
) -> Tuple[Optional[Tuple[Path, List[str], int, int]], str]:
    """Extract (target, slice_lines, start_line, end_line) when evidence is a file span."""
    cleaned = evidence_str.strip()
    match = _FILE_SPAN_RE.match(cleaned)
    if cleaned.startswith(("https://", "http://")) or not match:
        return None, "ok"
    start_line = int(match.group("start"))
    end_grp = match.group("end")
    end_line = int(end_grp) if end_grp else start_line
    if start_line < 1 or end_line < start_line:
        return None, "invalid_evidence_line_range"

    target, path_reason = _resolve_repo_target(
        match.group("path").strip(), repo_root
    )
    if target is None:
        return None, path_reason
    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    if end_line > len(lines):
        return None, "evidence_line_range_out_of_bounds"
    return (target, lines[start_line - 1 : end_line], start_line, end_line), "ok"


def _resolve_evidence_span(
    evidence_str: str,
    repo_root: Path,
) -> Tuple[bool, str]:
    """Verify file existence and line range when evidence is a file span."""
    _, reason = _extract_file_span_slice(evidence_str, repo_root)
    return reason == "ok", reason


def _verify_slice_sha256(
    slice_lines: Sequence[str],
    expected_prefix: str,
) -> Tuple[bool, str]:
    """Verify slice_lines SHA-256 hex digest matches expected_prefix (>=8 hex chars)."""
    prefix = expected_prefix.strip().lower()
    actual = hashlib.sha256("\n".join(slice_lines).encode("utf-8")).hexdigest()
    if not _HEX_ANCHOR_RE.match(prefix) or not actual.startswith(prefix):
        return False, "evidence_sha256_anchor_mismatch"
    return True, "ok"


def _node_matches_symbol_in_span(
    node: ast.AST,
    symbol: str,
    start_line: int,
    end_line: int,
) -> bool:
    """Return True if AST node matches symbol and overlaps [start_line, end_line]."""
    lineno = getattr(node, "lineno", None)
    if lineno is None:
        return False
    end_lineno = getattr(node, "end_lineno", lineno) or lineno
    if end_lineno < start_line or lineno > end_line:
        return False
    names = (
        getattr(node, "name", None),
        getattr(node, "id", None),
        getattr(node, "attr", None),
    )
    return symbol in names


def _py_ast_has_symbol_in_span(
    full_text: str,
    symbol: str,
    start_line: int,
    end_line: int,
) -> bool:
    """Return True if full_text AST contains symbol overlapping [start_line, end_line]."""
    try:
        tree = ast.parse(full_text)
    except SyntaxError:
        return False
    return any(
        _node_matches_symbol_in_span(node, symbol, start_line, end_line)
        for node in ast.walk(tree)
    )


def _verify_ast_symbol_span(
    target: Path,
    slice_lines: Sequence[str],
    start_line: int,
    end_line: int,
    symbol: str,
) -> Tuple[bool, str]:
    """Verify symbol exists in AST span (for .py) or slice text (for non-.py)."""
    sym = symbol.strip()
    if not sym:
        return False, "evidence_witness_symbol_missing"
    if target.suffix.lower() == ".py":
        full_text = target.read_text(encoding="utf-8", errors="replace")
        found = _py_ast_has_symbol_in_span(full_text, sym, start_line, end_line)
    else:
        found = sym in "\n".join(slice_lines)
    return (True, "ok") if found else (False, "evidence_witness_symbol_missing")


def _verify_z3_receipt_ref(
    raw_ref: str,
    repo_root: Path,
) -> Tuple[bool, str]:
    """Verify raw_ref points to a JSON Stage 0 proof receipt with status=SAT."""
    target, _ = _resolve_repo_target(raw_ref.strip(), repo_root)
    if target is None:
        return False, "invalid_z3_witness_receipt"
    try:
        data = json.loads(target.read_text(encoding="utf-8", errors="replace"))
    except ValueError:
        data = None
    if not isinstance(data, Mapping):
        return False, "invalid_z3_witness_receipt"
    if (data.get("status"), data.get("engine") in _VALID_Z3_ENGINES) != (
        "SAT",
        True,
    ):
        return False, "invalid_z3_witness_receipt"
    return True, "ok"


def _has_any_witness_key(item: Mapping[str, Any]) -> bool:
    """Return True if item has at least one non-empty witness field."""
    return any(_is_nonempty_str(item.get(k)) for k in _WITNESS_KEYS)


def _verify_span_witnesses(
    item: Mapping[str, Any],
    span_info: Optional[Tuple[Path, List[str], int, int]],
) -> Tuple[bool, str]:
    """Verify optional sha256_anchor and witness_symbol against extracted file slice."""
    sha_val = item.get("sha256_anchor")
    if sha_val is not None:
        if span_info is None:
            return False, "evidence_sha256_anchor_mismatch"
        ok_sha, reason = _verify_slice_sha256(span_info[1], str(sha_val))
        if not ok_sha:
            return False, reason
    sym_val = item.get("witness_symbol")
    if sym_val is not None:
        if span_info is None:
            return False, "evidence_witness_symbol_missing"
        return _verify_ast_symbol_span(
            span_info[0], span_info[1], span_info[2], span_info[3], str(sym_val)
        )
    return True, "ok"


def _verify_evidence_and_span_witnesses(
    item: Mapping[str, Any],
    repo_root: Path,
) -> Tuple[bool, str]:
    """Verify evidence file span and optional sha256_anchor / witness_symbol."""
    span_info, span_reason = _extract_file_span_slice(
        str(item.get("evidence", "")), repo_root
    )
    if span_reason != "ok":
        return False, span_reason
    return _verify_span_witnesses(item, span_info)


def _verify_criterion_witnesses(
    item: Mapping[str, Any],
    repo_root: Optional[Path],
    require_witness: bool = False,
) -> Tuple[bool, str]:
    """Verify optional or required PCV witnesses (sha256_anchor, witness_symbol, z3_receipt)."""
    if require_witness and not _has_any_witness_key(item):
        return False, "missing_criterion_witness"
    if repo_root is None:
        return True, "ok"
    ok_span, span_reason = _verify_evidence_and_span_witnesses(item, repo_root)
    if not ok_span:
        return False, span_reason
    z3_val = item.get("z3_receipt")
    return (
        _verify_z3_receipt_ref(str(z3_val), repo_root)
        if z3_val is not None
        else (True, "ok")
    )


def _is_valid_criterion_score(score: Any) -> bool:
    """Return True if score is a strict int in 0..3."""
    return _is_strict_int(score) and 0 <= int(score) <= 3


def _validate_single_criterion(
    item: Any,
    repo_root: Optional[Path],
    require_witness: bool = False,
) -> Tuple[Optional[int], str]:
    """Validate one criterion dict and return (score, reason)."""
    if not isinstance(item, Mapping):
        return None, "criterion_not_an_object"
    if not _is_nonempty_str(item.get("id")):
        return None, "missing_criterion_id"
    if not _is_nonempty_str(item.get("evidence")):
        return None, "missing_criterion_evidence"
    score = item.get("score")
    if not _is_valid_criterion_score(score):
        return None, "invalid_criterion_score"
    ok_wit, wit_reason = _verify_criterion_witnesses(
        item, repo_root, require_witness
    )
    if not ok_wit:
        return None, wit_reason
    return int(score), "ok"


def _validate_criteria_list(
    criteria: Any,
    min_criteria: int,
    repo_root: Optional[Path],
    require_witness: bool = False,
) -> Tuple[Optional[List[int]], str]:
    """Validate the criteria list and return extracted integer scores."""
    if not isinstance(criteria, list) or len(criteria) < min_criteria:
        return None, "insufficient_criteria_count"
    scores: List[int] = []
    seen_ids = set()
    for item in criteria:
        score, reason = _validate_single_criterion(
            item, repo_root, require_witness=require_witness
        )
        if score is None:
            return None, reason
        cid = str(item.get("id")).strip()
        if cid in seen_ids:
            return None, "duplicate_criterion_id"
        seen_ids.add(cid)
        scores.append(score)
    return scores, "ok"


def compute_rubric_metrics(scores: Sequence[int]) -> Dict[str, Any]:
    """Compute min_score, total_score, threshold, and Cobb-Douglas utility."""
    count = len(scores)
    actual_min = min(scores) if count > 0 else 0
    actual_total = sum(scores)
    default_threshold = int(math.ceil(0.75 * 3.0 * count))
    if count > 0 and actual_min >= 2:
        product = 1.0
        for val in scores:
            product *= (float(val) / 3.0) ** (1.0 / float(count))
        cobb_douglas = round(product, 4)
    else:
        cobb_douglas = 0.0
    return {
        "min_score": actual_min,
        "total_score": actual_total,
        "threshold": default_threshold,
        "cobb_douglas": cobb_douglas,
    }


def _matches_exact_int(declared: Any, expected: int) -> bool:
    """Return True if declared is None or equals expected as a strict int."""
    if declared is None:
        return True
    return _is_strict_int(declared) and int(declared) == expected


def _check_declared_arithmetic(
    payload: Mapping[str, Any],
    metrics: Mapping[str, Any],
) -> Optional[str]:
    """Verify declared min_score, total_score, and threshold match math."""
    if not _matches_exact_int(payload.get("min_score"), metrics["min_score"]):
        return "spoofed_rubric_arithmetic"
    if not _matches_exact_int(
        payload.get("total_score"), metrics["total_score"]
    ):
        return "spoofed_rubric_arithmetic"
    decl_thr = payload.get("threshold")
    if decl_thr is not None:
        if not _is_strict_int(decl_thr) or decl_thr < metrics["threshold"]:
            return "spoofed_rubric_arithmetic"
    return None


def _check_verdict_consistency(
    verdict: str,
    metrics: Mapping[str, Any],
    effective_threshold: int,
) -> Optional[str]:
    """Enforce symmetric non-compensatory verdict lock."""
    if verdict in APPROVAL_VERDICTS:
        if metrics["min_score"] < 2:
            return "min_score_veto"
        if metrics["total_score"] < effective_threshold:
            return "rubric_threshold_not_met"
        if metrics["cobb_douglas"] < 0.75:
            return "cobb_douglas_below_threshold"
    elif verdict in REJECTION_VERDICTS:
        if (
            metrics["min_score"] >= 2
            and metrics["total_score"] >= effective_threshold
        ):
            return "contradictory_reject_on_passing_rubric"
    return None


def _check_header_fields(
    payload: Mapping[str, Any],
) -> Tuple[Optional[str], str]:
    """Validate stage, role, and verdict fields on a rubric payload."""
    stage = payload.get("stage")
    if not _is_strict_int(stage) or int(stage) < 0 or int(stage) > 5:
        return None, "invalid_stage"
    if not _is_nonempty_str(payload.get("role")):
        return None, "missing_role"
    verdict = str(payload.get("verdict", "")).strip().upper()
    if verdict not in VALID_VERDICTS:
        return None, "invalid_verdict"
    return verdict, "ok"


def evaluate_rubric_payload(
    payload: Mapping[str, Any],
    repo_root: Optional[Path] = None,
    raw_json_str: Optional[str] = None,
    require_witness: bool = False,
) -> Dict[str, Any]:
    """Validate a parsed rubric payload and return a structured decision."""
    if raw_json_str is not None:
        ok_lex, lex_reason = check_lexical_evidence_precedence(raw_json_str)
        if not ok_lex:
            return {"status": "INVALID", "reason": lex_reason}

    verdict, hdr_reason = _check_header_fields(payload)
    if verdict is None:
        return {"status": "INVALID", "reason": hdr_reason}

    min_crit = 1 if int(payload["stage"]) == 0 else 3
    scores, crit_reason = _validate_criteria_list(
        payload.get("criteria"),
        min_crit,
        repo_root,
        require_witness=require_witness,
    )
    if scores is None:
        return {"status": "INVALID", "reason": crit_reason}

    metrics = compute_rubric_metrics(scores)
    arith_err = _check_declared_arithmetic(payload, metrics)
    if arith_err is not None:
        return {"status": "INVALID", "reason": arith_err, **metrics}

    eff_thr = int(payload.get("threshold", metrics["threshold"]))
    verdict_err = _check_verdict_consistency(verdict, metrics, eff_thr)
    if verdict_err is not None:
        return {"status": "INVALID", "reason": verdict_err, **metrics}

    digest = hashlib.sha256(
        json.dumps(
            {"verdict": verdict, "scores": scores, **metrics}, sort_keys=True
        ).encode("utf-8")
    ).hexdigest()
    return {
        "status": "VALID",
        "reason": "ok",
        "stage": int(payload["stage"]),
        "role": str(payload["role"]).strip(),
        "verdict": verdict,
        "certificate_sha256": digest,
        **metrics,
    }


def _evaluate_single_rubric_json(
    raw_json: str,
    repo_root: Optional[Path] = None,
    require_witness: bool = False,
) -> Dict[str, Any]:
    """Parse and validate a single rubric JSON string."""
    try:
        parsed = json.loads(raw_json)
    except ValueError:
        return {"status": "INVALID", "reason": "malformed_rubric_json"}
    if not isinstance(parsed, Mapping):
        return {"status": "INVALID", "reason": "rubric_root_not_an_object"}
    return evaluate_rubric_payload(
        parsed,
        repo_root=repo_root,
        raw_json_str=raw_json,
        require_witness=require_witness,
    )


def _aggregate_panel_verdict(
    results: Sequence[Mapping[str, Any]],
) -> str:
    """Return non-compensatory panel verdict (HALT > REJECT > PROCEED_FIX > last)."""
    verdicts = {str(r.get("verdict", "")).upper() for r in results}
    for priority in ("HALT", "REJECT", "PROCEED_FIX"):
        if priority in verdicts:
            return priority
    return str(results[-1]["verdict"])


def _has_duplicate_panel_role(
    results: Sequence[Mapping[str, Any]],
) -> bool:
    """Return True if a multi-block panel repeats a (stage, role) pair."""
    seen = set()
    for r in results:
        key = (
            int(r.get("stage", -1)),
            str(r.get("role", "")).strip().lower(),
        )
        if key in seen:
            return True
        seen.add(key)
    return False


def _check_panel_roles_and_prose(
    results: Sequence[Mapping[str, Any]],
    raw_text: str,
) -> Optional[str]:
    """Verify distinct panel roles and trailing prose verdict consistency."""
    if len(results) > 1 and _has_duplicate_panel_role(results):
        return "duplicate_panel_role"
    prose_tags = _PROSE_VERDICT_RE.findall(raw_text)
    if prose_tags:
        panel_verdict = _aggregate_panel_verdict(results)
        if prose_tags[-1].strip().upper() != panel_verdict:
            return "prose_verdict_contradicts_rubric"
    return None


def _compute_conformal_panel_stats(
    results: Sequence[Mapping[str, Any]],
) -> Dict[str, float]:
    """Compute panel mean, standard deviation, and 90% Conformal Lower Confidence Bound."""
    scores = [float(r["cobb_douglas"]) for r in results]
    n = float(len(scores))
    mean_val = sum(scores) / n
    variance = sum((s - mean_val) ** 2 for s in scores) / n
    std_val = math.sqrt(variance)
    lcb = max(0.0, mean_val - 1.28155 * std_val * math.sqrt((n + 1.0) / n))
    return {
        "panel_mean": round(mean_val, 4),
        "panel_std": round(std_val, 4),
        "conformal_lcb": round(lcb, 4),
    }


def _combine_valid_rubric_results(
    results: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Combine one or more valid rubric block decisions into a panel result."""
    if len(results) == 1:
        out = dict(results[0])
        out["block_count"] = 1
        return out
    certs = [str(r["certificate_sha256"]) for r in results]
    panel_cert = hashlib.sha256("|".join(certs).encode("utf-8")).hexdigest()
    return {
        "status": "VALID",
        "reason": "ok",
        "verdict": _aggregate_panel_verdict(results),
        "block_count": len(results),
        "certificate_sha256": panel_cert,
        "min_score": min(int(r["min_score"]) for r in results),
        "total_score": sum(int(r["total_score"]) for r in results),
        "threshold": sum(int(r["threshold"]) for r in results),
        "cobb_douglas": min(float(r["cobb_douglas"]) for r in results),
        **_compute_conformal_panel_stats(results),
    }


def evaluate_rubric_text(
    raw_text: str,
    repo_root: Optional[Path] = None,
    require_witness: bool = False,
) -> Dict[str, Any]:
    """Extract and validate all <RUBRIC_SCORE> blocks or a raw JSON string."""
    blocks = extract_all_rubric_json_strs(raw_text)
    if not blocks:
        return {"status": "INVALID", "reason": "missing_rubric_score_block"}
    valid_results: List[Dict[str, Any]] = []
    for idx, raw_json in enumerate(blocks):
        res = _evaluate_single_rubric_json(
            raw_json, repo_root=repo_root, require_witness=require_witness
        )
        if res.get("status") != "VALID":
            res["failed_block_index"] = idx
            return res
        valid_results.append(res)
    panel_err = _check_panel_roles_and_prose(valid_results, raw_text)
    if panel_err is not None:
        return {"status": "INVALID", "reason": panel_err}
    return _combine_valid_rubric_results(valid_results)


def derive_stage0_tier(
    files_touched: int,
    crosses_module_boundary: bool,
    touches_execution_or_global_state: bool,
    modifies_security_or_deps: bool,
    architectural_ambiguity: bool,
) -> str:
    """Deterministically route a task to TIER_0, TIER_1, or TIER_2."""
    if (
        touches_execution_or_global_state
        or modifies_security_or_deps
        or architectural_ambiguity
    ):
        return "TIER_2"
    if files_touched > 1 or crosses_module_boundary:
        return "TIER_1"
    return "TIER_0"


def _has_anti_loophole_path(target_paths: Sequence[str]) -> bool:
    """Return True if any path in target_paths touches an Anti-Loophole surface."""
    return any(
        isinstance(p, str) and bool(ANTI_LOOPHOLE_PATH_RE.search(p.strip()))
        for p in target_paths
    )


def _is_valid_unit_float(val: Any) -> bool:
    """Return True if val is a numeric float/int in [0.0, 1.0] and not a bool."""
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        return False
    return 0.0 <= float(val) <= 1.0


def _validate_jev_inputs(
    probs: Mapping[str, float],
    probability_threshold: float,
    jev_noul_bits: float,
    noul_tier2_threshold: float,
) -> None:
    """Validate calibrated probability bounds and Noul entropy thresholds."""
    if (
        not _is_valid_unit_float(probability_threshold)
        or float(probability_threshold) <= 0.0
    ):
        raise ValueError("probability_threshold must be in (0.0, 1.0]")
    if float(jev_noul_bits) < 0.0 or float(noul_tier2_threshold) <= 0.0:
        raise ValueError("jev_noul_bits must be >= 0.0 and noul_tier2_threshold > 0.0")
    if not all(_is_valid_unit_float(v) for v in probs.values()):
        raise ValueError("jev_probabilities values must be in [0.0, 1.0]")


def classify_stage0_prompt_features(
    *,
    target_paths: Sequence[str] = (),
    touches_execution_or_global_state: bool = False,
    jev_probabilities: Optional[Mapping[str, float]] = None,
    probability_threshold: float = 0.5,
    jev_noul_bits: float = 0.0,
    noul_tier2_threshold: float = 1.0,
) -> str:
    """Route Stage 0 prompt features with calibrated Jev probabilities and Anti-Loophole floor."""
    probs: Mapping[str, float] = jev_probabilities or {}
    _validate_jev_inputs(
        probs, probability_threshold, jev_noul_bits, noul_tier2_threshold
    )
    effective_touches = bool(
        touches_execution_or_global_state or _has_anti_loophole_path(target_paths)
    )
    thr = float(probability_threshold)
    crosses = float(probs.get("crosses_module_boundary", 0.0)) >= thr
    sec_deps = float(probs.get("modifies_security_or_deps", 0.0)) >= thr
    ambig = (
        float(probs.get("architectural_ambiguity", 0.0)) >= thr
        or float(jev_noul_bits) >= float(noul_tier2_threshold)
    )
    return derive_stage0_tier(
        files_touched=len(target_paths),
        crosses_module_boundary=crosses,
        touches_execution_or_global_state=effective_touches,
        modifies_security_or_deps=sec_deps,
        architectural_ambiguity=ambig,
    )


def _claim_rank_tuple(res: Mapping[str, Any]) -> Tuple[int, int]:
    """Return (is_valid_flag, total_score) for comparative claim ranking."""
    is_valid = (
        1
        if res.get("status") == "VALID" and res.get("min_score", 0) >= 2
        else 0
    )
    return is_valid, int(res.get("total_score", 0))


def evaluate_comparative_claims(
    claim_a: Mapping[str, Any],
    claim_b: Mapping[str, Any],
    repo_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Compare two Stage 2 debate claims deterministically without bias."""
    res_a = evaluate_rubric_payload(claim_a, repo_root=repo_root)
    res_b = evaluate_rubric_payload(claim_b, repo_root=repo_root)
    rank_a = _claim_rank_tuple(res_a)
    rank_b = _claim_rank_tuple(res_b)
    if rank_a[0] == 0 and rank_b[0] == 0:
        winner = "NONE"
    elif rank_a >= rank_b:
        winner = "Claim_A"
    else:
        winner = "Claim_B"
    return {"winner": winner, "claim_a": res_a, "claim_b": res_b}


def _run_negative_self_tests(repo_root: Path) -> Optional[str]:
    """Execute negative self-test cases and return error string on failure."""
    bad_lex = (
        '<RUBRIC_SCORE>{"stage": 3, "role": "Reviewer", '
        '"verdict": "APPROVE", "criteria": ['
        '{"id": "c1", "score": 3, "evidence": "src/engine.py:1-2"},'
        '{"id": "c2", "evidence": "src/engine.py:1-2", "score": 3},'
        '{"id": "c3", "evidence": "src/engine.py:1-2", "score": 3}'
        "]}</RUBRIC_SCORE>"
    )
    res_lex = evaluate_rubric_text(bad_lex, repo_root=repo_root)
    if res_lex.get("reason") != "score_precedes_evidence":
        return f"Expected score_precedes_evidence, got {res_lex}"

    bad_veto = {
        "stage": 3,
        "role": "Reviewer",
        "verdict": "APPROVE",
        "criteria": [
            {"id": "c1", "evidence": "src/engine.py:1-2", "score": 1},
            {"id": "c2", "evidence": "src/engine.py:1-2", "score": 3},
            {"id": "c3", "evidence": "src/engine.py:1-2", "score": 3},
        ],
    }
    res_veto = evaluate_rubric_payload(bad_veto, repo_root=repo_root)
    if res_veto.get("reason") != "min_score_veto":
        return f"Expected min_score_veto, got {res_veto}"

    bad_path = {
        "stage": 4,
        "role": "Auditor",
        "verdict": "APPROVE",
        "criteria": [
            {"id": "c1", "evidence": "src/missing.py:1-2", "score": 3},
            {"id": "c2", "evidence": "src/engine.py:1-2", "score": 3},
            {"id": "c3", "evidence": "src/engine.py:1-2", "score": 3},
        ],
    }
    res_path = evaluate_rubric_payload(bad_path, repo_root=repo_root)
    if res_path.get("reason") != "evidence_path_outside_repo_or_missing":
        return f"Expected missing path error, got {res_path}"
    wit_err = _run_witness_self_tests(repo_root)
    if wit_err is not None:
        return wit_err
    return _run_jev_stage0_self_tests()


def _run_witness_self_tests(repo_root: Path) -> Optional[str]:
    """Verify positive and negative PCV witness cases (sha256, AST symbol, z3_receipt)."""
    z3_ok = repo_root / "scratch" / "stage0_ok.json"
    z3_ok.parent.mkdir(parents=True, exist_ok=True)
    z3_ok.write_text(
        json.dumps({"status": "SAT", "engine": "stdlib-finite-domain"}),
        encoding="utf-8",
    )
    sha_f = hashlib.sha256(
        b"def f(x: int) -> int:\n    return x + 1"
    ).hexdigest()[:12]
    wit_ok = {
        "stage": 3,
        "role": "Reviewer",
        "verdict": "APPROVE",
        "criteria": [
            {
                "id": "c1",
                "evidence": "src/engine.py:1-2",
                "sha256_anchor": sha_f,
                "witness_symbol": "f",
                "score": 3,
            },
            {
                "id": "c2",
                "evidence": "src/engine.py:3-4",
                "witness_symbol": "g",
                "score": 3,
            },
            {
                "id": "c3",
                "evidence": "src/engine.py:1-2",
                "z3_receipt": "scratch/stage0_ok.json",
                "score": 3,
            },
        ],
    }
    if (
        evaluate_rubric_payload(
            wit_ok, repo_root=repo_root, require_witness=True
        ).get("status")
        != "VALID"
    ):
        return "Expected wit_ok to pass with require_witness=True"
    return _run_negative_witness_checks(repo_root, wit_ok)


def _run_negative_witness_checks(
    repo_root: Path,
    base_payload: Mapping[str, Any],
) -> Optional[str]:
    """Verify negative failure reasons for PCV witnesses."""
    c_list = list(base_payload["criteria"])
    bad_sym = dict(
        base_payload,
        criteria=[
            {"id": "c1", "evidence": "src/engine.py:1-2", "witness_symbol": "g", "score": 3},
            c_list[1],
            c_list[2],
        ],
    )
    if (
        evaluate_rubric_payload(bad_sym, repo_root=repo_root).get("reason")
        != "evidence_witness_symbol_missing"
    ):
        return "Expected evidence_witness_symbol_missing"
    bad_sha = dict(
        base_payload,
        criteria=[
            {"id": "c1", "evidence": "src/engine.py:1-2", "sha256_anchor": "00000000", "score": 3},
            c_list[1],
            c_list[2],
        ],
    )
    if (
        evaluate_rubric_payload(bad_sha, repo_root=repo_root).get("reason")
        != "evidence_sha256_anchor_mismatch"
    ):
        return "Expected evidence_sha256_anchor_mismatch"
    no_wit = dict(
        base_payload,
        criteria=[
            {"id": "c1", "evidence": "src/engine.py:1-2", "score": 3},
            c_list[1],
            c_list[2],
        ],
    )
    if (
        evaluate_rubric_payload(
            no_wit, repo_root=repo_root, require_witness=True
        ).get("reason")
        != "missing_criterion_witness"
    ):
        return "Expected missing_criterion_witness"
    return None


def _run_jev_stage0_self_tests() -> Optional[str]:
    """Verify Anti-Loophole hard clamp and calibrated Jev Stage 0 routing."""
    if (
        classify_stage0_prompt_features(
            target_paths=["hooks/brc-guard.ps1"],
            jev_probabilities={"architectural_ambiguity": 0.0},
        )
        != "TIER_2"
    ):
        return "Expected Anti-Loophole path to clamp to TIER_2"
    if (
        classify_stage0_prompt_features(
            target_paths=["src/app.py"],
            jev_probabilities={"crosses_module_boundary": 0.8},
        )
        != "TIER_1"
    ):
        return "Expected crosses_module_boundary >= 0.5 to route to TIER_1"
    if (
        classify_stage0_prompt_features(
            target_paths=["src/app.py"],
            jev_noul_bits=1.2,
            noul_tier2_threshold=1.0,
        )
        != "TIER_2"
    ):
        return "Expected high Noul entropy to escalate to TIER_2"
    if (
        classify_stage0_prompt_features(
            target_paths=["src/app.py"],
            jev_probabilities={"crosses_module_boundary": 0.1},
        )
        != "TIER_0"
    ):
        return "Expected low-probability single file to route to TIER_0"
    return None


def run_self_test() -> Tuple[int, List[str]]:
    """Run built-in deterministic unit tests for rubric_grade_gate."""
    with tempfile.TemporaryDirectory() as tmp_dir_str:
        repo_root = Path(tmp_dir_str)
        engine_py = repo_root / "src" / "engine.py"
        engine_py.parent.mkdir(parents=True, exist_ok=True)
        engine_py.write_bytes(
            b"def f(x: int) -> int:\n    return x + 1\n"
            b"def g(y: int) -> int:\n    return y * 2\n"
        )
        neg_err = _run_negative_self_tests(repo_root)
        if neg_err is not None:
            return 1, [neg_err]

        good_txt = (
            '<RUBRIC_SCORE>{"stage": 3, "role": "System Architect", '
            '"verdict": "APPROVE", "criteria": ['
            '{"id": "c1", "evidence": "src/engine.py:1-2", "score": 3},'
            '{"id": "c2", "evidence": "src/engine.py:3-4", "score": 2},'
            '{"id": "c3", "evidence": "https://arxiv.org/abs/2403.18771", '
            '"score": 3}], "min_score": 2, "total_score": 8, '
            '"threshold": 7}</RUBRIC_SCORE>'
        )
        res_ok = evaluate_rubric_text(good_txt, repo_root=repo_root)
        if res_ok.get("status") != "VALID":
            return 1, [f"Expected VALID, got {res_ok}"]
        good_txt_2 = good_txt.replace('"System Architect"', '"Idea Skeptic"')
        panel_ok = evaluate_rubric_text(
            good_txt + "\n" + good_txt_2, repo_root=repo_root
        )
        if (
            panel_ok.get("status"),
            panel_ok.get("block_count"),
            "conformal_lcb" in panel_ok,
        ) != ("VALID", 2, True):
            return 1, [f"Expected 2-block VALID panel, got {panel_ok}"]
        if panel_ok["conformal_lcb"] > panel_ok["panel_mean"]:
            return 1, [f"Expected conformal_lcb <= panel_mean, got {panel_ok}"]
        dup_res = evaluate_rubric_text(
            good_txt + "\n" + good_txt, repo_root=repo_root
        )
        if dup_res.get("reason") != "duplicate_panel_role":
            return 1, [f"Expected duplicate_panel_role, got {dup_res}"]
        if derive_stage0_tier(1, False, True, False, False) != "TIER_2":
            return 1, ["Anti-Loophole tier routing check failed"]

    return 0, ["SELF_TEST_OK: rubric_grade_gate verified Stages 0-5."]


def _build_arg_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser for rubric_grade_gate."""
    parser = argparse.ArgumentParser(
        description="Universal Rubric-Graded Qualitative Judgment Gate."
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run built-in deterministic self-tests and exit.",
    )
    parser.add_argument(
        "input_path",
        nargs="?",
        help="Path to markdown or JSON file containing <RUBRIC_SCORE>.",
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Optional repository root for verifying evidence file spans.",
    )
    parser.add_argument(
        "--require-witness",
        action="store_true",
        help="Require at least one proof-carrying witness per criterion.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point for rubric_grade_gate."""
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    if args.self_test:
        code, msgs = run_self_test()
        for msg in msgs:
            print(msg)
        return code
    if not args.input_path:
        parser.error("input_path is required unless --self-test is set.")
    target = Path(args.input_path)
    repo_root = Path(args.repo_root) if args.repo_root else None
    result = evaluate_rubric_text(
        target.read_text(encoding="utf-8", errors="replace"),
        repo_root=repo_root,
        require_witness=bool(args.require_witness),
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") == "VALID" else 1


if __name__ == "__main__":
    sys.exit(main())
