# `@slashml/memory` — TypeScript / Node.js SDK

Official TypeScript & Node.js client and MCP launcher for the **/ ml** Memory Cloud API (`https://api.slashml.ai`).

## Installation

```bash
npm install @slashml/memory
```

Configure your API key in the environment:

```bash
export SLASHML_API_KEY="ml-live-..."
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

// 3. Exact unlearning / GDPR right-to-be-forgotten
await client.forget("Refresh tokens expire after 7 days", {
  namespace: "repo:atlas",
});
```

## One-Command MCP Setup for Coding Agents

Install the `/ ml` MCP server into Cursor, Claude Code, or Windsurf:

```bash
npx @slashml/memory --init --skill cursor --api-key "$SLASHML_API_KEY"
```
