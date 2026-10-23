# Edge Cases & Heuristics: style-java

- **Try-With-Resources for AutoCloseable Streams**: Always wrap `AutoCloseable` I/O streams, database connections, and locks in `try (...)` blocks to guarantee deterministic closure on exceptions.
