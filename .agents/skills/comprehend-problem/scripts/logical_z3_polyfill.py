"""Logical constraint solver polyfill (Stage 0 Epistemic Engine).

Provides a deterministic CLI fallback when the optional `chiasmus` MCP server
is unavailable. Uses `z3-solver` if installed in the active Python environment,
and falls back to a deterministic stdlib finite-domain backtracking solver for
ordering, boolean, and linear integer constraints.

Usage:
    python logical_z3_polyfill.py <spec_json_path> <output_json_path>
    python logical_z3_polyfill.py --self-test
"""
import json
import sys
from pathlib import Path


def _eval_expr(expr, env):
    """Safely evaluate a simple arithmetic/comparison expression over integer/bool vars."""
    allowed_names = dict(env)
    allowed_names["abs"] = abs
    allowed_names["min"] = min
    allowed_names["max"] = max
    return bool(eval(expr, {"__builtins__": {}}, allowed_names))  # noqa: S307


def solve_finite_domain(spec):
    """Solve a finite-domain constraint specification deterministically.

    Spec format:
    {
      "variables": {"x": [1, 2, 3], "y": [1, 2, 3]},
      "constraints": ["x < y", "x + y == 4"]
    }
    """
    variables = spec.get("variables", {})
    constraints = spec.get("constraints", [])
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

    model = backtrack(0, {})
    if model is not None:
        return {
            "status": "SAT",
            "engine": "stdlib-finite-domain",
            "model": model,
            "constraints_count": len(constraints),
        }
    return {
        "status": "UNSAT",
        "engine": "stdlib-finite-domain",
        "model": None,
        "constraints_count": len(constraints),
    }


def solve_spec(spec):
    """Solve constraint spec using z3 if available, otherwise stdlib fallback."""
    try:
        import z3  # type: ignore

        solver = z3.Solver()
        variables = spec.get("variables", {})
        constraints = spec.get("constraints", [])
        z3_vars = {}
        env = {"And": z3.And, "Or": z3.Or, "Not": z3.Not, "Implies": z3.Implies}
        for name, domain in variables.items():
            var = z3.Int(name)
            z3_vars[name] = var
            env[name] = var
            if isinstance(domain, list) and domain:
                solver.add(z3.Or([var == int(v) for v in domain]))
        for expr in constraints:
            solver.add(eval(expr, {"__builtins__": {}}, env))  # noqa: S307
        check = solver.check()
        if check == z3.sat:
            m = solver.model()
            model_dict = {name: m[var].as_long() for name, var in sorted(z3_vars.items())}
            return {
                "status": "SAT",
                "engine": "z3-solver",
                "model": model_dict,
                "constraints_count": len(constraints),
            }
        return {
            "status": "UNSAT",
            "engine": "z3-solver",
            "model": None,
            "constraints_count": len(constraints),
        }
    except Exception:
        return solve_finite_domain(spec)


def run_self_test():
    """Verify SAT and UNSAT proofs deterministically."""
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
    }
    sat_res = solve_spec(sat_spec)
    if sat_res["status"] != "SAT" or sat_res["model"] != {"P4": 1, "P1": 2, "P3": 3, "P2": 4}:
        print("Self-test SAT failed: %r" % (sat_res,))
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


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--self-test":
        return run_self_test()
    if len(sys.argv) < 3:
        print("Usage: python logical_z3_polyfill.py <spec_json_path> <output_json_path>")
        return 1

    spec_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    result = solve_spec(spec)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("Success! Proof (%s) written to %s" % (result["status"], output_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
