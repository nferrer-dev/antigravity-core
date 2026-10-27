# Edge Cases & Heuristics: style-js

- **Unhandled Promise Rejections in Event Handlers**: Never pass an `async` callback to an event listener or timer without an internal `try/catch` block or `.catch()` handler if the caller ignores the returned Promise.
- **Dual DTO & Raw Nullable Payload Signatures (`strictNullChecks`)**: Type normalizer and helper parameters that accept both typed DTOs and raw nullable API/SQLite records as `Partial<Record<keyof T, unknown>>` rather than `Partial<T>`, and guard `null`/`undefined`/boolean/empty-string inputs before calling `Number(val)` so `Number(null)` never silently coerces to `0`.
