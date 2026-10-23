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
)
APPROVAL_VERDICTS: Tuple[str, ...] = ("APPROVE", "PROCEED")

_RUBRIC_TAG_RE = re.compile(
    r"<RUBRIC_SCORE>\s*(?P<json>\{[\s\S]*?\})\s*</RUBRIC_SCORE>",
    re.IGNORECASE,
)
_CRITERION_OBJ_RE = re.compile(r"\{[^{}]*\}")
_FILE_SPAN_RE = re.compile(
    r"^(?P<path>[^:#\s]+)(?::|#L)(?P<start>\d+)(?:-(?:L)?(?P<end>\d+))?$"
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


def _resolve_evidence_span(
    evidence_str: str,
    repo_root: Path,
) -> Tuple[bool, str]:
    """Verify file existence and line range when evidence is a file span."""
    cleaned = evidence_str.strip()
    match = _FILE_SPAN_RE.match(cleaned)
    if cleaned.startswith(("https://", "http://")) or not match:
        return True, "ok"
    start_line = int(match.group("start"))
    end_grp = match.group("end")
    end_line = int(end_grp) if end_grp else start_line
    if start_line < 1 or end_line < start_line:
        return False, "invalid_evidence_line_range"

    target, path_reason = _resolve_repo_target(
        match.group("path").strip(), repo_root
    )
    if target is None:
        return False, path_reason
    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    if end_line > len(lines):
        return False, "evidence_line_range_out_of_bounds"
    return True, "ok"


def _validate_single_criterion(
    item: Any,
    repo_root: Optional[Path],
) -> Tuple[Optional[int], str]:
    """Validate one criterion dict and return (score, reason)."""
    if not isinstance(item, Mapping):
        return None, "criterion_not_an_object"
    if not _is_nonempty_str(item.get("id")):
        return None, "missing_criterion_id"
    evidence = item.get("evidence")
    if not _is_nonempty_str(evidence):
        return None, "missing_criterion_evidence"
    score = item.get("score")
    if not _is_strict_int(score) or int(score) < 0 or int(score) > 3:
        return None, "invalid_criterion_score"
    if repo_root is not None:
        ok_span, span_reason = _resolve_evidence_span(str(evidence), repo_root)
        if not ok_span:
            return None, span_reason
    return int(score), "ok"


def _validate_criteria_list(
    criteria: Any,
    min_criteria: int,
    repo_root: Optional[Path],
) -> Tuple[Optional[List[int]], str]:
    """Validate the criteria list and return extracted integer scores."""
    if not isinstance(criteria, list) or len(criteria) < min_criteria:
        return None, "insufficient_criteria_count"
    scores: List[int] = []
    seen_ids = set()
    for item in criteria:
        score, reason = _validate_single_criterion(item, repo_root)
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
    elif verdict == "REJECT":
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
        payload.get("criteria"), min_crit, repo_root
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
        "verdict": verdict,
        "certificate_sha256": digest,
        **metrics,
    }


def _evaluate_single_rubric_json(
    raw_json: str,
    repo_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Parse and validate a single rubric JSON string."""
    try:
        parsed = json.loads(raw_json)
    except ValueError:
        return {"status": "INVALID", "reason": "malformed_rubric_json"}
    if not isinstance(parsed, Mapping):
        return {"status": "INVALID", "reason": "rubric_root_not_an_object"}
    return evaluate_rubric_payload(
        parsed, repo_root=repo_root, raw_json_str=raw_json
    )


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
        "verdict": str(results[-1]["verdict"]),
        "block_count": len(results),
        "certificate_sha256": panel_cert,
        "min_score": min(int(r["min_score"]) for r in results),
        "total_score": sum(int(r["total_score"]) for r in results),
        "threshold": sum(int(r["threshold"]) for r in results),
        "cobb_douglas": min(float(r["cobb_douglas"]) for r in results),
    }


def evaluate_rubric_text(
    raw_text: str,
    repo_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """Extract and validate all <RUBRIC_SCORE> blocks or a raw JSON string."""
    blocks = extract_all_rubric_json_strs(raw_text)
    if not blocks:
        return {"status": "INVALID", "reason": "missing_rubric_score_block"}
    valid_results: List[Dict[str, Any]] = []
    for idx, raw_json in enumerate(blocks):
        res = _evaluate_single_rubric_json(raw_json, repo_root=repo_root)
        if res.get("status") != "VALID":
            res["failed_block_index"] = idx
            return res
        valid_results.append(res)
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
        panel_ok = evaluate_rubric_text(good_txt + "\n" + good_txt, repo_root=repo_root)
        if panel_ok.get("status") != "VALID" or panel_ok.get("block_count") != 2:
            return 1, [f"Expected 2-block VALID panel, got {panel_ok}"]
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
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("status") == "VALID" else 1


if __name__ == "__main__":
    sys.exit(main())
