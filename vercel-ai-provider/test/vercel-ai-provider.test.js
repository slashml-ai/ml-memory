const test = require("node:test");
const assert = require("node:assert/strict");
const http = require("node:http");
const { performance } = require("node:perf_hooks");

const {
  createSlashML,
  createMem0,
  slashml,
  mem0,
  retrieveMemories,
  addMemories,
  getMemories,
  searchMemories,
  normalizePromptToQuery,
  normalizeMessages,
  SlashMLAILanguageModel,
  Mem0AILanguageModel,
  DEFAULT_BASE_URL,
  DEFAULT_SYSTEM_PREFIX,
} = require("../dist/index.js");

function createStatefulMockServer() {
  return new Promise((resolve) => {
    const store = [];
    const requests = [];
    let transientFailRemaining = 0;
    let transientStatus = 503;

    const server = http.createServer((req, res) => {
      let body = "";
      req.on("data", (chunk) => {
        body += chunk;
      });
      req.on("end", () => {
        let parsed = null;
        if (body) {
          try {
            parsed = JSON.parse(body);
          } catch {
            parsed = body;
          }
        }
        requests.push({
          method: req.method,
          url: req.url,
          headers: req.headers,
          body: parsed,
        });

        const auth = req.headers["authorization"] || req.headers["x-api-key"] || "";
        if (!auth || auth === "Bearer invalid_key") {
          res.writeHead(401, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ error: "Unauthorized API key" }));
          return;
        }

        if (transientFailRemaining > 0) {
          transientFailRemaining -= 1;
          res.writeHead(transientStatus, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ error: `Transient ${transientStatus}` }));
          return;
        }

        const parsedUrl = new URL(req.url, "http://127.0.0.1");

        if (req.method === "POST" && parsedUrl.pathname === "/v1/memories") {
          if (parsed && parsed.metadata && parsed.metadata.trigger_400) {
            res.writeHead(400, { "Content-Type": "application/json" });
            res.end(JSON.stringify({ detail: "Invalid metadata schema" }));
            return;
          }
          const msgText = Array.isArray(parsed?.messages)
            ? parsed.messages.map((m) => m.content).join(" | ")
            : String(parsed?.messages || "");
          const rec = {
            id: `mem_${store.length + 1}`,
            memory: msgText,
            user_id: parsed?.user_id ?? null,
            agent_id: parsed?.agent_id ?? null,
            app_id: parsed?.app_id ?? null,
            run_id: parsed?.run_id ?? null,
            metadata: parsed?.metadata ?? {},
            score: 0.96,
          };
          store.push(rec);
          res.writeHead(200, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ results: [rec] }));
          return;
        }

        if (req.method === "POST" && parsedUrl.pathname === "/v1/memories/search") {
          const userId = parsed?.user_id;
          const agentId = parsed?.agent_id;
          const limit = parsed?.top_k ?? parsed?.limit ?? 5;
          let filtered = store;
          if (userId) {
            filtered = filtered.filter((m) => m.user_id === userId);
          }
          if (agentId) {
            filtered = filtered.filter((m) => m.agent_id === agentId);
          }
          res.writeHead(200, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ results: filtered.slice(0, limit) }));
          return;
        }

        if (req.method === "GET" && parsedUrl.pathname === "/v1/memories") {
          const userId = parsedUrl.searchParams.get("user_id");
          const limit = Number(parsedUrl.searchParams.get("limit") || 100);
          let filtered = store;
          if (userId) {
            filtered = filtered.filter((m) => m.user_id === userId);
          }
          res.writeHead(200, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ results: filtered.slice(0, limit) }));
          return;
        }

        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ ok: true }));
      });
    });

    server.listen(0, "127.0.0.1", () => {
      const addr = server.address();
      resolve({
        baseUrl: `http://127.0.0.1:${addr.port}`,
        store,
        requests,
        injectTransientFailures(count, status = 503) {
          transientFailRemaining = count;
          transientStatus = status;
        },
        close: () => new Promise((r) => server.close(r)),
      });
    });
  });
}

