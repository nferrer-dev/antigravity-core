"""Deterministic Diminishing-Returns & Full-System Coherence Bake Gate.

Evaluates cross-layer AST producer-consumer audits, formal Z3/SMT state
proofs, and candidate findings across four first-class dimensions:
1. COHERENCE_CONTRACT (cross-layer producer-consumer seams & schema fidelity)
2. SYSTEM_DESIGN (modularity, concurrency, bulkhead & complexity hotspots)
3. OPTIMIZATION (asymptotic complexity, query plans, vectorization & I/O)
4. SOTA_BENCHMARK (peer-reviewed literature & production OSS benchmarks)

Rejects speculative, sub-epsilon, or rubric-deficient findings and emits either
`AIRTIGHT_HALT` (when the point of diminishing returns is reached with an
exhaustive audit manifest) or `PROCEED_FIX`.

Usage:
    python coherence_bake_gate.py <ast> <z3> <findings> <out> --repo-root <d>
    python coherence_bake_gate.py --self-test
"""
import argparse
import hashlib
import json
import math
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

_FILE_LINE_RE = re.compile(r"^(?P<path>.+?):(?P<start>\d+)(?:-(?P<end>\d+))?$")
_MD_IMAGE_EXFIL_RE = re.compile(r"!\[[^\]]*\]\(\s*https?://", re.IGNORECASE)
_INVISIBLE_CHAR_RE = re.compile(
    r"[\u200b-\u200d\u202a-\u202e\u2060-\u2064\ufeff\U000e0000-\U000e007f]"
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


def _count_unconstrained_vars(z3_data: Mapping[str, Any]) -> int:
    """Return the count of unconstrained Z3 state variables."""
    unconstrained = z3_data.get("unconstrained_variables", [])
    if isinstance(unconstrained, (list, tuple)):
        return len(unconstrained)
    return 0 if unconstrained is None else 1


def _check_exhaustiveness_manifest(manifest: Any) -> str:
    """Validate optional exhaustiveness_manifest dict."""
    if manifest is None:
        return "ok"
    if not isinstance(manifest, Mapping):
        return "incomplete_exhaustiveness_manifest"
    bool_flags = (
        manifest.get("uncapped_discovery") is True
        and manifest.get("full_suite_executed") is True
        and manifest.get("closed_loop_reaudit") is True
    )
    zero_counts = (
        _non_negative_count(manifest.get("test_failures", 0)) == 0
        and _non_negative_count(manifest.get("invariant_violations", 0)) == 0
    )
    if bool_flags and zero_counts:
        return "ok"
    return "incomplete_exhaustiveness_manifest"


def _extract_findings_and_manifest(
    ast_data: Mapping[str, Any],
    findings_payload: Any,
) -> Tuple[List[Any], str]:
    """Extract candidate finding list and validate exhaustiveness_manifest."""
    manifest = ast_data.get("exhaustiveness_manifest")
    if isinstance(findings_payload, Mapping):
        if manifest is None:
            manifest = findings_payload.get("exhaustiveness_manifest")
        items = findings_payload.get(
            "findings",
            findings_payload.get("candidate_items", []),
        )
        raw_list = list(items) if isinstance(items, list) else []
        return raw_list, _check_exhaustiveness_manifest(manifest)
    if isinstance(findings_payload, list):
        return list(findings_payload), _check_exhaustiveness_manifest(manifest)
    return [], _check_exhaustiveness_manifest(manifest)


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


def evaluate_bake_inputs(
    ast_data: Mapping[str, Any],
    z3_data: Mapping[str, Any],
    findings_payload: Any,
    repo_root: Path,
) -> Dict[str, Any]:
    """Evaluate AST audit, Z3 proof, exhaustiveness manifest, and findings."""
    ast_contract_gaps = _non_negative_count(
        ast_data.get("contract_gaps", 0)
    ) + _non_negative_count(ast_data.get("unindexed_hot_paths", 0))
    z3_status = str(z3_data.get("status", "SAT")).strip().upper()
    z3_unconstrained_count = _count_unconstrained_vars(z3_data)

    raw_items, exhaustiveness_status = _extract_findings_and_manifest(
        ast_data, findings_payload
    )
    verified, rejected, by_category = _partition_findings(raw_items, repo_root)

    is_airtight = (
        len(verified) == 0
        and ast_contract_gaps == 0
        and z3_status == "SAT"
        and z3_unconstrained_count == 0
        and exhaustiveness_status == "ok"
    )
    status = "AIRTIGHT_HALT" if is_airtight else "PROCEED_FIX"

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
        "action_declare_airtight_halt": 1 if is_airtight else 0,
        "action_propose_invariant_fix": 0 if is_airtight else 1,
        "ast_contract_gaps": ast_contract_gaps,
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
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entry point for coherence_bake_gate."""
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    if args.self_test:
        code, msgs = run_self_test()
        for msg in msgs:
            print(msg)
        return code
    if not all(
        (args.ast_json, args.z3_json, args.findings_json, args.output_json)
    ):
        parser.error(
            "ast_json, z3_json, findings_json, and output_json are required "
            "unless --self-test is set."
        )
    return _execute_cli_gate(args)


if __name__ == "__main__":
    sys.exit(main())
