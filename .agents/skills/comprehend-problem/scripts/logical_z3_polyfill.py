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
from collections import deque
import hashlib
import itertools
import json
import operator
import sys
from pathlib import Path

_MAX_TEMPORAL_STATES = 2048
_ALLOWED_CALLS = {"And", "Or", "Not", "Implies", "abs", "min", "max"}
_SAFE_AST_TYPES = (
    ast.Expression,
    ast.IfExp,
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
_SAFE_FUNC_AST_TYPES = _SAFE_AST_TYPES + (
    ast.FunctionDef,
    ast.arguments,
    ast.arg,
    ast.Return,
    ast.Assign,
    ast.AnnAssign,
    ast.AugAssign,
    ast.If,
    ast.Pass,
    ast.Assert,
    ast.Expr,
    ast.Store,
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


def _eval_ifexp_node(node, env):
    """Evaluate a conditional expression (body if test else orelse) node."""
    if _eval_ast_node(node.test, env):
        return _eval_ast_node(node.body, env)
    return _eval_ast_node(node.orelse, env)


_AST_EVAL_DISPATCH = {
    ast.Constant: lambda node, env: _eval_constant_node(node),
    ast.Name: _eval_name_node,
    ast.IfExp: _eval_ifexp_node,
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


def _is_domain_tautology(inv, variables, constraints):
    """Return True if inv already holds over raw variable domains without constraints."""
    if not constraints or _extract_implies_antecedent(inv) is not None:
        return False
    return _find_satisfying_assignment(variables, ["Not(%s)" % inv]) is None


def _check_clause_equivalence(
    variables, constraints, eq_constraints, engine_name, model, unconstrained
):
    """Verify mutual entailment between constraints and eq_constraints."""
    for premises, clauses in (
        (constraints, eq_constraints),
        (eq_constraints, constraints),
    ):
        for clause in clauses:
            ce = _find_satisfying_assignment(
                variables, list(premises) + ["Not(%s)" % clause]
            )
            if ce is not None:
                return {
                    "status": "REFUTED",
                    "engine": engine_name,
                    "model": model,
                    "refuted_equivalence": clause,
                    "counterexample": ce,
                    "unconstrained_variables": unconstrained,
                    "constraints_count": len(constraints),
                }
    return None


def _normalize_str_list(val):
    """Normalize a string or list of strings into a list of strings."""
    if isinstance(val, str):
        return [val] if val.strip() else []
    return list(val) if isinstance(val, list) else []


def _collect_sm_exprs(spec):
    """Collect all constraint and property expression strings from state_machine."""
    sm = spec.get("state_machine")
    if not isinstance(sm, dict):
        return []
    return (
        _normalize_str_list(sm.get("init"))
        + _normalize_str_list(sm.get("transitions"))
        + _normalize_str_list(sm.get("invariants"))
        + _normalize_str_list(sm.get("terminal"))
        + _normalize_str_list(sm.get("liveness"))
    )


def _collect_all_spec_exprs(spec):
    """Collect all expression strings across constraints, invariants, equivalence, must_refute, and state_machine."""
    return (
        list(spec.get("constraints", []))
        + list(spec.get("invariants", []))
        + list(spec.get("equivalence_constraints", []))
        + _normalize_str_list(spec.get("must_refute"))
        + _collect_sm_exprs(spec)
    )


def _check_must_refute(
    spec, variables, constraints, engine_name, model, unconstrained
):
    """Verify every fault expression in must_refute is falsified by at least one valid state."""
    if "must_refute" not in spec:
        return None
    faults = spec.get("must_refute")
    if not isinstance(faults, list) or not faults:
        return {
            "status": "VACUOUS",
            "engine": engine_name,
            "model": model,
            "vacuous_invariant": "",
            "vacuous_reason": "unfalsified_fault_mutation",
            "unconstrained_variables": unconstrained,
            "constraints_count": len(constraints),
        }
    base_clauses = list(constraints) + list(spec.get("invariants", []))
    for fault in faults:
        ce = _find_satisfying_assignment(
            variables, base_clauses + ["Not(%s)" % fault]
        )
        if ce is None:
            return {
                "status": "VACUOUS",
                "engine": engine_name,
                "model": model,
                "vacuous_invariant": fault,
                "vacuous_reason": "unfalsified_fault_mutation",
                "unconstrained_variables": unconstrained,
                "constraints_count": len(constraints),
            }
    return None


def _partition_sm_constraints(constraints, state_set, sm):
    """Partition constraints into state-only clauses and relational step clauses."""
    state_only = []
    step_clauses = []
    for clause in constraints:
        if _extract_referenced_vars([clause]).issubset(state_set):
            state_only.append(clause)
        else:
            step_clauses.append(clause)
    step_clauses.extend(_normalize_str_list(sm.get("transitions")))
    return state_only, step_clauses


def _enumerate_tuples(variables, var_names):
    """Return Cartesian product tuples over domains of var_names."""
    if not var_names:
        return [()]
    return list(itertools.product(*(variables[v] for v in var_names)))


def _find_initial_states(variables, state_vars, clauses):
    """Return list of state tuples over state_vars satisfying clauses."""
    out = []
    for s in _enumerate_tuples(variables, state_vars):
        if _all_constraints_hold(clauses, dict(zip(state_vars, s))):
            out.append(s)
    return out


def _step_enabled(base_env, next_env, action_vars, action_tuples, step_clauses):
    """Return True if any action assignment satisfies step_clauses for (base_env, next_env)."""
    env = dict(base_env)
    env.update(next_env)
    for act_vals in action_tuples:
        env.update(zip(action_vars, act_vals))
        if _all_constraints_hold(step_clauses, env):
            return True
    return False


def _find_outgoing_states(
    s, state_vars, next_vars, action_vars, action_tuples, valid_states, step_clauses
):
    """Return list of next state tuples reachable in one transition from state tuple s."""
    if not step_clauses:
        return []
    base_env = dict(zip(state_vars, s))
    succs = []
    for next_s in valid_states:
        next_env = dict(zip(next_vars, next_s))
        if _step_enabled(
            base_env, next_env, action_vars, action_tuples, step_clauses
        ):
            succs.append(next_s)
    return succs


def _explore_state_graph(
    init_states,
    state_vars,
    next_vars,
    action_vars,
    action_tuples,
    valid_states,
    step_clauses,
):
    """Explore reachable states via bounded iterative BFS using collections.deque."""
    parent = {s0: None for s0 in init_states}
    queue = deque(init_states)
    reachable = list(init_states)
    adj = {}
    total_transitions = 0
    while queue:
        s = queue.popleft()
        succs = _find_outgoing_states(
            s,
            state_vars,
            next_vars,
            action_vars,
            action_tuples,
            valid_states,
            step_clauses,
        )
        adj[s] = succs
        total_transitions += len(succs)
        for nxt in succs:
            if nxt not in parent and len(reachable) < _MAX_TEMPORAL_STATES:
                parent[nxt] = s
                reachable.append(nxt)
                queue.append(nxt)
    return reachable, adj, parent, total_transitions


def _reconstruct_trace(parent, target_s, state_vars):
    """Reconstruct shortest-path state dict trace from an initial state to target_s."""
    path = []
    curr = target_s
    while curr is not None:
        path.append(dict(zip(state_vars, curr)))
        curr = parent.get(curr)
    path.reverse()
    return path


def _check_sm_safety(reachable, parent, state_vars, sm_invariants):
    """Verify all state_machine invariants hold on every reachable state."""
    for s in reachable:
        env = dict(zip(state_vars, s))
        for inv in sm_invariants:
            if not _eval_expr(inv, env):
                return inv, _reconstruct_trace(parent, s, state_vars)
    return None, None


def _check_sm_deadlock(reachable, adj, parent, state_vars, terminal_expr):
    """Verify every 0-outdegree reachable state satisfies terminal_expr."""
    for s in reachable:
        if adj.get(s):
            continue
        env = dict(zip(state_vars, s))
        if not terminal_expr or not _eval_expr(terminal_expr, env):
            return _reconstruct_trace(parent, s, state_vars)
    return None


def _build_non_goal_adj(reachable, adj, state_vars, goal_expr):
    """Build adjacency list restricted to reachable states where goal_expr is False."""
    non_goal = [
        s
        for s in reachable
        if not _eval_expr(goal_expr, dict(zip(state_vars, s)))
    ]
    ng_set = set(non_goal)
    return {
        s: [nxt for nxt in adj.get(s, []) if nxt in ng_set] for s in non_goal
    }


def _find_non_goal_cycle(start_s, ng_adj, state_vars):
    """Return cycle trace from start_s back to start_s within ng_adj, or None."""
    cycle_parent = {}
    queue = deque()
    for nxt in ng_adj.get(start_s, []):
        cycle_parent[nxt] = None
        queue.append(nxt)
    while queue:
        curr = queue.popleft()
        if curr == start_s:
            return _reconstruct_trace(cycle_parent, start_s, state_vars)
        for nxt in ng_adj.get(curr, []):
            if nxt not in cycle_parent:
                cycle_parent[nxt] = curr
                queue.append(nxt)
    return None


def _check_single_liveness_goal(reachable, adj, parent, state_vars, goal_expr):
    """Verify a single liveness goal holds along all paths; return trace on violation."""
    ng_adj = _build_non_goal_adj(reachable, adj, state_vars, goal_expr)
    for s in ng_adj:
        if not adj.get(s):
            return _reconstruct_trace(parent, s, state_vars)
        cycle = _find_non_goal_cycle(s, ng_adj, state_vars)
        if cycle is not None:
            return _reconstruct_trace(parent, s, state_vars) + cycle
    return None


def _check_sm_liveness(reachable, adj, parent, state_vars, liveness_exprs):
    """Verify all liveness goal expressions hold; return (goal, trace) on failure."""
    for goal in liveness_exprs:
        trace = _check_single_liveness_goal(
            reachable, adj, parent, state_vars, goal
        )
        if trace is not None:
            return goal, trace
    return None, None


def _build_temporal_refuted(
    engine_name, model, unconstrained, constraints, violation, inv, trace
):
    """Construct a REFUTED result dictionary for a state_machine temporal violation."""
    return {
        "status": "REFUTED",
        "engine": engine_name,
        "model": model,
        "temporal_violation": violation,
        "refuted_invariant": inv,
        "counterexample_trace": trace,
        "unconstrained_variables": unconstrained,
        "constraints_count": len(constraints),
    }


def _verify_temporal_pillars(
    sm,
    reachable,
    adj,
    parent,
    state_vars,
    engine_name,
    model,
    unconstrained,
    constraints,
):
    """Verify Safety, Deadlock Freedom, and Liveness on the reachable state graph."""
    inv_fail, trace = _check_sm_safety(
        reachable, parent, state_vars, _normalize_str_list(sm.get("invariants"))
    )
    if inv_fail is not None:
        return _build_temporal_refuted(
            engine_name,
            model,
            unconstrained,
            constraints,
            "SAFETY_VIOLATION",
            inv_fail,
            trace,
        )
    term_list = _normalize_str_list(sm.get("terminal"))
    dl_trace = _check_sm_deadlock(
        reachable, adj, parent, state_vars, term_list[0] if term_list else ""
    )
    if dl_trace is not None:
        return _build_temporal_refuted(
            engine_name,
            model,
            unconstrained,
            constraints,
            "DEADLOCK",
            "deadlock_freedom",
            dl_trace,
        )
    live_fail, l_trace = _check_sm_liveness(
        reachable, adj, parent, state_vars, _normalize_str_list(sm.get("liveness"))
    )
    if live_fail is not None:
        return _build_temporal_refuted(
            engine_name,
            model,
            unconstrained,
            constraints,
            "LIVENESS_VIOLATION",
            live_fail,
            l_trace,
        )
    return None


def _prepare_sm_domains(variables, constraints, sm):
    """Extract state, next, and action variable lists and constraint partitions."""
    state_vars = list(sm.get("state_vars", []))
    next_vars = ["next_" + v for v in state_vars]
    excluded = set(state_vars) | set(next_vars)
    action_vars = [v for v in variables if v not in excluded]
    state_only, step_clauses = _partition_sm_constraints(
        constraints, set(state_vars), sm
    )
    return state_vars, next_vars, action_vars, state_only, step_clauses


def _check_state_machine(
    spec, variables, constraints, engine_name, model, unconstrained
):
    """Run TLA+-style reachable-state verification when state_machine is present."""
    sm = spec.get("state_machine")
    if not isinstance(sm, dict):
        return None, 0, 0
    state_vars, next_vars, action_vars, state_only, step_clauses = (
        _prepare_sm_domains(variables, constraints, sm)
    )
    init_clauses = state_only + _normalize_str_list(sm.get("init"))
    init_states = _find_initial_states(variables, state_vars, init_clauses)
    if not state_vars or not init_states:
        return (
            {
                "status": "UNSAT",
                "engine": engine_name,
                "model": None,
                "unsat_reason": "empty_initial_states",
                "unconstrained_variables": unconstrained,
                "constraints_count": len(constraints),
            },
            0,
            0,
        )
    valid_states = _find_initial_states(variables, state_vars, state_only)
    action_tuples = _enumerate_tuples(variables, action_vars)
    reachable, adj, parent, total_tx = _explore_state_graph(
        init_states,
        state_vars,
        next_vars,
        action_vars,
        action_tuples,
        valid_states,
        step_clauses,
    )
    if total_tx == 0:
        return (
            {
                "status": "VACUOUS",
                "engine": engine_name,
                "model": model,
                "vacuous_reason": "zero_transitions_explored",
                "unconstrained_variables": unconstrained,
                "constraints_count": len(constraints),
            },
            0,
            0,
        )
    failure = _verify_temporal_pillars(
        sm,
        reachable,
        adj,
        parent,
        state_vars,
        engine_name,
        model,
        unconstrained,
        constraints,
    )
    return failure, len(reachable), total_tx


def _compute_proof_certificate(spec, engine_name, model):
    """Return deterministic SHA-256 hex digest over spec, engine, and model."""
    payload = {
        "engine": engine_name,
        "model": model,
        "constraints": list(spec.get("constraints", [])),
        "invariants": list(spec.get("invariants", [])),
        "equivalence_constraints": list(
            spec.get("equivalence_constraints", [])
        ),
    }
    for opt_key in ("program_target", "state_machine", "must_refute"):
        if opt_key in spec:
            payload[opt_key] = spec[opt_key]
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _attach_sat_extensions(out, spec, reach_cnt, tx_cnt):
    """Attach equivalence, must_refute, and state_machine verification metadata to SAT output."""
    if spec.get("equivalence_constraints"):
        out["equivalence_verified"] = True
    if "must_refute" in spec:
        out["must_refute"] = list(spec["must_refute"])
        out["must_refute_verified"] = True
    if isinstance(spec.get("state_machine"), dict):
        out["state_machine"] = spec["state_machine"]
        out["temporal_verified"] = True
        out["reachable_states_count"] = reach_cnt
        out["transitions_explored_count"] = tx_cnt
    return out


def _finalize_sat_result(
    spec, engine_name, variables, constraints, model, unconstrained
):
    """Check equivalence, must_refute, and state_machine, then build SAT receipt."""
    eq_constraints = spec.get("equivalence_constraints", [])
    if eq_constraints:
        eq_fail = _check_clause_equivalence(
            variables,
            constraints,
            eq_constraints,
            engine_name,
            model,
            unconstrained,
        )
        if eq_fail is not None:
            return eq_fail
    mr_fail = _check_must_refute(
        spec, variables, constraints, engine_name, model, unconstrained
    )
    if mr_fail is not None:
        return mr_fail
    sm_fail, reach_cnt, tx_cnt = _check_state_machine(
        spec, variables, constraints, engine_name, model, unconstrained
    )
    if sm_fail is not None:
        return sm_fail
    out = {
        "status": "SAT",
        "engine": engine_name,
        "model": model,
        "unconstrained_variables": unconstrained,
        "constraints_count": len(constraints),
        "proof_certificate_sha256": _compute_proof_certificate(
            spec, engine_name, model
        ),
    }
    return _attach_sat_extensions(out, spec, reach_cnt, tx_cnt)


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
    if _is_domain_tautology(inv, variables, constraints):
        return {
            "status": "VACUOUS",
            "engine": "stdlib-finite-domain",
            "model": model,
            "vacuous_invariant": inv,
            "vacuous_reason": "domain_tautology",
            "unconstrained_variables": unconstrained,
            "constraints_count": len(constraints),
        }
    return None


def solve_finite_domain(spec):
    """Solve a finite-domain constraint specification deterministically with refutation and vacuity checks."""
    variables = spec.get("variables", {})
    constraints = spec.get("constraints", [])
    invariants = spec.get("invariants", [])
    referenced = _extract_referenced_vars(_collect_all_spec_exprs(spec))
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

    return _finalize_sat_result(
        spec, "stdlib-finite-domain", variables, constraints, model, unconstrained
    )


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


def _eval_z3_ifexp(node, env, z3_mod):
    """Evaluate an IfExp AST node into a Z3 If expression."""
    return z3_mod.If(
        _eval_z3_ast_node(node.test, env, z3_mod),
        _eval_z3_ast_node(node.body, env, z3_mod),
        _eval_z3_ast_node(node.orelse, env, z3_mod),
    )


_Z3_AST_DISPATCH = {
    ast.Constant: lambda node, env, z3_mod: node.value,
    ast.Name: lambda node, env, z3_mod: _eval_z3_name(node, env),
    ast.IfExp: _eval_z3_ifexp,
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


def _check_z3_invariant(
    inv, variables, constraints, solver, env, z3_vars, z3_mod, model_dict, unconstrained
):
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
            "constraints_count": len(constraints),
        }
    solver.pop()
    antecedent = _extract_implies_antecedent(inv)
    if antecedent is None:
        if _is_domain_tautology(inv, variables, constraints):
            return {
                "status": "VACUOUS",
                "engine": "z3-solver",
                "model": model_dict,
                "vacuous_invariant": inv,
                "vacuous_reason": "domain_tautology",
                "unconstrained_variables": unconstrained,
                "constraints_count": len(constraints),
            }
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
            "constraints_count": len(constraints),
        }
    return None


def _solve_with_z3(spec, z3_mod):
    """Solve constraint specification using the Z3 solver module."""
    variables = spec.get("variables", {})
    constraints = spec.get("constraints", [])
    invariants = spec.get("invariants", [])
    referenced = _extract_referenced_vars(_collect_all_spec_exprs(spec))
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
            inv, variables, constraints, solver, env, z3_vars, z3_mod, model_dict, unconstrained
        )
        if failure is not None:
            return failure
    return _finalize_sat_result(
        spec, "z3-solver", variables, constraints, model_dict, unconstrained
    )


def compute_function_ast_sha256(func_node):
    """Compute canonical SHA-256 hex digest of an ast.FunctionDef node."""
    raw = ast.dump(func_node, include_attributes=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _check_vcgen_func_signature(func_node):
    """Reject decorators and variadic arguments on a VCGen target function."""
    has_varargs = bool(func_node.args.vararg or func_node.args.kwarg)
    if func_node.decorator_list or has_varargs:
        raise ValueError("VCGen target forbids decorators and *args/**kwargs")


def _is_valid_vcgen_node(node, func_name):
    """Return True if node is allowed inside a VCGen target function."""
    if isinstance(node, _SAFE_FUNC_AST_TYPES):
        return True
    if isinstance(node, ast.Call) and _is_safe_call_node(node):
        return node.func.id != func_name
    return False


def _validate_vcgen_func_ast(func_node):
    """Ensure a FunctionDef AST contains only safe closed-set VCGen nodes."""
    _check_vcgen_func_signature(func_node)
    for node in ast.walk(func_node):
        if not _is_valid_vcgen_node(node, func_node.name):
            raise ValueError(
                "Unsafe AST node in VCGen function: %s" % type(node).__name__
            )


class _SymSubstTransformer(ast.NodeTransformer):
    """Substitute bound local variable ast.Name loads from sym_env."""

    def __init__(self, sym_env):
        self.sym_env = sym_env

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load) and node.id in self.sym_env:
            return ast.parse(ast.unparse(self.sym_env[node.id]), mode="eval").body
        return node


def _subst_ast_names(node, sym_env):
    """Return a fresh expression AST with bound local variables substituted."""
    cloned = ast.parse(ast.unparse(node), mode="eval").body
    return _SymSubstTransformer(sym_env).visit(cloned)


def _extract_assign_pair(stmt):
    """Extract (target_node, value_expr) from Assign, AnnAssign, or AugAssign."""
    if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
        return stmt.targets[0], stmt.value
    if isinstance(stmt, ast.AnnAssign):
        return stmt.target, stmt.value
    if isinstance(stmt, ast.AugAssign) and isinstance(stmt.target, ast.Name):
        lhs = ast.Name(id=stmt.target.id, ctx=ast.Load())
        return stmt.target, ast.BinOp(left=lhs, op=stmt.op, right=stmt.value)
    return None, None


def _lower_assign_stmt(stmt, sym_env):
    """Symbolic-execute an assignment statement and update sym_env in place."""
    target, val_node = _extract_assign_pair(stmt)
    if not isinstance(target, ast.Name) or val_node is None:
        raise ValueError("Unsupported VCGen assignment: %s" % type(stmt).__name__)
    sym_env[target.id] = _subst_ast_names(val_node, sym_env)


def _lower_assert_stmt(stmt, sym_env, path_guards, asserts_out):
    """Lower an ast.Assert statement into a path-guarded invariant string."""
    cond_str = ast.unparse(_subst_ast_names(stmt.test, sym_env))
    if not path_guards:
        asserts_out.append(cond_str)
        return
    guard_expr = (
        path_guards[0]
        if len(path_guards) == 1
        else "And(%s)" % ", ".join(path_guards)
    )
    asserts_out.append("Implies(%s, %s)" % (guard_expr, cond_str))


def _lower_return_stmt(stmt, sym_env):
    """Lower an ast.Return statement into a substituted expression AST."""
    if stmt.value is None:
        raise ValueError("VCGen return statement must return a value")
    return _subst_ast_names(stmt.value, sym_env)


def _is_ignorable_stmt(stmt):
    """Return True if stmt is Pass or a constant docstring Expr."""
    if isinstance(stmt, ast.Pass):
        return True
    return isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant)


