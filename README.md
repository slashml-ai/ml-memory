# SlashML Memory (`slashml-memory`)

Official **SlashML (`/` `ml`)** plugin, skill, and MCP server for sub-millisecond persistent memory, ambient lifecycle hooks, behavioral code search, and bug localization.

---

## Overview

SlashML provides persistent conversational memory, repository symbol recall, and automatic rule enforcement for AI coding agents:

- **Persistent Memory (`search_memories`, `add_memory`, `get_memories`, `forget_memory`)**: Store and retrieve architectural decisions, user preferences, and standing project rules across sessions.
- **Behavioral Code Search (`search_code_by_behavior`, `index_repository`)**: Locate functions, classes, and modules by runtime or architectural behavior.
- **Bug Localization (`find_bug_candidates`)**: Rank candidate functions and files most likely responsible for a symptom or stack trace.
- **Ambient Lifecycle Hooks (`hooks/hooks.json`)**: Automatically assimilate new standing instructions on `UserPromptSubmit` and check tool calls against active rules on `PreToolUse`, `PostToolUse`, and `Stop`.

---

## Configuration

Install directly in Claude Code:

```bash
/plugin install slashml-memory --marketplace slashml-ai/ml-memory
```

When installing the plugin in Claude Code, provide your SlashML API key (`sml_live_...` from [https://app.slashml.ai](https://app.slashml.ai)) when prompted for the `api_key` plugin option.

---

## Python & TypeScript SDK Usage

### Python (`slashml-memory`)

```python
from slashml import SlashMLMemory

memory = SlashMLMemory(api_key="sml_live_...")
memory.add("User prefers dark mode and strict TypeScript.", user_id="u_123")
hits = memory.search("What are the user's coding preferences?", user_id="u_123")
```

### TypeScript (`@slashml/memory`)

```typescript
import { SlashMLMemory } from "@slashml/memory";

const memory = new SlashMLMemory({ apiKey: "sml_live_..." });
await memory.add("We migrated auth from JWT to session cookies", { userId: "team_backend" });
const results = await memory.search("How does auth work?", { userId: "team_backend" });
```

---

## License

Apache-2.0. See [`LICENSE`](./LICENSE) for details.

<!-- mcp-name: io.github.slashml-ai/ml-memory -->
