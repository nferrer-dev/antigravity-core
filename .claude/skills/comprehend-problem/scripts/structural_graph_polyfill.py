"""Local pure-Python structural dependency graph polyfill for Stage 0 comprehend-problem.

Builds a deterministic JSON AST dependency and symbol graph for Python files when
the code-graph-context MCP server is unavailable, and computes transitive impacted
test files per TDAD graph-based impact analysis (arXiv:2603.17973).

Usage:
    python structural_graph_polyfill.py <target_directory> [--out] <output_json_path>
    python structural_graph_polyfill.py <target_directory> --impacted-tests <changed_file...>
    python structural_graph_polyfill.py --self-test
"""
import argparse
import ast
import json
import os
import sys
import tempfile
from pathlib import Path

IGNORED_DIRS = {
    "__pycache__",
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "scratch",
    "chroma_db",
    "chroma_data",
    "fpcalc_dir",
    ".next",
    "coverage",
    ".claude",
}
_BRANCH_AST_TYPES = (
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


def compute_cyclomatic_complexity(func_node):
    """Return the McCabe cyclomatic complexity of an AST FunctionDef/AsyncFunctionDef."""
    complexity = 1
    for child in ast.walk(func_node):
        if isinstance(child, _BRANCH_AST_TYPES):
            complexity += 1
        elif isinstance(child, ast.BoolOp):
            complexity += max(0, len(child.values) - 1)
    return complexity


def _read_python_source(filepath):
    """Read Python file text as UTF-8 with UTF-16 fallback; return (text, error_tag)."""
    for enc in ("utf-8", "utf-16"):
        try:
            with open(filepath, "r", encoding=enc) as f:
                return f.read(), None
        except UnicodeDecodeError:
            continue
    return None, "UnicodeDecodeError"


def _empty_parse_error(error_name):
    """Return a default parse_file error record."""
    return {
        "imports": [],
        "classes": [],
        "functions": [],
        "calls": [],
        "function_complexities": {},
        "error": error_name,
    }


def _extract_call_name(call_node):
    """Return the called function/method name from an ast.Call node, or None."""
    if isinstance(call_node.func, ast.Name):
        return call_node.func.id
    if isinstance(call_node.func, ast.Attribute):
        return call_node.func.attr
    return None


def _record_ast_node(node, imports, classes, functions, calls, complexities):
    """Accumulate symbol and edge data from a single AST node."""
    if isinstance(node, ast.Import):
        for alias in node.names:
            imports.add(alias.name)
    elif isinstance(node, ast.ImportFrom) and node.module:
        imports.add(node.module)
    elif isinstance(node, ast.ClassDef):
        classes.append(node.name)
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        functions.append(node.name)
        complexities[node.name] = compute_cyclomatic_complexity(node)
    elif isinstance(node, ast.Call):
        callee = _extract_call_name(node)
        if callee:
            calls.add(callee)


def parse_file(filepath):
    """Parse a single Python file and return its imports, classes, functions, calls, and complexities."""
    content, err = _read_python_source(filepath)
    if err is not None:
        return _empty_parse_error(err)
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return _empty_parse_error("SyntaxError")

    imports = set()
    classes = []
    functions = []
    calls = set()
    function_complexities = {}

    for node in ast.walk(tree):
        _record_ast_node(node, imports, classes, functions, calls, function_complexities)

    return {
        "imports": sorted(imports),
        "classes": sorted(classes),
        "functions": sorted(functions),
        "calls": sorted(calls),
        "function_complexities": dict(sorted(function_complexities.items())),
    }


def _add_file_to_graph(rel_path, data, graph, symbol_to_files):
    """Add a parsed file node, its symbols, and its IMPORTS edges to graph."""
    for sym in list(data["functions"]) + list(data["classes"]):
        symbol_to_files.setdefault(sym, set()).add(rel_path)

    graph["nodes"].append(
        {
            "id": rel_path,
            "type": "file",
            "classes": data["classes"],
            "functions": data["functions"],
            "calls": data["calls"],
            "function_complexities": data["function_complexities"],
        }
    )
    for imp in data["imports"]:
        graph["edges"].append(
            {
                "source": rel_path,
                "target": imp,
                "relation": "imports",
                "type": "IMPORTS",
            }
        )


def _append_call_edges(graph, file_records, symbol_to_files):
    """Append cross-file CALLS edges to graph."""
    for rel_path, data in file_records:
        for called_sym in data["calls"]:
            targets = sorted(symbol_to_files.get(called_sym, ()))
            for target_file in targets:
                if target_file != rel_path:
                    graph["edges"].append(
                        {
                            "source": rel_path,
                            "target": target_file,
                            "relation": "calls",
                            "type": "CALLS",
                            "symbol": called_sym,
                        }
                    )


def build_graph(directory):
    """Build a deterministic structural dependency and call graph for a directory."""
    graph = {"nodes": [], "edges": []}
    file_records = []
    symbol_to_files = {}

    for root, dirnames, files in os.walk(directory):
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORED_DIRS)
        py_files = [f for f in sorted(files) if f.endswith(".py")]
        for file in py_files:
            filepath = os.path.join(root, file)
            rel_path = os.path.relpath(filepath, directory).replace("\\", "/")
            data = parse_file(filepath)
            if "error" not in data:
                file_records.append((rel_path, data))
                _add_file_to_graph(rel_path, data, graph, symbol_to_files)

    _append_call_edges(graph, file_records, symbol_to_files)
    return graph


