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
_SAFE_AST_TYPES = (
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
)
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
_BUILTIN_MATH_CALLS = {"abs": abs, "min": min, "max": max}


def _is_safe_call_node(node):
    """Return True if an ast.Call node invokes an allowed pure function without keywords."""
    return (
        isinstance(node.func, ast.Name)
        and node.func.id in _ALLOWED_CALLS
        and not node.keywords
    )


def _validate_safe_ast(tree):
    """Ensure an expression AST contains only safe arithmetic/boolean/comparison nodes."""
    for node in ast.walk(tree):
        if isinstance(node, _SAFE_AST_TYPES):
            continue
        if isinstance(node, ast.Call):
            if _is_safe_call_node(node):
                continue
            raise ValueError("Unsafe call in constraint expression: %r" % ast.dump(node))
        raise ValueError("Unsafe AST node in constraint expression: %s" % type(node).__name__)


def _eval_constant_node(node):
    """Evaluate an ast.Constant node to bool or int."""
    if isinstance(node.value, (int, bool)):
        return node.value
    raise ValueError("Unsupported constant type: %r" % (node.value,))


def _eval_name_node(node, env):
    """Resolve a variable or boolean literal identifier from env."""
    if node.id in env:
        return env[node.id]
    if node.id == "True":
        return True
    if node.id == "False":
        return False
    raise ValueError("Unknown variable in constraint expression: %r" % node.id)


def _eval_unary_node(node, env):
    """Evaluate a unary operator node."""
    op_fn = _UNARY_OPS.get(type(node.op))
    if op_fn is None:
        raise ValueError("Unsupported unary operator: %s" % type(node.op).__name__)
    return op_fn(_eval_ast_node(node.operand, env))


def _eval_bin_node(node, env):
    """Evaluate a binary arithmetic operator node."""
    op_fn = _BIN_OPS.get(type(node.op))
    if op_fn is None:
        raise ValueError("Unsupported binary operator: %s" % type(node.op).__name__)
    return op_fn(_eval_ast_node(node.left, env), _eval_ast_node(node.right, env))


def _eval_bool_op_node(node, env):
    """Evaluate an And/Or boolean operator node."""
    if isinstance(node.op, ast.And):
        return all(bool(_eval_ast_node(v, env)) for v in node.values)
    if isinstance(node.op, ast.Or):
        return any(bool(_eval_ast_node(v, env)) for v in node.values)
    raise ValueError("Unsupported boolean operator: %s" % type(node.op).__name__)


def _eval_compare_node(node, env):
    """Evaluate a chained comparison node."""
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


def _eval_logic_call(fn_name, args):
    """Evaluate a logical function call (And, Or, Not, Implies)."""
    if fn_name == "And":
        return all(bool(a) for a in args)
    if fn_name == "Or":
        return any(bool(a) for a in args)
    if fn_name == "Not":
        if len(args) != 1:
            raise ValueError("Not() takes exactly 1 argument")
        return not bool(args[0])
    if len(args) != 2:
        raise ValueError("Implies() takes exactly 2 arguments")
    return (not bool(args[0])) or bool(args[1])


def _eval_call_node(node, env):
    """Evaluate a whitelisted function call node."""
    if not isinstance(node.func, ast.Name):
        raise ValueError("Unsupported call target: %s" % type(node.func).__name__)
    fn_name = node.func.id
    args = [_eval_ast_node(a, env) for a in node.args]
    if fn_name in _BUILTIN_MATH_CALLS:
        return _BUILTIN_MATH_CALLS[fn_name](*args)
    if fn_name in {"And", "Or", "Not", "Implies"}:
        return _eval_logic_call(fn_name, args)
    raise ValueError("Unsupported function call: %s" % fn_name)


_AST_EVAL_DISPATCH = {
    ast.Constant: lambda node, env: _eval_constant_node(node),
    ast.Name: _eval_name_node,
    ast.UnaryOp: _eval_unary_node,
    ast.BinOp: _eval_bin_node,
    ast.BoolOp: _eval_bool_op_node,
    ast.Compare: _eval_compare_node,
    ast.Call: _eval_call_node,
}