def _lower_if_stmt(stmt, rest_stmts, sym_env, path_guards, asserts_out):
    """Lower an ast.If statement by continuation-passing over both branches."""
    cond_ast = _subst_ast_names(stmt.test, sym_env)
    cond_str = ast.unparse(cond_ast)
    then_stmts = list(stmt.body) + list(rest_stmts)
    else_stmts = list(stmt.orelse) + list(rest_stmts)
    then_expr = _lower_stmt_block(
        then_stmts,
        dict(sym_env),
        path_guards + ["(%s)" % cond_str],
        asserts_out,
    )
    else_expr = _lower_stmt_block(
        else_stmts,
        dict(sym_env),
        path_guards + ["Not(%s)" % cond_str],
        asserts_out,
    )
    return ast.IfExp(test=cond_ast, body=then_expr, orelse=else_expr)


def _lower_stmt_block(stmts, sym_env, path_guards, asserts_out):
    """Lower a sequence of statements into a symbolic return expression AST."""
    for idx, stmt in enumerate(stmts):
        if _is_ignorable_stmt(stmt):
            continue
        if isinstance(stmt, ast.Return):
            return _lower_return_stmt(stmt, sym_env)
        if isinstance(stmt, ast.If):
            return _lower_if_stmt(
                stmt, stmts[idx + 1 :], sym_env, path_guards, asserts_out
            )
        if isinstance(stmt, ast.Assert):
            _lower_assert_stmt(stmt, sym_env, path_guards, asserts_out)
        else:
            _lower_assign_stmt(stmt, sym_env)
    raise ValueError("VCGen function path missing explicit return statement")