def _is_test_file(rel_path):
    """Return True if the filename matches test_*.py or *_test.py."""
    name = Path(rel_path).name
    return name.startswith("test_") or name.endswith("_test.py")


def _is_test_path(rel_path):
    """Return True if rel_path is inside a tests directory or is a test file."""
    norm = str(rel_path).replace("\\", "/")
    return "tests" in Path(norm).parts or _is_test_file(norm)


def _build_reverse_importers(graph, node_ids):
    """Map each node ID to the set of node IDs that import or call it."""
    mod_to_nodes = {}
    for nid in node_ids:
        p = Path(nid)
        dotted = ".".join(p.with_suffix("").parts)
        for m in (nid, p.stem, dotted):
            mod_to_nodes.setdefault(m, set()).add(nid)

    reverse_importers = {nid: set() for nid in node_ids}
    for edge in graph["edges"]:
        src = edge["source"]
        target_mod = edge["target"]
        for candidate_mod in (target_mod, target_mod.split(".")[-1]):
            for target_nid in mod_to_nodes.get(candidate_mod, ()):
                reverse_importers.setdefault(target_nid, set()).add(src)
    return reverse_importers


def _matches_changed_target(nid, norm_ch, ch_stem):
    """Return True if node ID nid directly matches or tests changed file norm_ch."""
    if nid == norm_ch or nid.endswith("/" + norm_ch) or Path(nid).stem == ch_stem:
        return True
    return _is_test_file(nid) and Path(nid).stem in {"test_" + ch_stem, ch_stem + "_test"}


def _seed_changed_nodes(node_ids, changed_files):
    """Return initial queue and visited set for changed_files."""
    queue = []
    visited = set()
    for ch in changed_files:
        norm_ch = str(ch).replace("\\", "/")
        ch_stem = Path(norm_ch).stem
        for nid in node_ids:
            if nid not in visited and _matches_changed_target(nid, norm_ch, ch_stem):
                visited.add(nid)
                queue.append(nid)
    return queue, visited


def find_impacted_tests(directory_or_graph, changed_files):
    """Return sorted relative paths of test_*.py files transitively impacted by changed_files."""
    graph = (
        directory_or_graph
        if isinstance(directory_or_graph, dict)
        else build_graph(directory_or_graph)
    )
    node_ids = [n["id"] for n in graph["nodes"]]
    reverse_importers = _build_reverse_importers(graph, node_ids)
    queue, visited = _seed_changed_nodes(node_ids, changed_files)

    idx = 0
    while idx < len(queue):
        curr = queue[idx]
        idx += 1
        for importer in sorted(reverse_importers.get(curr, ())):
            if importer not in visited:
                visited.add(importer)
                queue.append(importer)

    return sorted(nid for nid in visited if _is_test_file(nid))


def _format_positional_args(args_obj):
    """Format positional-only and standard positional arguments with defaults."""
    parts = [a.arg + "/" for a in getattr(args_obj, "posonlyargs", ())]
    default_start = len(args_obj.args) - len(args_obj.defaults)
    for i, a in enumerate(args_obj.args):
        if i >= default_start:
            def_node = args_obj.defaults[i - default_start]
            parts.append("%s=%s" % (a.arg, ast.dump(def_node)))
        else:
            parts.append(a.arg)
    return parts


def _format_keyword_args(args_obj):
    """Format vararg, kwonlyargs, and kwarg sections of a signature."""
    parts = []
    if args_obj.vararg:
        parts.append("*" + args_obj.vararg.arg)
    for a, kw_def in zip(args_obj.kwonlyargs, args_obj.kw_defaults):
        if kw_def is not None:
            parts.append("%s=%s" % (a.arg, ast.dump(kw_def)))
        else:
            parts.append(a.arg)
    if args_obj.kwarg:
        parts.append("**" + args_obj.kwarg.arg)
    return parts


def _format_signature(fn_node):
    """Return a deterministic string representation of a function/method signature."""
    args_obj = fn_node.args
    parts = _format_positional_args(args_obj) + _format_keyword_args(args_obj)
    prefix = "async def" if isinstance(fn_node, ast.AsyncFunctionDef) else "def"
    return "%s(%s)" % (prefix, ", ".join(parts))


