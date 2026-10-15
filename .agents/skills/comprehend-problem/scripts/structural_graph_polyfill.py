"""Local pure-Python structural dependency graph polyfill for Stage 0 comprehend-problem.

Builds a deterministic JSON AST dependency and symbol graph for Python files when
the code-graph-context MCP server is unavailable.

Usage:
    python structural_graph_polyfill.py <target_directory> <output_json_path>
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


def run_self_test():
    """Verify AST parsing, deterministic graph generation, and LF UTF-8 output."""
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
        nodes = loaded.get("nodes", [])
        if len(nodes) != 1 or nodes[0]["id"] != "sample.py":
            print("SELF-TEST FAIL: unexpected nodes %r" % nodes, file=sys.stderr)
            return 1
        if nodes[0]["classes"] != ["Widget"]:
            print("SELF-TEST FAIL: missing ClassDef Widget", file=sys.stderr)
            return 1
        if nodes[0]["functions"] != ["async_fn", "sync_fn"]:
            print("SELF-TEST FAIL: missing functions %r" % nodes[0]["functions"], file=sys.stderr)
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

