# `@slashml/mcp` — SlashML MCP Server

Official Model Context Protocol (MCP) server for **SlashML (`/` `ml`)**. Connects coding and chat agents to the SlashML Cloud API (`https://api.slashml.ai`).

## Quick Install

### Claude Code (1-liner)
```bash
claude mcp add --scope user ml-memory -- env SLASHML_API_KEY=sml_live_xxx npx -y @slashml/mcp
```

### Cursor / Claude Desktop / Windsurf (`mcp.json`)
```json
{
  "mcpServers": {
    "ml-memory": {
      "command": "npx",
      "args": ["-y", "@slashml/mcp"],
      "env": {
        "SLASHML_API_KEY": "sml_live_xxx"
      }
    }
  }
}
```

### Code Mode (91% Token Savings)
Expose a single `execute_memory_code` meta-tool instead of all 7 tool schemas:
```bash
claude mcp add --scope user ml-memory-code -- env SLASHML_API_KEY=sml_live_xxx npx -y @slashml/mcp --code-mode
```

## Available Tools (Standard Mode)
1. `add_memory` — Add a persistent memory with temporal extraction.
2. `search_memories` — Search memories via hybrid retrieval.
3. `get_memories` — List all memories for a user/agent scope.
4. `forget_memory` — Delete a specific memory by ID.
5. `index_repository` — Index a git repository for AST-aware code search.
6. `search_code_by_behavior` — Search code symbols by behavioral description.
7. `find_bug_candidates` — Rank likely bug locations from symptoms and stack traces.

## License
Apache-2.0. Connects to the SlashML Cloud Service (`https://api.slashml.ai`).