def _record_class_surface(cls_node, symbols):
    """Record a class definition and its method signatures into symbols."""
    symbols[cls_node.name] = "class(%d bases)" % len(cls_node.bases)
    for item in cls_node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols["%s.%s" % (cls_node.name, item.name)] = _format_signature(item)


def _extract_surface(source_text):
    """Extract top-level symbols, class methods, signatures, and imports from Python source."""
    tree = ast.parse(source_text)
    symbols = {}
    imports = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols[node.name] = _format_signature(node)
        elif isinstance(node, ast.ClassDef):
            _record_class_surface(node, symbols)
    return symbols, imports


def compute_ast_surface_diff(old_source, new_source):
    """Compute deterministic AST symbol, signature, and import differences (PatchDiff, arXiv:2503.15223)."""
    old_syms, old_imps = _extract_surface(old_source)
    new_syms, new_imps = _extract_surface(new_source)
    old_keys = set(old_syms.keys())
    new_keys = set(new_syms.keys())
    sig_changes = [
        {"symbol": sym, "old": old_syms[sym], "new": new_syms[sym]}
        for sym in sorted(old_keys & new_keys)
        if old_syms[sym] != new_syms[sym]
    ]
    return {
        "added_symbols": sorted(new_keys - old_keys),
        "removed_symbols": sorted(old_keys - new_keys),
        "signature_changes": sig_changes,
        "import_changes": {
            "added": sorted(new_imps - old_imps),
            "removed": sorted(old_imps - new_imps),
        },
    }


def find_high_complexity_functions(directory_or_graph, threshold=10):
    """Return a sorted list of functions whose McCabe cyclomatic complexity >= threshold."""
    graph = (
        directory_or_graph
        if isinstance(directory_or_graph, dict)
        else build_graph(directory_or_graph)
    )
    results = []
    for node in graph.get("nodes", []):
        for fn_name, comp in sorted(node.get("function_complexities", {}).items()):
            if comp >= threshold:
                results.append(
                    {"file": node["id"], "function": fn_name, "complexity": comp}
                )
    return results


def _write_self_test_fixture(tmp_dir):
    """Create sample Python files for run_self_test."""
    sample_py = tmp_dir / "sample.py"
    sample_py.write_text(
        "import json\nfrom pathlib import Path\n\n"
        "class Widget:\n    pass\n\n"
        "def sync_fn(x=1):\n    if x > 0 and x < 10:\n        return 1\n    return 0\n\n"
        "async def async_fn():\n    return 2\n",
        encoding="utf-8",
        newline="\n",
    )
    test_py = tmp_dir / "test_widget.py"
    test_py.write_text(
        "import sample\n\ndef test_sync():\n    assert sample.sync_fn() == 1\n",
        encoding="utf-8",
        newline="\n",
    )


def _is_expected_call_edge(edge):
    """Return True if edge is the expected test_widget.py -> sample.py CALLS edge."""
    return (
        edge.get("type") == "CALLS"
        and edge.get("source") == "test_widget.py"
        and edge.get("target") == "sample.py"
    )


def _verify_loaded_graph(loaded):
    """Validate nodes, classes, functions, complexities, and CALLS edges in loaded graph."""
    nodes = {n["id"]: n for n in loaded.get("nodes", [])}
    sample = nodes.get("sample.py")
    if sample is None or sample["classes"] != ["Widget"]:
        print("SELF-TEST FAIL: missing sample.py or Widget class", file=sys.stderr)
        return False
    if sample["functions"] != ["async_fn", "sync_fn"]:
        print("SELF-TEST FAIL: unexpected sample.py functions", file=sys.stderr)
        return False
    if sample["function_complexities"].get("sync_fn") != 3:
        print("SELF-TEST FAIL: unexpected sync_fn complexity", file=sys.stderr)
        return False
    if not any(_is_expected_call_edge(e) for e in loaded.get("edges", [])):
        print("SELF-TEST FAIL: missing CALLS edge", file=sys.stderr)
        return False
    return True


def _verify_diff_and_cli_helpers(tmp_dir, loaded):
    """Verify high-complexity finder, impacted tests, AST surface diff, and --out CLI flag."""
    if not find_high_complexity_functions(loaded, threshold=3):
        print("SELF-TEST FAIL: find_high_complexity_functions empty", file=sys.stderr)
        return False
    if find_impacted_tests(str(tmp_dir), ["sample.py"]) != ["test_widget.py"]:
        print("SELF-TEST FAIL: unexpected find_impacted_tests output", file=sys.stderr)
        return False
    surf_diff = compute_ast_surface_diff(
        "import os\ndef f(a):\n    return a\n",
        "import os\nimport sys\ndef f(a, b=1):\n    return a + b\ndef g():\n    return 0\n",
    )
    if surf_diff["added_symbols"] != ["g"] or not surf_diff["signature_changes"]:
        print("SELF-TEST FAIL: compute_ast_surface_diff failed", file=sys.stderr)
        return False
    out_flag_target = tmp_dir / "scratch" / "stage0_graph.json"
    if main([str(tmp_dir), "--out", str(out_flag_target)]) != 0 or not out_flag_target.is_file():
        print("SELF-TEST FAIL: --out flag failed", file=sys.stderr)
        return False
    return True


