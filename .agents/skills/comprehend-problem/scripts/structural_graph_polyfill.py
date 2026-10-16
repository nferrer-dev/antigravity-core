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


def parse_file(filepath):
    """Parse a single Python file and return its imports, classes, and functions."""
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
                "error": "UnicodeDecodeError",
            }

    try:
        tree = ast.parse(content)
    except SyntaxError:
        return {
            "imports": [],
            "classes": [],
            "functions": [],
            "error": "SyntaxError",
        }

    imports = set()
    classes = []
    functions = []

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

    return {
        "imports": sorted(imports),
        "classes": sorted(classes),
        "functions": sorted(functions),
    }


def build_graph(directory):
    """Build a deterministic structural dependency graph for a directory."""
    graph = {"nodes": [], "edges": []}

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

            graph["nodes"].append(
                {
                    "id": rel_path,
                    "type": "file",
                    "classes": data["classes"],
                    "functions": data["functions"],
                }
            )

            for imp in data["imports"]:
                graph["edges"].append(
                    {
                        "source": rel_path,
                        "target": imp,
                        "relation": "imports",
                    }
                )

    return graph


def _is_test_file(rel_path):
    name = Path(rel_path).name
    return name.startswith("test_") or name.endswith("_test.py")


def find_impacted_tests(directory, changed_files):
    """Return sorted relative paths of test_*.py files transitively impacted by changed_files."""
    graph = build_graph(directory)
    node_ids = [n["id"] for n in graph["nodes"]]

    # Map module identifiers (stem and dotted path) to node relative paths
    mod_to_nodes = {}
    node_to_mods = {}
    for nid in node_ids:
        p = Path(nid)
        stem = p.stem
        dotted = ".".join(p.with_suffix("").parts)
        mods = {stem, dotted}
        node_to_mods[nid] = mods
        for m in mods:
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


def run_self_test():
    """Verify AST parsing, deterministic graph generation, impacted-test selection, and LF output."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        sample_py = tmp_dir / "sample.py"
        sample_py.write_text(
            "import json\nfrom pathlib import Path\n\n"
            "class Widget:\n    pass\n\n"
            "def sync_fn():\n    return 1\n\n"
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
        impacted = find_impacted_tests(str(tmp_dir), ["sample.py"])
        if impacted != ["test_widget.py"]:
            print("SELF-TEST FAIL: expected ['test_widget.py'], got %r" % impacted, file=sys.stderr)
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
