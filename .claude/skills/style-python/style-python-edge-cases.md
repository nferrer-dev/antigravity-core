# Edge Cases & Heuristics: style-python

- **N+1 Query Anti-Pattern**: Avoid executing `SELECT` queries iteratively inside a loop (e.g., `for` loop); consolidate into a single batch query using an `IN` clause.
- **Numerical Anti-Pattern**: Avoid exact floating-point comparisons (e.g., `value == 0.0`); use `math.isclose(value, 0.0)` or `np.isclose(value, 0.0)` instead.