test("1. Standalone Functions E2E: addMemories, getMemories (query & list), searchMemories, retrieveMemories", async () => {
  const mock = await createStatefulMockServer();
  try {
    const cfg = {
      slashmlApiKey: "sml_vercel_test",
      baseUrl: mock.baseUrl,
      user_id: "u_vercel_1",
      agentId: "agent_router",
      orgId: "org_acme",
      projectId: "proj_nextjs",
      metadata: { env: "prod" },
    };

    const addRes = await addMemories(
      [
        {
          role: "user",
          content: [{ type: "text", text: "I use Next.js App Router and TypeScript." }],
        },
        {
          role: "assistant",
          content: "Got it, I will use Next.js App Router conventions.",
        },
      ],
      cfg,
    );
    assert.equal(addRes.results.length, 1);
    assert.match(addRes.results[0].memory, /Next\.js App Router/);

    // Verify Org & Project headers on POST /v1/memories
    const lastReq = mock.requests[mock.requests.length - 1];
    assert.equal(lastReq.headers["x-slashml-org-id"], "org_acme");
    assert.equal(lastReq.headers["x-slashml-project-id"], "proj_nextjs");
    assert.equal(lastReq.body.agent_id, "agent_router");

    // Search via getMemories(query, cfg)
    const memories = await getMemories("What framework do I use?", cfg);
    assert.equal(memories.length, 1);
    assert.match(memories[0].memory, /Next\.js App Router/);

    // List all via getMemories(cfg) without query -> GET /v1/memories
    const listed = await getMemories({
      apiKey: "sml_vercel_test",
      baseUrl: mock.baseUrl,
      userId: "u_vercel_1",
      limit: 10,
    });
    assert.equal(listed.length, 1);
    assert.equal(mock.requests[mock.requests.length - 1].method, "GET");

    // Alias searchMemories
    const searched = await searchMemories("Next.js", cfg);
    assert.equal(searched.length, 1);

    // retrieveMemories with default and custom prefix
    const sysPrompt = await retrieveMemories("What framework do I use?", cfg);
    assert.ok(sysPrompt.startsWith(DEFAULT_SYSTEM_PREFIX));
    assert.match(sysPrompt, /- I use Next\.js App Router/);

    const customPrompt = await retrieveMemories("What framework?", {
      ...cfg,
      systemPromptPrefix: "Custom Memory Header:",
    });
    assert.ok(customPrompt.startsWith("Custom Memory Header:\n- "));

    // Empty user returns empty string (no header pollution)
    const emptyPrompt = await retrieveMemories("Anything?", {
      ...cfg,
      user_id: "non_existent_user",
    });
    assert.equal(emptyPrompt, "");
  } finally {
    await mock.close();
  }
});

