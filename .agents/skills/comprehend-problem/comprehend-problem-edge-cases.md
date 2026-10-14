# Edge Cases & Heuristics: comprehend-problem

- When saving formal rubric output (such as JSON graphs or structural mappings) to temporary text files, you MUST explicitly force UTF-8 encoding (e.g., avoiding native PowerShell `>` redirection) to prevent downstream file-reading errors in `view_file`.