def _eval_ast_node(node, env):
    """Evaluate a validated AST node over Python primitives."""
    if isinstance(node, ast.Expression):
        return _eval_ast_node(node.body, env)
    handler = _AST_EVAL_DISPATCH.get(type(node))
    if handler is not None:
        return handler(node, env)
    raise ValueError("Unsupported AST node: %s" % type(node).__name__)


def _eval_expr(expr, env):
    """Safely parse and evaluate an arithmetic/comparison/boolean expression."""
    tree = ast.parse(expr, mode="eval")
    _validate_safe_ast(tree)
    return bool(_eval_ast_node(tree, env))


def _all_constraints_hold(constraints, assignment):
    """Return True if every constraint expression evaluates to True under assignment."""
    return all(_eval_expr(c, assignment) for c in constraints)


def _extract_referenced_vars(exprs):
    """Return the set of variable identifiers referenced across a list of expressions."""
    refs = set()
    excluded = _ALLOWED_CALLS | {"True", "False"}
    for expr in exprs:
        tree = ast.parse(expr, mode="eval")
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id not in excluded:
                refs.add(node.id)
    return refs


def _compile_constraint_scopes(constraints, var_set):
    """Pair each constraint expression with its referenced variable scope."""
    return [
        (c, frozenset(_extract_referenced_vars([c]) & var_set))
        for c in constraints
    ]


def _order_mrv_variables(variables, scoped_constraints):
    """Order variables by Minimum Remaining Values (domain size) and degree heuristic."""
    degree = {v: 0 for v in variables}
    for _, scope in scoped_constraints:
        for v in scope:
            if v in degree:
                degree[v] += 1
    return sorted(
        variables.keys(),
        key=lambda v: (len(variables[v]), -degree[v], v),
    )


def _consistent_partial(assignment, scoped_constraints):
    """Return True if all constraints whose scope is bound in assignment evaluate to True."""
    return all(
        _eval_expr(c, assignment)
        for c, scope in scoped_constraints
        if scope.issubset(assignment.keys())
    )


def _find_satisfying_assignment(variables, constraints):
    """Return a satisfying assignment dict for variables and constraints, or None."""
    scoped = _compile_constraint_scopes(constraints, set(variables.keys()))
    if not _consistent_partial({}, scoped):
        return None
    var_names = _order_mrv_variables(variables, scoped)

    def backtrack(idx, assignment):
        if idx == len(var_names):
            return {k: assignment[k] for k in sorted(assignment.keys())}
        name = var_names[idx]
        for val in variables[name]:
            assignment[name] = val
            if _consistent_partial(assignment, scoped):
                result = backtrack(idx + 1, assignment)
                if result is not None:
                    return result
            del assignment[name]
        return None

    return backtrack(0, {})


def _extract_implies_antecedent(inv_expr):
    """If inv_expr is Implies(P, Q), return the source string of P; otherwise None."""
    tree = ast.parse(inv_expr, mode="eval")
    body = tree.body
    is_implies = (
        isinstance(body, ast.Call)
        and isinstance(body.func, ast.Name)
        and body.func.id == "Implies"
        and len(body.args) == 2
    )
    return ast.unparse(body.args[0]) if is_implies else None


def _extract_unsat_core_finite(variables, constraints):
    """Compute a deterministic deletion-based Minimal Unsatisfiable Core (MUS)."""
    core = list(constraints)
    idx = 0
    while idx < len(core):
        candidate = core[:idx] + core[idx + 1 :]
        if candidate and _find_satisfying_assignment(variables, candidate) is None:
            core = candidate
        else:
            idx += 1
    return core


