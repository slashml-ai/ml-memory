# SlashML Public Packages (`slashml-public-packages/`)

This directory contains all **publicly published, open-source (`Apache-2.0`) client packages and developer tools** for **SlashML (`/` `ml`)**.

---

## Directory Layout (Open to Public)

| Directory | Public Package Name | Registry | License | Description |
| :--- | :--- | :--- | :--- | :--- |
| [`python/`](./python) | `slashml` | PyPI | `Apache-2.0` | Python SDK (`SlashMLMemory`, `MemoryClient`, `AsyncMemoryClient`, `Memory`, `AsyncMemory` 100% Mem0 drop-in, LangChain / LangGraph / LlamaIndex / CrewAI adapters, `/ml-memory` MCP server) |
| [`typescript/`](./typescript) | `@slashml/memory` | npm | `Apache-2.0` | Zero-dependency TypeScript/Node.js SDK (`SlashMLMemory`, `MemoryClient`, `AsyncMemoryClient`, `Memory`, `AsyncMemory` 100% Mem0 drop-in) + CLI (`npx @slashml/memory`) |
| [`vercel-ai-provider/`](./vercel-ai-provider) | `@slashml/vercel-ai-provider` | npm | `Apache-2.0` | Vercel AI SDK Provider (`createSlashML`, `createMem0`, `slashml`, `mem0`, `retrieveMemories`, `addMemories`, `getMemories`, `searchMemories`) — drop-in replacement for `@mem0/vercel-ai-provider` |
| [`mcp/`](./mcp) | `@slashml/mcp` | npm | `Apache-2.0` | Standalone local MCP stdio server (`slashml-mcp` and `slashml-mcp-code` for Claude Code, Cursor, Windsurf, Cline, Zed) |
| [`eval/`](./eval) | `slashml-eval` | PyPI | `Apache-2.0` | Public benchmark harness CLI (`slashml-eval`) for LongMemEval, LoCoMo, and ConvoMem via the SlashML Cloud API |
| [`launch/`](./launch) | — | Docs | `Apache-2.0` | Public launch blog post and documentation |
| [`LICENSE`](./LICENSE) | — | Docs | `Apache-2.0` | Apache-2.0 open-source license for the public client packages |

---

## Quick Start

### 1. Python SDK (`pip install slashml`)

```python
from slashml import SlashMLMemory

# Connects to https://api.slashml.ai (or reads SLASHML_API_KEY from env)
memory = SlashMLMemory(api_key="sml_live_...")

memory.add("User prefers dark mode and strict TypeScript.", user_id="u_123")
hits = memory.search("What are the user's coding preferences?", user_id="u_123")
```

### 2. TypeScript SDK (`npm install @slashml/memory`)

```typescript
import { SlashMLMemory } from "@slashml/memory";

const memory = new SlashMLMemory({ apiKey: process.env.SLASHML_API_KEY });
await memory.add("We migrated auth from JWT to session cookies", { userId: "team_backend" });
const results = await memory.search("How does auth work?", { userId: "team_backend" });
```

### 3. Local MCP Server (`npx -y @slashml/mcp`)

```bash
claude mcp add /ml-memory -- env SLASHML_API_KEY=sml_live_xxx npx -y @slashml/mcp
```
