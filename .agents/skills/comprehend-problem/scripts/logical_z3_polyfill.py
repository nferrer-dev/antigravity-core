"""Logical constraint solver polyfill (Stage 0 Epistemic Engine).

Provides a deterministic CLI fallback when the optional `chiasmus` MCP server
is unavailable. Uses `z3-solver` if installed in the active Python environment,
and falls back to a deterministic stdlib finite-domain backtracking solver for
ordering, boolean, and linear integer constraints.

Usage:
    python logical_z3_polyfill.py <spec_json_path> <output_json_path>
    python logical_z3_polyfill.py --self-test
"""
import ast
import json
import operator
import sys
from pathlib import Path

_ALLOWED_CALLS = {"And", "Or", "Not", "Implies", "abs", "min", "max"}
_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
}
_UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
    ast.Not: operator.not_,
}
_CMP_OPS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}


def _validate_safe_ast(tree):
    """Ensure an expression AST contains only safe arithmetic/boolean/comparison nodes."""
    for node in ast.walk(tree):
        if isinstance(
            node,
            (
                ast.Expression,
                ast.BoolOp,
                ast.BinOp,
                ast.UnaryOp,
                ast.Compare,
                ast.Name,
                ast.Load,
                ast.Constant,
                ast.And,
                ast.Or,
                ast.Add,
                ast.Sub,
                ast.Mult,
                ast.FloorDiv,
                ast.Mod,
                ast.UAdd,
                ast.USub,
                ast.Not,
                ast.Eq,
                ast.NotEq,
                ast.Lt,
                ast.LtE,
                ast.Gt,
                ast.GtE,
            ),
        ):
            continue
        if isinstance(node, ast.Call):
            if (
                isinstance(node.func, ast.Name)
                and node.func.id in _ALLOWED_CALLS
                and not node.keywords
            ):
                continue
            raise ValueError("Unsafe call in constraint expression: %r" % ast.dump(node))
        raise ValueError("Unsafe AST node in constraint expression: %s" % type(node).__name__)


def _eval_ast_node(node, env):
    """Evaluate a validated AST node over Python primitives."""
    if isinstance(node, ast.Expression):
        return _eval_ast_node(node.body, env)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, bool)):
            return node.value
        raise ValueError("Unsupported constant type: %r" % (node.value,))
    if isinstance(node, ast.Name):
        if node.id in env:
            return env[node.id]
        if node.id == "True":
            return True
        if node.id == "False":
            return False
        raise ValueError("Unknown variable in constraint expression: %r" % node.id)
    if isinstance(node, ast.UnaryOp):
        op_fn = _UNARY_OPS.get(type(node.op))
        if op_fn is None:
            raise ValueError("Unsupported unary operator: %s" % type(node.op).__name__)
        return op_fn(_eval_ast_node(node.operand, env))
    if isinstance(node, ast.BinOp):
        op_fn = _BIN_OPS.get(type(node.op))
        if op_fn is None:
            raise ValueError("Unsupported binary operator: %s" % type(node.op).__name__)
        return op_fn(_eval_ast_node(node.left, env), _eval_ast_node(node.right, env))
    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            return all(bool(_eval_ast_node(v, env)) for v in node.values)
        if isinstance(node.op, ast.Or):
            return any(bool(_eval_ast_node(v, env)) for v in node.values)
        raise ValueError("Unsupported boolean operator: %s" % type(node.op).__name__)
    if isinstance(node, ast.Compare):
        left_val = _eval_ast_node(node.left, env)
        for op, comparator in zip(node.ops, node.comparators):
            cmp_fn = _CMP_OPS.get(type(op))
            if cmp_fn is None:
                raise ValueError("Unsupported comparison operator: %s" % type(op).__name__)
            right_val = _eval_ast_node(comparator, env)
            if not cmp_fn(left_val, right_val):
                return False
            left_val = right_val
        return True
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        fn_name = node.func.id
        args = [_eval_ast_node(a, env) for a in node.args]
        if fn_name == "And":
            return all(bool(a) for a in args)
        if fn_name == "Or":
            return any(bool(a) for a in args)
        if fn_name == "Not":
            if len(args) != 1:
                raise ValueError("Not() takes exactly 1 argument")
            return not bool(args[0])
        if fn_name == "Implies":
            if len(args) != 2:
                raise ValueError("Implies() takes exactly 2 arguments")
            return (not bool(args[0])) or bool(args[1])
        if fn_name in {"abs", "min", "max"}:
            return {"abs": abs, "min": min, "max": max}[fn_name](*args)
    raise ValueError("Unsupported AST node: %s" % type(node).__name__)