def _resolve_vcgen_file(raw_file, repo_root=None):
    """Resolve a VCGen target Python file path, enforcing repo_root containment when given."""
    candidate = Path(str(raw_file).strip())
    if repo_root is None:
        return candidate.resolve(strict=True)
    root_res = Path(repo_root).resolve()
    if not candidate.is_absolute():
        candidate = root_res / candidate
    resolved = candidate.resolve(strict=True)
    resolved.relative_to(root_res)
    return resolved


def _find_function_def(tree, func_name):
    """Locate an ast.FunctionDef node by name."""
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            return node
    raise ValueError("VCGen target function not found: %r" % func_name)


def _compile_program_target_spec(spec, repo_root=None):
    """Compile program_target Python AST into formal constraints and invariants."""
    prog = spec.get("program_target")
    if not isinstance(prog, dict):
        return dict(spec)
    target_path = _resolve_vcgen_file(prog.get("file", ""), repo_root=repo_root)
    func_name = str(prog.get("function", "")).strip()
    result_var = str(prog.get("result_var", "result")).strip() or "result"
    tree = ast.parse(target_path.read_text(encoding="utf-8"))
    func_node = _find_function_def(tree, func_name)
    _validate_vcgen_func_ast(func_node)
    fn_sha = compute_function_ast_sha256(func_node)
    sym_env = {
        arg.arg: ast.Name(id=arg.arg, ctx=ast.Load())
        for arg in func_node.args.args
    }
    asserts_out = []
    ret_ast = _lower_stmt_block(func_node.body, sym_env, [], asserts_out)
    lowered_str = ast.unparse(ret_ast)
    compiled = dict(spec)
    compiled["constraints"] = (
        list(spec.get("constraints", []))
        + list(prog.get("preconditions", []))
        + ["%s == (%s)" % (result_var, lowered_str)]
    )
    compiled["invariants"] = (
        list(spec.get("invariants", []))
        + asserts_out
        + list(prog.get("postconditions", []))
    )
    compiled["function_ast_sha256"] = fn_sha
    compiled["program_target"] = {
        "file": str(prog.get("file", "")),
        "function": func_name,
        "result_var": result_var,
        "function_ast_sha256": fn_sha,
        "lowered_return_expr": lowered_str,
    }
    return compiled


