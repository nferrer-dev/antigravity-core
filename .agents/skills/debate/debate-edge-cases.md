# Learned Edge Cases

- **Missing Subagent/Write/MCP Tool Permissions**: When spawning a Sub-Orchestrator to execute a Map-Reduce debate, you MUST first use the `define_subagent` tool to create a new agent type with `enable_subagent_tools=True`, `enable_write_tools=True`, and `enable_mcp_tools=True`. The default `research` subagent type is strictly read-only and will trigger a BLOCKED_STATE when attempting to spawn its own subagents, execute empirical PoCs, or commit arguments to the Cortex MCP server.
