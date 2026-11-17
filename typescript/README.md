# `@slashml/memory` -- TypeScript / Node.js SDK

Official TypeScript & Node.js client and MCP launcher for the **/ ml** Memory Cloud API (`https://api.slashml.ai`).

## Installation

```bash
npm install @slashml/memory
```

Configure your API key in the environment:

```bash
export SLASHML_API_KEY="sml_live_..."
```

## Quickstart (Mem0 Drop-in Replacement)

```typescript
import { Memory } from "@slashml/memory";

const m = new Memory({ apiKey: process.env.SLASHML_API_KEY });

// Add a memory
await m.add("User prefers TypeScript with strict mode enabled", {
  user_id: "alice",
  metadata: { topic: "preferences" },
});

// Search memories
const results = await m.search("What language settings does Alice prefer?", {
  user_id: "alice",
  limit: 5,
});
console.log(results);
```

## Native `/ ml` Memory API (`ingest` / `query` / `forget`)

```typescript
import { MemoryClient } from "@slashml/memory";

const client = new MemoryClient({
  apiKey: process.env.SLASHML_API_KEY,
  model: "slashml-1.5-pro", // or "slashml-1.5-fast"
});

// 1. Ingest documents into a namespace
await client.ingest(
  [
    "Project Atlas uses JWT RS256 tokens signed by the auth-gateway service.",
    "Refresh tokens expire after 7 days and are rotated on every use.",
  ],
  { namespace: "repo:atlas" }
);

// 2. Query the memory store
const answer = await client.query("How are JWT tokens signed and rotated?", {
  namespace: "repo:atlas",
});
console.log(answer);

// 3. Delete a memory
await client.forget("Refresh tokens expire after 7 days", {
  namespace: "repo:atlas",
});
```

## One-Command MCP & Ambient Hook Setup for Coding Agents

Install the `/ ml` MCP server into Cursor, Claude Code, or Windsurf:

```bash
npx -y @slashml/memory@latest --init --skill cursor --api-key "$SLASHML_API_KEY"
```

Install ambient lifecycle hooks (`UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `Stop`) into `~/.claude/settings.json`:

```bash
npx -y @slashml/memory@latest --install-hooks --api-key "$SLASHML_API_KEY"
```

Or evaluate an agent action / prompt programmatically via `client.intervene()`:

```typescript
const decision = await client.intervene("aws ec2 run-instances --placement AvailabilityZone=us-east-1b", {
  hookEventName: "PreToolUse",
  toolName: "Bash",
  userId: "team_infra",
});
```

## Inline Redaction & Per-Agent Read/Write Access Control

```typescript
import { Memory } from "@slashml/memory";

const admin = new Memory({ apiKey: process.env.SLASHML_API_KEY });

// Set workspace redaction defaults & configure a read-only agent policy
await admin.setRedactionPolicy({
  redactPolicy: "tier1_secrets",
  redactScope: "recall_only",
  accessMode: "read_write",
});
await admin.agents.set("support_triage_bot", {
  accessMode: "read_only",
  redactPolicy: "gdpr",
  redactScope: "recall_only",
});

// Scoped agent client attaches X-SlashML-Agent-Id automatically
const triage = new Memory({
  apiKey: process.env.SLASHML_API_KEY,
  agentId: "support_triage_bot",
});
const masked = await triage.redact({ text: "Contact alice@acme.io for billing" });
const hits = await triage.search("Who handles billing?", { userId: "alice" });
```

---

## License

Apache-2.0