test("2. LanguageModelV1 Wrapper: doGenerate & doStream isolation, auto-addMemories, provider methods", async () => {
  const mock = await createStatefulMockServer();
  try {
    await addMemories("User prefers Tailwind CSS and dark mode", {
      apiKey: "sml_vercel_lm",
      baseUrl: mock.baseUrl,
      userId: "u_lm",
    });

    let generateCalls = 0;
    let streamCalls = 0;
    let capturedOptions = null;

    const mockUpstreamModel = {
      specificationVersion: "v1",
      provider: "openai.chat",
      modelId: "gpt-4o-mini",
      defaultObjectGenerationMode: "json",
      async doGenerate(options) {
        generateCalls += 1;
        capturedOptions = options;
        return {
          text: "Generated with injected SlashML memory!",
          finishReason: "stop",
          usage: { promptTokens: 25, completionTokens: 10 },
          rawCall: { rawPrompt: options.prompt, rawSettings: {} },
        };
      },
      async doStream(options) {
        streamCalls += 1;
        capturedOptions = options;
        return {
          stream: {
            async *[Symbol.asyncIterator]() {
              yield { type: "text-delta", textDelta: "chunk1" };
              yield { type: "text-delta", textDelta: "chunk2" };
              yield { type: "finish", finishReason: "stop" };
            },
          },
          rawCall: { rawPrompt: options.prompt, rawSettings: {} },
        };
      },
    };

    const provider = createMem0({
      mem0ApiKey: "sml_vercel_lm",
      baseUrl: mock.baseUrl,
      user_id: "u_lm",
      addMemories: true,
    });

    // Test provider(), provider.languageModel(), provider.chat(), provider.completion()
    const m1 = provider("gpt-4o-mini", { upstreamModel: mockUpstreamModel });
    const m2 = provider.languageModel("gpt-4o-mini", { upstreamModel: mockUpstreamModel });
    const m3 = provider.chat("gpt-4o-mini", { upstreamModel: mockUpstreamModel });
    const m4 = provider.completion("gpt-4o-mini", { upstreamModel: mockUpstreamModel });
    assert.ok(m1 instanceof SlashMLAILanguageModel);
    assert.ok(m2 instanceof Mem0AILanguageModel);
    assert.equal(m3.modelId, "gpt-4o-mini");
    assert.equal(m4.provider, "slashml.openai");

    // 1) doGenerate should ONLY call upstreamModel.doGenerate (and auto-ingest memory since addMemories: true)
    const storeBeforeGen = mock.store.length;
    const genRes = await m1.doGenerate({
      inputFormat: "messages",
      mode: { type: "regular" },
      prompt: [
        { role: "system", content: "You are a helpful coding assistant." },
        { role: "user", content: [{ type: "text", text: "Style my button component" }] },
      ],
    });
    assert.equal(generateCalls, 1);
    assert.equal(streamCalls, 0);
    assert.equal(mock.store.length, storeBeforeGen + 1);
    assert.equal(genRes.text, "Generated with injected SlashML memory!");
    assert.equal(genRes.sources.length, 1);
    assert.equal(genRes.providerMetadata.slashml.memories.length, 1);
    assert.match(capturedOptions.prompt[0].content, /Tailwind CSS and dark mode/);

    // 2) doStream MUST NOT call upstreamModel.doGenerate — only upstreamModel.doStream!
    const streamRes = await m1.doStream({
      inputFormat: "messages",
      mode: { type: "regular" },
      prompt: [{ role: "user", content: [{ type: "text", text: "Stream me a navbar" }] }],
    });
    assert.equal(generateCalls, 1, "doStream must not invoke upstreamModel.doGenerate");
    assert.equal(streamCalls, 1, "doStream must invoke upstreamModel.doStream once");
    assert.ok(streamRes.sources.length >= 1);
    assert.ok(streamRes.providerMetadata.slashml.systemMemory.includes("Tailwind CSS"));

    const collectedChunks = [];
    for await (const chunk of streamRes.stream) {
      collectedChunks.push(chunk);
    }
    assert.equal(collectedChunks.length, 3);
    assert.equal(collectedChunks[0].textDelta, "chunk1");

    // 3) Standalone fallback (no upstreamModel provided) for both doGenerate and doStream
    const standaloneModel = createSlashML({
      slashmlApiKey: "sml_vercel_lm",
      baseUrl: mock.baseUrl,
      userId: "u_lm",
    })("claude-3-7-sonnet");

    const fallbackGen = await standaloneModel.doGenerate({
      prompt: "Build a card component",
    });
    assert.match(fallbackGen.text, /\[Memory-Augmented Response \(claude-3-7-sonnet\)\]/);

    const fallbackStream = await standaloneModel.doStream({
      prompt: "Build a modal component",
    });
    const fbChunks = [];
    for await (const ch of fallbackStream.stream) {
      fbChunks.push(ch);
    }
    assert.equal(fbChunks.length, 2);
    assert.equal(fbChunks[0].type, "text-delta");
    assert.match(fbChunks[0].textDelta, /Tailwind CSS/);
  } finally {
    await mock.close();
  }
});

test("3. Prompt & Message Normalization Edge Cases", async () => {
  assert.equal(normalizePromptToQuery("  hello world  "), "hello world");
  assert.equal(
    normalizePromptToQuery([
      { role: "system", content: "Ignore system" },
      {
        role: "user",
        content: [
          { type: "text", text: "First line" },
          { type: "text", text: "Second line" },
        ],
      },
    ]),
    "First line\nSecond line",
  );
  const norm = normalizeMessages([
    { role: "user", content: [{ type: "text", text: "Part A" }] },
    { role: "assistant", content: "Part B" },
  ]);
  assert.deepEqual(norm, [
    { role: "user", content: "Part A" },
    { role: "assistant", content: "Part B" },
  ]);
});

test("4. Error Handling & Retry Resilience (401 Missing Key, 429/503 Transient Retry, 400 Bad Request)", async () => {
  const mock = await createStatefulMockServer();
  try {
    // 1) Missing API key -> immediate 401 error
    await assert.rejects(
      () => getMemories("query", { baseUrl: mock.baseUrl }),
      /SlashMLAPIError \(401\): Missing API key/,
    );

    // 2) Transient 503 twice -> succeeds on 3rd attempt
    mock.injectTransientFailures(2, 503);
    const addRes = await addMemories("Resilient fact under 503", {
      slashmlApiKey: "sml_retry_key",
      baseUrl: mock.baseUrl,
      userId: "u_retry",
      maxRetries: 3,
    });
    assert.equal(addRes.results.length, 1);

    // 3) Transient 429 rate-limit -> retries and succeeds
    mock.injectTransientFailures(1, 429);
    const hits = await getMemories("Resilient", {
      slashmlApiKey: "sml_retry_key",
      baseUrl: mock.baseUrl,
      userId: "u_retry",
      maxRetries: 2,
    });
    assert.equal(hits.length, 1);

    // 4) Non-retryable 400 -> fails immediately with server detail
    await assert.rejects(
      () =>
        addMemories("Bad request", {
          slashmlApiKey: "sml_retry_key",
          baseUrl: mock.baseUrl,
          userId: "u_retry",
          metadata: { trigger_400: true },
        }),
      /SlashMLAPIError \(400\): Invalid metadata schema/,
    );
  } finally {
    await mock.close();
  }
});