def _attach_program_target_metadata(result, compiled_spec):
    """Attach program_target and function_ast_sha256 metadata to solver result when present."""
    if "program_target" in compiled_spec:
        result["program_target"] = compiled_spec["program_target"]
        result["function_ast_sha256"] = compiled_spec["function_ast_sha256"]
    return result


def solve_spec(spec):
    """Solve constraint spec using z3 if available, otherwise stdlib fallback."""
    compiled = _compile_program_target_spec(spec)
    for expr in _collect_all_spec_exprs(compiled):
        _validate_safe_ast(ast.parse(expr, mode="eval"))
    try:
        import z3  # type: ignore

        res = _solve_with_z3(compiled, z3)
    except Exception:
        res = solve_finite_domain(compiled)
    return _attach_program_target_metadata(res, compiled)


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
    return _check_pcv_tautology_and_equivalence_cases()


def _check_pcv_tautology_and_equivalence_cases():
    """Verify domain_tautology vacuity, equivalence_constraints, and proof_certificate_sha256."""
    taut_res = solve_spec(
        {
            "variables": {"x": [1, 2]},
            "constraints": ["x == 1"],
            "invariants": ["x >= 1"],
        }
    )
    if (taut_res.get("status"), taut_res.get("vacuous_reason")) != (
        "VACUOUS",
        "domain_tautology",
    ):
        print("Self-test domain_tautology failed: %r" % (taut_res,))
        return False
    eq_ok = solve_spec(
        {
            "variables": {"x": [1, 2, 3], "y": [1, 2, 3]},
            "constraints": ["x < y", "y <= 2"],
            "equivalence_constraints": ["x == 1", "y == 2"],
        }
    )
    if (
        eq_ok.get("status"),
        eq_ok.get("equivalence_verified"),
        len(eq_ok.get("proof_certificate_sha256", "")),
    ) != ("SAT", True, 64):
        print("Self-test equivalence SAT failed: %r" % (eq_ok,))
        return False
    eq_bad = solve_spec(
        {
            "variables": {"x": [1, 2, 3], "y": [1, 2, 3]},
            "constraints": ["x < y"],
            "equivalence_constraints": ["x == 1", "y == 2"],
        }
    )
    if eq_bad.get("status") != "REFUTED" or "refuted_equivalence" not in eq_bad:
        print("Self-test equivalence REFUTED failed: %r" % (eq_bad,))
        return False
    return True