def _check_finite_invariant(inv, variables, constraints, model, unconstrained):
    """Verify a single invariant over finite domains; return failure dict or None."""
    negated_constraints = list(constraints) + ["Not(%s)" % inv]
    counterexample = _find_satisfying_assignment(variables, negated_constraints)
    if counterexample is not None:
        return {
            "status": "REFUTED",
            "engine": "stdlib-finite-domain",
            "model": model,
            "refuted_invariant": inv,
            "counterexample": counterexample,
            "unconstrained_variables": unconstrained,
            "constraints_count": len(constraints),
        }
    antecedent = _extract_implies_antecedent(inv)
    if antecedent is not None:
        ant_model = _find_satisfying_assignment(variables, list(constraints) + [antecedent])
        if ant_model is None:
            return {
                "status": "VACUOUS",
                "engine": "stdlib-finite-domain",
                "model": model,
                "vacuous_invariant": inv,
                "vacuous_reason": "antecedent_unsat",
                "unconstrained_variables": unconstrained,
                "constraints_count": len(constraints),
            }
    return None


def solve_finite_domain(spec):
    """Solve a finite-domain constraint specification deterministically with refutation and vacuity checks."""
    variables = spec.get("variables", {})
    constraints = spec.get("constraints", [])
    invariants = spec.get("invariants", [])
    referenced = _extract_referenced_vars(list(constraints) + list(invariants))
    unconstrained = sorted(set(variables.keys()) - referenced)

    model = _find_satisfying_assignment(variables, constraints)
    if model is None:
        return {
            "status": "UNSAT",
            "engine": "stdlib-finite-domain",
            "model": None,
            "unsat_core": _extract_unsat_core_finite(variables, constraints),
            "unconstrained_variables": unconstrained,
            "constraints_count": len(constraints),
        }

    for inv in invariants:
        failure = _check_finite_invariant(inv, variables, constraints, model, unconstrained)
        if failure is not None:
            return failure

    return {
        "status": "SAT",
        "engine": "stdlib-finite-domain",
        "model": model,
        "unconstrained_variables": unconstrained,
        "constraints_count": len(constraints),
    }


def _eval_z3_name(node, env):
    """Resolve a variable or boolean constant in a Z3 expression."""
    if node.id in env:
        return env[node.id]
    if node.id == "True":
        return True
    if node.id == "False":
        return False
    raise ValueError("Unknown variable in Z3 expression: %r" % node.id)


def _eval_z3_unary(node, env, z3_mod):
    """Evaluate a unary AST node into a Z3 expression."""
    operand = _eval_z3_ast_node(node.operand, env, z3_mod)
    if isinstance(node.op, ast.Not):
        return z3_mod.Not(operand)
    return _UNARY_OPS[type(node.op)](operand)


def _eval_z3_compare(node, env, z3_mod):
    """Evaluate a comparison AST node into a Z3 expression."""
    terms = []
    left_val = _eval_z3_ast_node(node.left, env, z3_mod)
    for op, comparator in zip(node.ops, node.comparators):
        right_val = _eval_z3_ast_node(comparator, env, z3_mod)
        terms.append(_CMP_OPS[type(op)](left_val, right_val))
        left_val = right_val
    return terms[0] if len(terms) == 1 else z3_mod.And(*terms)


def _eval_z3_bool_op(node, env, z3_mod):
    """Evaluate a BoolOp AST node into a Z3 expression."""
    vals = [_eval_z3_ast_node(v, env, z3_mod) for v in node.values]
    return z3_mod.And(*vals) if isinstance(node.op, ast.And) else z3_mod.Or(*vals)


def _eval_z3_call(node, env, z3_mod):
    """Evaluate a Call AST node into a Z3 expression."""
    if not isinstance(node.func, ast.Name):
        raise ValueError("Unsupported Z3 call node: %s" % type(node).__name__)
    fn = env[node.func.id]
    args = [_eval_z3_ast_node(a, env, z3_mod) for a in node.args]
    return fn(*args)


def _eval_z3_bin_op(node, env, z3_mod):
    """Evaluate a BinOp AST node into a Z3 expression."""
    return _BIN_OPS[type(node.op)](
        _eval_z3_ast_node(node.left, env, z3_mod),
        _eval_z3_ast_node(node.right, env, z3_mod),
    )