test("5. High-Throughput Sequential & 200-Concurrent Load Benchmark (@slashml/vercel-ai-provider)", async () => {
  const mock = await createStatefulMockServer();
  try {
    const provider = createSlashML({
      slashmlApiKey: "sml_bench_key",
      baseUrl: mock.baseUrl,
      userId: "u_bench",
    });
    const model = provider("gpt-4o-mini");

    await model.addMemories("User builds low-latency AI agents with Vercel AI SDK.");

    // 1) 150 Sequential doGenerate calls with latency percentiles
    const seqCount = 150;
    const latencies = [];
    const t0 = performance.now();
    for (let i = 0; i < seqCount; i++) {
      const s = performance.now();
      const res = await model.doGenerate({
        prompt: [{ role: "user", content: [{ type: "text", text: `Query ${i}` }] }],
      });
      assert.ok(res.text.includes("low-latency AI agents"));
      latencies.push(performance.now() - s);
    }
    const seqElapsedSec = (performance.now() - t0) / 1000;
    const seqOpsPerSec = seqCount / seqElapsedSec;
    latencies.sort((a, b) => a - b);
    const p50 = latencies[Math.floor(latencies.length * 0.5)];
    const p95 = latencies[Math.floor(latencies.length * 0.95)];
    const p99 = latencies[Math.floor(latencies.length * 0.99)];

    // 2) 200 Concurrent mixed doGenerate + doStream + retrieveMemories calls
    const concCount = 200;
    const c0 = performance.now();
    const promises = Array.from({ length: concCount }, (_, idx) => {
      if (idx % 3 === 0) {
        return model.retrieveMemories(`Concurrent prompt ${idx}`);
      }
      if (idx % 3 === 1) {
        return model.doGenerate({ prompt: `Concurrent gen ${idx}` });
      }
      return model.doStream({ prompt: `Concurrent stream ${idx}` });
    });
    const results = await Promise.all(promises);
    const concElapsedSec = (performance.now() - c0) / 1000;
    const concOpsPerSec = concCount / concElapsedSec;

    assert.equal(results.length, concCount);
    console.log(
      `[Vercel AI Provider Benchmark] Seq(${seqCount}): ${seqOpsPerSec.toFixed(1)} ops/s ` +
        `(P50=${p50.toFixed(2)}ms, P95=${p95.toFixed(2)}ms, P99=${p99.toFixed(2)}ms) | ` +
        `Concurrent(${concCount}): ${concOpsPerSec.toFixed(1)} ops/s (0 errors)`,
    );
    assert.ok(seqOpsPerSec > 100, `Expected >100 seq ops/s, got ${seqOpsPerSec}`);
    assert.ok(concOpsPerSec > 100, `Expected >100 concurrent ops/s, got ${concOpsPerSec}`);
  } finally {
    await mock.close();
  }
});

test("6. CJS & ESM Export Parity", async () => {
  const esm = await import("../dist/index.mjs");
  assert.equal(typeof esm.createSlashML, "function");
  assert.equal(typeof esm.createMem0, "function");
  assert.equal(typeof esm.slashml, "function");
  assert.equal(typeof esm.mem0, "function");
  assert.equal(typeof esm.retrieveMemories, "function");
  assert.equal(typeof esm.addMemories, "function");
  assert.equal(typeof esm.getMemories, "function");
  assert.equal(typeof esm.searchMemories, "function");
  assert.equal(typeof esm.SlashMLAILanguageModel, "function");
  assert.equal(typeof esm.Mem0AILanguageModel, "function");
  assert.equal(esm.DEFAULT_BASE_URL, DEFAULT_BASE_URL);
  assert.equal(typeof slashml, "function");
  assert.equal(typeof mem0, "function");
});
