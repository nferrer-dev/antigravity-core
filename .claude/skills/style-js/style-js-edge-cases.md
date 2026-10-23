# Edge Cases & Heuristics: style-js

- **Unhandled Promise Rejections in Event Handlers**: Never pass an `async` callback to an event listener or timer without an internal `try/catch` block or `.catch()` handler if the caller ignores the returned Promise.