def run_self_test():
    """Verify AST parsing, deterministic graph generation, CALLS edges, complexity, impacted-test selection, AST diff, and LF output."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        _write_self_test_fixture(tmp_dir)
        out_json = tmp_dir / "graph.json"
        graph = build_graph(str(tmp_dir))
        out_json.write_text(
            json.dumps(graph, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        raw = out_json.read_bytes()
        if b"\r" in raw:
            print("SELF-TEST FAIL: CRLF detected in output JSON", file=sys.stderr)
            return 1
        loaded = json.loads(raw.decode("utf-8"))
        if not _verify_loaded_graph(loaded):
            return 1
        if not _verify_diff_and_cli_helpers(tmp_dir, loaded):
            return 1
    print("structural_graph_polyfill.py self-test: PASS")
    return 0


def _build_arg_parser():
    """Create the CLI argument parser for structural_graph_polyfill."""
    parser = argparse.ArgumentParser(
        description="Build a deterministic AST dependency graph JSON for a directory."
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run built-in deterministic self-test and exit.",
    )
    parser.add_argument(
        "--out",
        dest="out_flag",
        help="Destination path for the output JSON graph (Stage 0 receipt).",
    )
    parser.add_argument(
        "--impacted-tests",
        nargs="+",
        dest="impacted_tests",
        help="Return transitive test_*.py files impacted by the given changed files.",
    )
    parser.add_argument(
        "--high-complexity",
        nargs="?",
        const=10,
        type=int,
        dest="high_complexity",
        help="Return functions whose McCabe cyclomatic complexity >= threshold (default 10).",
    )
    parser.add_argument(
        "--ast-diff",
        nargs=2,
        metavar=("OLD_FILE", "NEW_FILE"),
        dest="ast_diff",
        help="Compute deterministic AST symbol, signature, and import diff between two Python files.",
    )
    parser.add_argument(
        "target_directory",
        nargs="?",
        help="Target directory to scan for Python files.",
    )
    parser.add_argument(
        "output_json_path",
        nargs="?",
        help="Destination path for the output JSON graph.",
    )
    return parser


def _write_json_output(payload, dest_str):
    """Write payload as LF-normalized JSON to dest_str."""
    output_path = Path(dest_str)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return output_path


def _run_high_complexity_cli(target_dir, threshold, dest_str):
    """Execute --high-complexity scan, optionally writing enriched graph JSON."""
    if dest_str:
        graph = build_graph(target_dir)
        high = find_high_complexity_functions(graph, threshold=threshold)
        non_test_high = [
            item for item in high if not _is_test_path(item.get("file", ""))
        ]
        graph["high_complexity_functions"] = high
        graph["contract_gaps"] = len(non_test_high)
        _write_json_output(graph, dest_str)
    else:
        high = find_high_complexity_functions(target_dir, threshold=threshold)
    print(json.dumps({"high_complexity_functions": high}, indent=2))
    return 0


def _dispatch_analysis_flag(args, dest_str):
    """Handle --ast-diff, --high-complexity, or --impacted-tests; return exit code or None."""
    if args.ast_diff:
        old_p, new_p = Path(args.ast_diff[0]), Path(args.ast_diff[1])
        diff = compute_ast_surface_diff(
            old_p.read_text(encoding="utf-8"), new_p.read_text(encoding="utf-8")
        )
        print(json.dumps(diff, indent=2))
        return 0
    if args.high_complexity is not None:
        return _run_high_complexity_cli(
            args.target_directory or ".", args.high_complexity, dest_str
        )
    if args.impacted_tests:
        impacted = find_impacted_tests(
            args.target_directory or ".", args.impacted_tests
        )
        print(json.dumps({"impacted_tests": impacted}, indent=2))
        return 0
    return None


def main(argv=None):
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    if args.self_test:
        return run_self_test()
    dest_str = args.out_flag or args.output_json_path
    flag_rc = _dispatch_analysis_flag(args, dest_str)
    if flag_rc is not None:
        return flag_rc
    if not args.target_directory or not dest_str:
        parser.print_usage(sys.stderr)
        return 1

    graph = build_graph(args.target_directory)
    output_path = _write_json_output(graph, dest_str)
    print("Success! Graph written to %s" % output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