def _eval_expr(expr, env):
    """Safely parse and evaluate an arithmetic/comparison/boolean expression."""
    tree = ast.parse(expr, mode="eval")
    _validate_safe_ast(tree)
    return bool(_eval_ast_node(tree, env))


def _find_satisfying_assignment(variables, constraints):
    """Return a satisfying assignment dict for variables and constraints, or None."""
    var_names = sorted(variables.keys())

    def backtrack(idx, assignment):
        if idx == len(var_names):
            for c in constraints:
                if not _eval_expr(c, assignment):
                    return None
            return dict(assignment)
        name = var_names[idx]
        domain = variables[name]
        for val in domain:
            assignment[name] = val
            result = backtrack(idx + 1, assignment)
            if result is not None:
                return result
            del assignment[name]
        return None

    return backtrack(0, {})


def solve_finite_domain(spec):
    """Solve a finite-domain constraint specification deterministically with refutation checks."""
    variables = spec.get("variables", {})
    constraints = spec.get("constraints", [])
    invariants = spec.get("invariants", [])

    model = _find_satisfying_assignment(variables, constraints)
    if model is None:
        return {
            "status": "UNSAT",
            "engine": "stdlib-finite-domain",
            "model": None,
            "constraints_count": len(constraints),
        }

    for inv in invariants:
        negated_constraints = list(constraints) + ["Not(%s)" % inv]
        counterexample = _find_satisfying_assignment(variables, negated_constraints)
        if counterexample is not None:
            return {
                "status": "REFUTED",
                "engine": "stdlib-finite-domain",
                "model": model,
                "refuted_invariant": inv,
                "counterexample": counterexample,
                "constraints_count": len(constraints),
            }

    return {
        "status": "SAT",
        "engine": "stdlib-finite-domain",
        "model": model,
        "constraints_count": len(constraints),
    }


def _eval_z3_ast_node(node, env, z3_mod):
    """Evaluate a validated AST node into a Z3 expression."""
    if isinstance(node, ast.Expression):
        return _eval_z3_ast_node(node.body, env, z3_mod)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in env:
            return env[node.id]
        if node.id == "True":
            return True
        if node.id == "False":
            return False
        raise ValueError("Unknown variable in Z3 expression: %r" % node.id)
    if isinstance(node, ast.UnaryOp):
        operand = _eval_z3_ast_node(node.operand, env, z3_mod)
        if isinstance(node.op, ast.Not):
            return z3_mod.Not(operand)
        return _UNARY_OPS[type(node.op)](operand)
    if isinstance(node, ast.BinOp):
        return _BIN_OPS[type(node.op)](
            _eval_z3_ast_node(node.left, env, z3_mod),
            _eval_z3_ast_node(node.right, env, z3_mod),
        )
    if isinstance(node, ast.BoolOp):
        vals = [_eval_z3_ast_node(v, env, z3_mod) for v in node.values]
        return z3_mod.And(*vals) if isinstance(node.op, ast.And) else z3_mod.Or(*vals)
    if isinstance(node, ast.Compare):
        terms = []
        left_val = _eval_z3_ast_node(node.left, env, z3_mod)
        for op, comparator in zip(node.ops, node.comparators):
            right_val = _eval_z3_ast_node(comparator, env, z3_mod)
            terms.append(_CMP_OPS[type(op)](left_val, right_val))
            left_val = right_val
        return terms[0] if len(terms) == 1 else z3_mod.And(*terms)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        fn = env[node.func.id]
        args = [_eval_z3_ast_node(a, env, z3_mod) for a in node.args]
        return fn(*args)
    raise ValueError("Unsupported Z3 AST node: %s" % type(node).__name__)