_Z3_AST_DISPATCH = {
    ast.Constant: lambda node, env, z3_mod: node.value,
    ast.Name: lambda node, env, z3_mod: _eval_z3_name(node, env),
    ast.UnaryOp: _eval_z3_unary,
    ast.BinOp: _eval_z3_bin_op,
    ast.BoolOp: _eval_z3_bool_op,
    ast.Compare: _eval_z3_compare,
    ast.Call: _eval_z3_call,
}


def _eval_z3_ast_node(node, env, z3_mod):
    """Evaluate a validated AST node into a Z3 expression."""
    if isinstance(node, ast.Expression):
        return _eval_z3_ast_node(node.body, env, z3_mod)
    handler = _Z3_AST_DISPATCH.get(type(node))
    if handler is not None:
        return handler(node, env, z3_mod)
    raise ValueError("Unsupported Z3 AST node: %s" % type(node).__name__)


def _build_z3_solver(z3_mod, variables, constraints):
    """Initialize a Z3 Solver, variable map, and evaluation environment."""
    solver = z3_mod.Solver()
    z3_vars = {}
    env = {
        "And": z3_mod.And,
        "Or": z3_mod.Or,
        "Not": z3_mod.Not,
        "Implies": z3_mod.Implies,
        "abs": lambda x: z3_mod.If(x >= 0, x, -x),
        "min": lambda a, b: z3_mod.If(a <= b, a, b),
        "max": lambda a, b: z3_mod.If(a >= b, a, b),
    }
    for name, domain in variables.items():
        var = z3_mod.Int(name)
        z3_vars[name] = var
        env[name] = var
        if isinstance(domain, list) and domain:
            solver.add(z3_mod.Or([var == int(v) for v in domain]))
    for expr in constraints:
        tree = ast.parse(expr, mode="eval")
        solver.add(_eval_z3_ast_node(tree, env, z3_mod))
    return solver, z3_vars, env


def _check_z3_invariant(inv, solver, env, z3_vars, z3_mod, model_dict, unconstrained, constraints_count):
    """Check one invariant in Z3 for refutation or vacuity; return failure dict or None."""
    solver.push()
    inv_tree = ast.parse(inv, mode="eval")
    solver.add(z3_mod.Not(_eval_z3_ast_node(inv_tree, env, z3_mod)))
    if solver.check() == z3_mod.sat:
        ce_m = solver.model()
        ce_dict = {name: ce_m[var].as_long() for name, var in sorted(z3_vars.items())}
        solver.pop()
        return {
            "status": "REFUTED",
            "engine": "z3-solver",
            "model": model_dict,
            "refuted_invariant": inv,
            "counterexample": ce_dict,
            "unconstrained_variables": unconstrained,
            "constraints_count": constraints_count,
        }
    solver.pop()
    antecedent = _extract_implies_antecedent(inv)
    if antecedent is None:
        return None
    solver.push()
    ant_tree = ast.parse(antecedent, mode="eval")
    solver.add(_eval_z3_ast_node(ant_tree, env, z3_mod))
    is_ant_unsat = solver.check() != z3_mod.sat
    solver.pop()
    if is_ant_unsat:
        return {
            "status": "VACUOUS",
            "engine": "z3-solver",
            "model": model_dict,
            "vacuous_invariant": inv,
            "vacuous_reason": "antecedent_unsat",
            "unconstrained_variables": unconstrained,
            "constraints_count": constraints_count,
        }
    return None


