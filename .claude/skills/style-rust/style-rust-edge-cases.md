# Edge Cases & Heuristics: style-rust

- **Explicit Error Propagation Over Unwrap in Library Paths**: Use `?` with structured error types instead of `.unwrap()` or `.expect()` in non-test library functions to prevent runtime panics on invalid inputs.