def _check_vcgen_program_target_cases():
    """Verify Python AST-to-SMT VCGen SAT and REFUTED cases."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        py_f = Path(tmp) / "vcgen_self_test.py"
        py_f.write_text(
            "def clamp_val(x: int, lo: int, hi: int) -> int:\n"
            "    if x < lo:\n"
            "        return lo\n"
            "    if x > hi:\n"
            "        res = hi\n"
            "    else:\n"
            "        res = x\n"
            "    assert res >= lo\n"
            "    return res\n\n"
            "def buggy_withdraw(balance: int, amt: int) -> int:\n"
            "    return balance + amt\n",
            encoding="utf-8",
        )
        ok_res = solve_spec(
            {
                "variables": {
                    "x": [-1, 1, 3],
                    "lo": [0, 1],
                    "hi": [2],
                    "result": [-1, 0, 1, 2, 3],
                },
                "program_target": {
                    "file": str(py_f),
                    "function": "clamp_val",
                    "result_var": "result",
                    "preconditions": ["lo <= hi"],
                    "postconditions": ["result >= lo", "result <= hi"],
                },
            }
        )
        if ok_res.get("status") != "SAT" or len(ok_res.get("function_ast_sha256", "")) != 64:
            print("Self-test VCGen SAT failed: %r" % (ok_res,))
            return False
        bad_res = solve_spec(
            {
                "variables": {"balance": [10], "amt": [5], "result": [5, 15]},
                "program_target": {
                    "file": str(py_f),
                    "function": "buggy_withdraw",
                    "result_var": "result",
                    "preconditions": ["amt > 0"],
                    "postconditions": ["result == balance - amt"],
                },
            }
        )
        if bad_res.get("status") != "REFUTED":
            print("Self-test VCGen REFUTED failed: %r" % (bad_res,))
            return False
    return True


def _check_temporal_and_must_refute_cases():
    """Verify state_machine temporal properties and must_refute fault falsifiability."""
    sm_ok = solve_spec(
        {
            "variables": {"state": [0, 1, 2], "next_state": [0, 1, 2]},
            "constraints": ["next_state == (state + 1 if state < 2 else 2)"],
            "state_machine": {
                "state_vars": ["state"],
                "init": ["state == 0"],
                "invariants": ["state >= 0 and state <= 2"],
                "terminal": "state == 2",
                "liveness": ["state == 2"],
            },
            "must_refute": ["state == 0"],
        }
    )
    if (
        sm_ok.get("status"),
        sm_ok.get("temporal_verified"),
        sm_ok.get("must_refute_verified"),
    ) != ("SAT", True, True):
        print("Self-test temporal SAT failed: %r" % (sm_ok,))
        return False
    live_bad = solve_spec(
        {
            "variables": {"state": [0, 1], "next_state": [0, 1]},
            "constraints": ["next_state == 1 - state"],
            "state_machine": {
                "state_vars": ["state"],
                "init": ["state == 0"],
                "liveness": "state == 1 and state == 0",
            },
        }
    )
    if live_bad.get("temporal_violation") != "LIVENESS_VIOLATION":
        print("Self-test temporal LIVENESS_VIOLATION failed: %r" % (live_bad,))
        return False
    mr_bad = solve_spec(
        {
            "variables": {"x": [1, 2]},
            "constraints": ["x == 1"],
            "must_refute": ["x >= 1"],
        }
    )
    if mr_bad.get("vacuous_reason") != "unfalsified_fault_mutation":
        print("Self-test must_refute failed: %r" % (mr_bad,))
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
    if not _check_vcgen_program_target_cases():
        return 1
    if not _check_temporal_and_must_refute_cases():
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
