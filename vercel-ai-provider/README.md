# `@slashml/vercel-ai-provider` — `/ ml` Memory Provider for the Vercel AI SDK

Official `/ ml` persistent memory integration for the **Vercel AI SDK** (`ai`), and a **100% drop-in replacement for `@mem0/vercel-ai-provider`**.

---

## Installation

```bash
npm install @slashml/vercel-ai-provider ai
```

---

## Quickstart

### 1. Standalone Utilities (`retrieveMemories`, `addMemories`, `getMemories`)

```typescript
import { generateText } from "ai";
import { openai } from "@ai-sdk/openai";
import {
  retrieveMemories,
  addMemories,
  getMemories,
} from "@slashml/vercel-ai-provider";

// 1. Store conversation messages into / ml Memory
await addMemories(
  [
    {
      role: "user",
      content: [{ type: "text", text: "I prefer dark mode and TypeScript strict mode." }],
    },
  ],
  { user_id: "alex" }
);

// 2. Retrieve relevant memories formatted as a system prompt
const systemMemoryPrompt = await retrieveMemories("How should I configure the new repo?", {
  user_id: "alex",
});

const { text } = await generateText({
  model: openai("gpt-4.1"),
  system: systemMemoryPrompt,
  prompt: "How should I configure the new repo?",
});

// 3. Fetch raw memory objects as an array
const rawMemories = await getMemories({ user_id: "alex" });
```

### 2. Unified Provider Wrapper (`createSlashML` / `createMem0`)

```typescript
import { generateText } from "ai";
import { createSlashML, createMem0 } from "@slashml/vercel-ai-provider";

// Initialize the / ml provider (or use `createMem0` as a 1-line drop-in replacement)
const slashml = createSlashML({
  provider: "openai",
  slashmlApiKey: process.env.SLASHML_API_KEY,
  apiKey: process.env.OPENAI_API_KEY,
  slashmlConfig: {
    user_id: "alex",
  },
});

const { text, sources } = await generateText({
  model: slashml("gpt-4.1", { user_id: "alex" }),
  prompt: "What are my coding preferences?",
});
```

---

## License

Apache-2.0
