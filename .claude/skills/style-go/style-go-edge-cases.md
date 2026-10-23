# Edge Cases & Heuristics: style-go

- **Goroutine Context Cancellation**: Always propagate `context.Context` into long-running goroutines or blocking I/O channels to prevent goroutine leaks when a request or parent task is cancelled.