def solve_spec(spec):
    """Solve constraint spec using z3 if available, otherwise stdlib fallback."""
    for expr in list(spec.get("constraints", [])) + list(spec.get("invariants", [])):
        _validate_safe_ast(ast.parse(expr, mode="eval"))
    try:
        import z3  # type: ignore

        solver = z3.Solver()
        variables = spec.get("variables", {})
        constraints = spec.get("constraints", [])
        invariants = spec.get("invariants", [])
        z3_vars = {}
        env = {
            "And": z3.And,
            "Or": z3.Or,
            "Not": z3.Not,
            "Implies": z3.Implies,
            "abs": lambda x: z3.If(x >= 0, x, -x),
            "min": lambda a, b: z3.If(a <= b, a, b),
            "max": lambda a, b: z3.If(a >= b, a, b),
        }
        for name, domain in variables.items():
            var = z3.Int(name)
            z3_vars[name] = var
            env[name] = var
            if isinstance(domain, list) and domain:
                solver.add(z3.Or([var == int(v) for v in domain]))
        for expr in constraints:
            tree = ast.parse(expr, mode="eval")
            solver.add(_eval_z3_ast_node(tree, env, z3))
        if solver.check() != z3.sat:
            return {
                "status": "UNSAT",
                "engine": "z3-solver",
                "model": None,
                "constraints_count": len(constraints),
            }
        m = solver.model()
        model_dict = {name: m[var].as_long() for name, var in sorted(z3_vars.items())}
        for inv in invariants:
            solver.push()
            inv_tree = ast.parse(inv, mode="eval")
            solver.add(z3.Not(_eval_z3_ast_node(inv_tree, env, z3)))
            if solver.check() == z3.sat:
                ce_m = solver.model()
                ce_dict = {name: ce_m[var].as_long() for name, var in sorted(z3_vars.items())}
                solver.pop()
                return {
                    "status": "REFUTED",
                    "engine": "z3-solver",
                    "model": model_dict,
                    "refuted_invariant": inv,
                    "counterexample": ce_dict,
                    "constraints_count": len(constraints),
                }
            solver.pop()
        return {
            "status": "SAT",
            "engine": "z3-solver",
            "model": model_dict,
            "constraints_count": len(constraints),
        }
    except Exception:
        return solve_finite_domain(spec)


def run_self_test():
    """Verify SAT, UNSAT, REFUTED proofs and AST sandbox safety deterministically."""
    try:
        _eval_expr("().__class__", {})
        print("Self-test AST safety failed: allowed attribute access", file=sys.stderr)
        return 1
    except ValueError:
        pass

    sat_spec = {
        "variables": {
            "P4": [1, 2, 3, 4],
            "P1": [1, 2, 3, 4],
            "P3": [1, 2, 3, 4],
            "P2": [1, 2, 3, 4],
        },
        "constraints": [
            "P4 != P1",
            "P4 != P3",
            "P4 != P2",
            "P1 != P3",
            "P1 != P2",
            "P3 != P2",
            "P4 < P1",
            "P4 < P3",
            "P1 < P3",
            "P1 < P2",
            "P3 < P2",
        ],
        "invariants": ["P4 < P2"],
    }
    sat_res = solve_spec(sat_spec)
    if sat_res["status"] != "SAT" or sat_res["model"] != {"P4": 1, "P1": 2, "P3": 3, "P2": 4}:
        print("Self-test SAT failed: %r" % (sat_res,))
        return 1

    refuted_spec = dict(sat_spec, invariants=["P1 > P3"])
    refuted_res = solve_spec(refuted_spec)
    if refuted_res["status"] != "REFUTED" or refuted_res.get("refuted_invariant") != "P1 > P3":
        print("Self-test REFUTED failed: %r" % (refuted_res,))
        return 1

    unsat_spec = {
        "variables": {"a": [1, 2], "b": [1, 2]},
        "constraints": ["a < b", "b < a"],
    }
    unsat_res = solve_spec(unsat_spec)
    if unsat_res["status"] != "UNSAT":
        print("Self-test UNSAT failed: %r" % (unsat_res,))
        return 1

    print("logical_z3_polyfill self-test: PASS (%s)" % sat_res["engine"])
    return 0


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(
        description="Solve a Stage 0 logical constraint specification deterministically."
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run built-in deterministic self-test and exit.",
    )
    parser.add_argument(
        "--out",
        dest="out_flag",
        help="Destination path for the output JSON proof (Stage 0 receipt).",
    )
    parser.add_argument(
        "spec_json_path",
        nargs="?",
        help="Input JSON constraint specification path.",
    )
    parser.add_argument(
        "output_json_path",
        nargs="?",
        help="Destination path for the output JSON proof.",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        import tempfile

        rc = run_self_test()
        if rc != 0:
            return rc
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            spec_p = tmp_dir / "spec.json"
            out_p = tmp_dir / "scratch" / "stage0_test.json"
            spec_p.write_text(
                json.dumps({"variables": {"x": [1, 2]}, "constraints": ["x == 2"]}),
                encoding="utf-8",
            )
            if main([str(spec_p), "--out", str(out_p)]) != 0 or not out_p.is_file():
                print("Self-test --out flag failed", file=sys.stderr)
                return 1
        return 0

    dest_str = args.out_flag or args.output_json_path
    if not args.spec_json_path or not dest_str:
        print("Usage: python logical_z3_polyfill.py <spec_json_path> [--out] <output_json_path>")
        return 1

    spec_path = Path(args.spec_json_path)
    output_path = Path(dest_str)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    result = solve_spec(spec)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("Success! Proof (%s) written to %s" % (result["status"], output_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
