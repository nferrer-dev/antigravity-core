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


def compute_cyclomatic_complexity(func_node):
    """Return the McCabe cyclomatic complexity of an AST FunctionDef/AsyncFunctionDef."""
    complexity = 1
    for child in ast.walk(func_node):
        if isinstance(
            child,
            (
                ast.If,
                ast.For,
                ast.AsyncFor,
                ast.While,
                ast.ExceptHandler,
                ast.With,
                ast.AsyncWith,
                ast.IfExp,
                ast.comprehension,
            ),
        ):
            complexity += 1
        elif isinstance(child, ast.BoolOp):
            complexity += max(0, len(child.values) - 1)
    return complexity


def parse_file(filepath):
    """Parse a single Python file and return its imports, classes, functions, calls, and complexities."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except UnicodeDecodeError:
        try:
            with open(filepath, "r", encoding="utf-16") as f:
                content = f.read()
        except UnicodeDecodeError:
            return {
                "imports": [],
                "classes": [],
                "functions": [],
                "calls": [],
                "function_complexities": {},
                "error": "UnicodeDecodeError",
            }

    try:
        tree = ast.parse(content)
    except SyntaxError:
        return {
            "imports": [],
            "classes": [],
            "functions": [],
            "calls": [],
            "function_complexities": {},
            "error": "SyntaxError",
        }

    imports = set()
    classes = []
    functions = []
    calls = set()
    function_complexities = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.append(node.name)
            function_complexities[node.name] = compute_cyclomatic_complexity(node)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                calls.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                calls.add(node.func.attr)

    return {
        "imports": sorted(imports),
        "classes": sorted(classes),
        "functions": sorted(functions),
        "calls": sorted(calls),
        "function_complexities": dict(sorted(function_complexities.items())),
    }


def build_graph(directory):
    """Build a deterministic structural dependency and call graph for a directory."""
    graph = {"nodes": [], "edges": []}
    file_records = []
    symbol_to_files = {}

    for root, dirnames, files in os.walk(directory):
        dirnames[:] = sorted(d for d in dirnames if d not in {"__pycache__", ".git"})
        for file in sorted(files):
            if not file.endswith(".py"):
                continue
            filepath = os.path.join(root, file)
            rel_path = os.path.relpath(filepath, directory).replace("\\", "/")

            data = parse_file(filepath)
            if "error" in data:
                continue

            file_records.append((rel_path, data))
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

    for rel_path, data in file_records:
        for called_sym in data["calls"]:
            for target_file in sorted(symbol_to_files.get(called_sym, ())):
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

    return graph


def _is_test_file(rel_path):
    name = Path(rel_path).name
    return name.startswith("test_") or name.endswith("_test.py")


def find_impacted_tests(directory_or_graph, changed_files):
    """Return sorted relative paths of test_*.py files transitively impacted by changed_files."""
    graph = (
        directory_or_graph
        if isinstance(directory_or_graph, dict)
        else build_graph(directory_or_graph)
    )
    node_ids = [n["id"] for n in graph["nodes"]]

    # Map module identifiers (stem, relative path, and dotted path) to node relative paths
    mod_to_nodes = {}
    for nid in node_ids:
        p = Path(nid)
        stem = p.stem
        dotted = ".".join(p.with_suffix("").parts)
        for m in (nid, stem, dotted):
            mod_to_nodes.setdefault(m, set()).add(nid)

    reverse_importers = {nid: set() for nid in node_ids}
    for edge in graph["edges"]:
        src = edge["source"]
        target_mod = edge["target"]
        target_leaf = target_mod.split(".")[-1]
        for candidate_mod in (target_mod, target_leaf):
            for target_nid in mod_to_nodes.get(candidate_mod, ()):
                reverse_importers.setdefault(target_nid, set()).add(src)

    queue = []
    visited = set()
    for ch in changed_files:
        norm_ch = str(ch).replace("\\", "/")
        ch_stem = Path(norm_ch).stem
        for nid in node_ids:
            if nid == norm_ch or nid.endswith("/" + norm_ch) or Path(nid).stem == ch_stem:
                if nid not in visited:
                    visited.add(nid)
                    queue.append(nid)
            elif _is_test_file(nid) and Path(nid).stem in {
                "test_" + ch_stem,
                ch_stem + "_test",
            }:
                if nid not in visited:
                    visited.add(nid)
                    queue.append(nid)

    idx = 0
    while idx < len(queue):
        curr = queue[idx]
        idx += 1
        for importer in sorted(reverse_importers.get(curr, ())):
            if importer not in visited:
                visited.add(importer)
                queue.append(importer)

    return sorted(nid for nid in visited if _is_test_file(nid))


def _format_signature(fn_node):
    """Return a deterministic string representation of a function/method signature."""
    args_obj = fn_node.args
    parts = []
    for a in getattr(args_obj, "posonlyargs", ()):
        parts.append(a.arg + "/")
    num_pos = len(args_obj.args)
    num_defaults = len(args_obj.defaults)
    default_start = num_pos - num_defaults
    for i, a in enumerate(args_obj.args):
        if i >= default_start:
            def_node = args_obj.defaults[i - default_start]
            parts.append("%s=%s" % (a.arg, ast.dump(def_node)))
        else:
            parts.append(a.arg)
    if args_obj.vararg:
        parts.append("*" + args_obj.vararg.arg)
    for a, kw_def in zip(args_obj.kwonlyargs, args_obj.kw_defaults):
        if kw_def is not None:
            parts.append("%s=%s" % (a.arg, ast.dump(kw_def)))
        else:
            parts.append(a.arg)
    if args_obj.kwarg:
        parts.append("**" + args_obj.kwarg.arg)
    prefix = "async def" if isinstance(fn_node, ast.AsyncFunctionDef) else "def"
    return "%s(%s)" % (prefix, ", ".join(parts))


def _extract_surface(source_text):
    """Extract top-level symbols, class methods, signatures, and imports from Python source."""
    tree = ast.parse(source_text)
    symbols = {}
    imports = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols[node.name] = _format_signature(node)
        elif isinstance(node, ast.ClassDef):
            symbols[node.name] = "class(%d bases)" % len(node.bases)
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    symbols["%s.%s" % (node.name, item.name)] = _format_signature(item)
    return symbols, imports


def compute_ast_surface_diff(old_source, new_source):
    """Compute deterministic AST symbol, signature, and import differences (PatchDiff, arXiv:2503.15223)."""
    old_syms, old_imps = _extract_surface(old_source)
    new_syms, new_imps = _extract_surface(new_source)
    old_keys = set(old_syms.keys())
    new_keys = set(new_syms.keys())
    added = sorted(new_keys - old_keys)
    removed = sorted(old_keys - new_keys)
    sig_changes = []
    for sym in sorted(old_keys & new_keys):
        if old_syms[sym] != new_syms[sym]:
            sig_changes.append(
                {"symbol": sym, "old": old_syms[sym], "new": new_syms[sym]}
            )
    return {
        "added_symbols": added,
        "removed_symbols": removed,
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


def run_self_test():
    """Verify AST parsing, deterministic graph generation, CALLS edges, complexity, impacted-test selection, AST diff, and LF output."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
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
        nodes = {n["id"]: n for n in loaded.get("nodes", [])}
        if "sample.py" not in nodes:
            print("SELF-TEST FAIL: missing sample.py in %r" % nodes, file=sys.stderr)
            return 1
        if nodes["sample.py"]["classes"] != ["Widget"]:
            print("SELF-TEST FAIL: missing ClassDef Widget", file=sys.stderr)
            return 1
        if nodes["sample.py"]["functions"] != ["async_fn", "sync_fn"]:
            print(
                "SELF-TEST FAIL: missing functions %r" % nodes["sample.py"]["functions"],
                file=sys.stderr,
            )
            return 1
        if nodes["sample.py"]["function_complexities"].get("sync_fn") != 3:
            print("SELF-TEST FAIL: expected sync_fn complexity 3", file=sys.stderr)
            return 1
        if not any(
            e.get("type") == "CALLS"
            and e.get("source") == "test_widget.py"
            and e.get("target") == "sample.py"
            for e in loaded.get("edges", [])
        ):
            print("SELF-TEST FAIL: missing CALLS edge in %r" % loaded.get("edges"), file=sys.stderr)
            return 1
        if not find_high_complexity_functions(loaded, threshold=3):
            print("SELF-TEST FAIL: find_high_complexity_functions empty", file=sys.stderr)
            return 1
        impacted = find_impacted_tests(str(tmp_dir), ["sample.py"])
        if impacted != ["test_widget.py"]:
            print("SELF-TEST FAIL: expected ['test_widget.py'], got %r" % impacted, file=sys.stderr)
            return 1
        surf_diff = compute_ast_surface_diff(
            "import os\ndef f(a):\n    return a\n",
            "import os\nimport sys\ndef f(a, b=1):\n    return a + b\ndef g():\n    return 0\n",
        )
        if surf_diff["added_symbols"] != ["g"] or not surf_diff["signature_changes"]:
            print("SELF-TEST FAIL: compute_ast_surface_diff failed: %r" % surf_diff, file=sys.stderr)
            return 1
        out_flag_target = tmp_dir / "scratch" / "stage0_graph.json"
        if main([str(tmp_dir), "--out", str(out_flag_target)]) != 0 or not out_flag_target.is_file():
            print("SELF-TEST FAIL: --out flag failed", file=sys.stderr)
            return 1
    print("structural_graph_polyfill.py self-test: PASS")
    return 0


def main(argv=None):
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
    args = parser.parse_args(argv)

    if args.self_test:
        return run_self_test()
    if args.ast_diff:
        old_p, new_p = Path(args.ast_diff[0]), Path(args.ast_diff[1])
        diff = compute_ast_surface_diff(
            old_p.read_text(encoding="utf-8"), new_p.read_text(encoding="utf-8")
        )
        print(json.dumps(diff, indent=2))
        return 0
    if args.high_complexity is not None:
        target_dir = args.target_directory or "."
        high = find_high_complexity_functions(target_dir, threshold=args.high_complexity)
        print(json.dumps({"high_complexity_functions": high}, indent=2))
        return 0
    if args.impacted_tests:
        target_dir = args.target_directory or "."
        impacted = find_impacted_tests(target_dir, args.impacted_tests)
        print(json.dumps({"impacted_tests": impacted}, indent=2))
        return 0

    dest_str = args.out_flag or args.output_json_path
    if not args.target_directory or not dest_str:
        parser.print_usage(sys.stderr)
        return 1

    graph = build_graph(args.target_directory)
    output_path = Path(dest_str)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(graph, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print("Success! Graph written to %s" % output_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())