def _solve_with_z3(spec, z3_mod):
    """Solve constraint specification using the Z3 solver module."""
    variables = spec.get("variables", {})
    constraints = spec.get("constraints", [])
    invariants = spec.get("invariants", [])
    referenced = _extract_referenced_vars(list(constraints) + list(invariants))
    unconstrained = sorted(set(variables.keys()) - referenced)
    solver, z3_vars, env = _build_z3_solver(z3_mod, variables, constraints)
    if solver.check() != z3_mod.sat:
        return {
            "status": "UNSAT",
            "engine": "z3-solver",
            "model": None,
            "unsat_core": _extract_unsat_core_finite(variables, constraints),
            "unconstrained_variables": unconstrained,
            "constraints_count": len(constraints),
        }
    m = solver.model()
    model_dict = {name: m[var].as_long() for name, var in sorted(z3_vars.items())}
    for inv in invariants:
        failure = _check_z3_invariant(
            inv, solver, env, z3_vars, z3_mod, model_dict, unconstrained, len(constraints)
        )
        if failure is not None:
            return failure
    return {
        "status": "SAT",
        "engine": "z3-solver",
        "model": model_dict,
        "unconstrained_variables": unconstrained,
        "constraints_count": len(constraints),
    }


def solve_spec(spec):
    """Solve constraint spec using z3 if available, otherwise stdlib fallback."""
    for expr in list(spec.get("constraints", [])) + list(spec.get("invariants", [])):
        _validate_safe_ast(ast.parse(expr, mode="eval"))
    try:
        import z3  # type: ignore

        return _solve_with_z3(spec, z3)
    except Exception:
        return solve_finite_domain(spec)


def _check_ast_sandbox_safety():
    """Verify that attribute access expressions are rejected by the AST validator."""
    try:
        _eval_expr("().__class__", {})
        print("Self-test AST safety failed: allowed attribute access", file=sys.stderr)
        return False
    except ValueError:
        return True


def _check_sat_and_refuted_cases():
    """Run SAT and REFUTED self-test cases and return (ok, engine_name)."""
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
        return False, ""

    refuted_spec = dict(sat_spec, invariants=["P1 > P3"])
    refuted_res = solve_spec(refuted_spec)
    if refuted_res["status"] != "REFUTED" or refuted_res.get("refuted_invariant") != "P1 > P3":
        print("Self-test REFUTED failed: %r" % (refuted_res,))
        return False, ""
    return True, sat_res["engine"]


def _check_unsat_and_vacuous_cases():
    """Run UNSAT core and VACUOUS implication self-test cases."""
    unsat_spec = {
        "variables": {"a": [1, 2], "b": [1, 2], "unused": [1, 2]},
        "constraints": ["a == 1", "b == 2", "a == 2"],
    }
    unsat_res = solve_spec(unsat_spec)
    unsat_ok = (
        unsat_res["status"] == "UNSAT"
        and unsat_res.get("unsat_core") == ["a == 1", "a == 2"]
        and unsat_res.get("unconstrained_variables") == ["unused"]
    )
    if not unsat_ok:
        print("Self-test UNSAT/core failed: %r" % (unsat_res,))
        return False

    vac_spec = {
        "variables": {"x": [1, 2]},
        "constraints": ["x == 1"],
        "invariants": ["Implies(x == 2, x == 99)"],
    }
    vac_res = solve_spec(vac_spec)
    if vac_res["status"] != "VACUOUS" or vac_res.get("vacuous_invariant") != "Implies(x == 2, x == 99)":
        print("Self-test VACUOUS failed: %r" % (vac_res,))
        return False
    return True


def run_self_test():
    """Verify SAT, UNSAT, REFUTED, VACUOUS proofs and AST sandbox safety deterministically."""
    if not _check_ast_sandbox_safety():
        return 1
    ok_sat, engine = _check_sat_and_refuted_cases()
    if not ok_sat:
        return 1
    if not _check_unsat_and_vacuous_cases():
        return 1
    print("logical_z3_polyfill self-test: PASS (%s)" % engine)
    return 0


def _run_cli_self_test():
    """Execute run_self_test plus a temporary directory --out CLI verification."""
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


def _build_arg_parser():
    """Create the CLI argument parser for logical_z3_polyfill."""
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
    return parser


def main(argv=None):
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    if args.self_test:
        return _run_cli_self_test()

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
