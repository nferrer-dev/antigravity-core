# Edge Cases & Heuristics: style-cpp

- **RAII Ownership Over Raw Allocation**: Prefer `std::unique_ptr` or stack-allocated value types over raw `new`/`delete` to guarantee exception-safe resource cleanup.
