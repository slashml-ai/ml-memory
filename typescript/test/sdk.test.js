const test = require("node:test");
const assert = require("node:assert/strict");
const http = require("node:http");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawn } = require("node:child_process");
const { performance } = require("node:perf_hooks");

const {
  Memory,
  AsyncMemory,
  MemoryClient,
  AsyncMemoryClient,
  SlashMLMemory,
  SlashMLClient,
  SlashMLAPIError,
  DEFAULT_BASE_URL,
  DEFAULT_MODEL,
} = require("../dist/index.js");

function createMockServer(handler) {
  return new Promise((resolve) => {
    const requests = [];
    const server = http.createServer((req, res) => {
      let body = "";
      req.on("data", (chunk) => {
        body += chunk;
      });
      req.on("end", () => {
        let parsedBody = null;
        if (body) {
          try {
            parsedBody = JSON.parse(body);
          } catch {
            parsedBody = body;
          }
        }
        const record = {
          method: req.method,
          url: req.url,
          headers: req.headers,
          body: parsedBody,
        };
        requests.push(record);
        handler(record, res);
      });
    });
    server.listen(0, "127.0.0.1", () => {
      const addr = server.address();
      resolve({
        baseUrl: `http://127.0.0.1:${addr.port}`,
        requests,
        close: () => new Promise((r) => server.close(r)),
      });
    });
  });
}

test("MemoryClient defaults to https://api.slashml.ai and slashml-1.5-fast", () => {
  const client = new MemoryClient({ apiKey: "ml-test-key" });
  assert.equal(client.baseUrl, DEFAULT_BASE_URL);
  assert.equal(client.model, DEFAULT_MODEL);
  assert.equal(client.apiKey, "ml-test-key");
});

test("Native / ml endpoints: ingest, query, forget", async () => {
  const mock = await createMockServer((req, res) => {
    res.writeHead(200, { "Content-Type": "application/json" });
    if (req.url === "/v1/memory/ingest") {
      res.end(JSON.stringify({ status: "ingested", count: req.body.documents.length }));
    } else if (req.url === "/v1/memory/query") {
      res.end(JSON.stringify({ answer: "RS256", results: [{ text: "JWT RS256" }] }));
    } else if (req.url === "/v1/memory/forget") {
      res.end(JSON.stringify({ status: "forgotten", forgotten: true }));
    }
  });

  try {
    const client = new MemoryClient({
      apiKey: "ml-live-secret",
      baseUrl: mock.baseUrl,
      model: "slashml-1.5-pro",
    });

    const ingestRes = await client.ingest(["Doc 1", "Doc 2"], { namespace: "ns1" });
    assert.equal(ingestRes.status, "ingested");
    assert.equal(ingestRes.count, 2);
    assert.equal(mock.requests[0].headers.authorization, "Bearer ml-live-secret");
    assert.equal(mock.requests[0].body.namespace, "ns1");
    assert.equal(mock.requests[0].body.model, "slashml-1.5-pro");

    const queryRes = await client.query("How is JWT signed?", { namespace: "ns1", top_k: 3 });
    assert.equal(queryRes.answer, "RS256");
    assert.equal(mock.requests[1].body.top_k, 3);

    const forgetRes = await client.forget("Doc 1", { namespace: "ns1" });
    assert.equal(forgetRes.forgotten, true);
    assert.equal(mock.requests[2].body.target, "Doc 1");
  } finally {
    await mock.close();
  }
});

test("Mem0 drop-in Memory CRUD + search + history", async () => {
  const mock = await createMockServer((req, res) => {
    res.writeHead(200, { "Content-Type": "application/json" });
    if (req.method === "POST" && req.url === "/v1/memories") {
      res.end(JSON.stringify({ results: [{ id: "mem_1", memory: req.body.messages, event: "ADD" }] }));
    } else if (req.method === "POST" && req.url === "/v1/memories/search") {
      res.end(JSON.stringify({ results: [{ id: "mem_1", memory: "Likes TypeScript", score: 0.95 }] }));
    } else if (req.method === "GET" && req.url.startsWith("/v1/memories?")) {
      res.end(JSON.stringify({ results: [{ id: "mem_1", memory: "Likes TypeScript" }] }));
    } else if (req.method === "GET" && req.url === "/v1/memories/mem_1") {
      res.end(JSON.stringify({ id: "mem_1", memory: "Likes TypeScript" }));
    } else if (req.method === "PUT" && req.url === "/v1/memories/mem_1") {
      res.end(JSON.stringify({ id: "mem_1", memory: req.body.text, event: "UPDATE" }));
    } else if (req.method === "GET" && req.url === "/v1/memories/mem_1/history") {
      res.end(JSON.stringify({ history: [{ memory_id: "mem_1", event: "ADD" }, { memory_id: "mem_1", event: "UPDATE" }] }));
    } else if (req.method === "DELETE" && req.url === "/v1/memories/mem_1") {
      res.end(JSON.stringify({ message: "Memory deleted successfully!", deleted: true }));
    }
  });

  try {
    const m = Memory.fromConfig({ api_key: "ml-key", base_url: mock.baseUrl });
    assert.ok(m instanceof SlashMLMemory || m instanceof SlashMLClient || m instanceof MemoryClient);

    const added = await m.add("Likes TypeScript", { user_id: "u1" });
    assert.equal(added.results[0].id, "mem_1");

    const searched = await m.search("What language?", { user_id: "u1", limit: 3 });
    assert.equal(searched.results[0].id, "mem_1");

    const all = await m.getAll({ user_id: "u1" });
    assert.equal(all.results.length, 1);

    const single = await m.get("mem_1");
    assert.equal(single.id, "mem_1");

    const updated = await m.update("mem_1", "Loves strict TypeScript");
    assert.equal(updated.event, "UPDATE");

    const hist = await m.history("mem_1");
    assert.equal(hist.length, 2);

    const del = await m.delete("mem_1");
    assert.equal(del.deleted, true);
  } finally {
    await mock.close();
  }
});

test("HTTP 404 on get() returns null and HTTP 401 throws SlashMLAPIError", async () => {
  const mock = await createMockServer((req, res) => {
    if (req.url === "/v1/memories/missing") {
      res.writeHead(404, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: "Not found" }));
    } else {
      res.writeHead(401, { "Content-Type": "application/json" });
      res.end(JSON.stringify({ error: "Invalid API key" }));
    }
  });

  try {
    const m = new Memory({ apiKey: "bad-key", baseUrl: mock.baseUrl });
    const missing = await m.get("missing");
    assert.equal(missing, null);

    await assert.rejects(
      async () => {
        await m.search("test");
      },
      (err) => {
        assert.ok(err instanceof SlashMLAPIError);
        assert.equal(err.statusCode, 401);
        assert.match(err.message, /Invalid API key/);
        return true;
      }
    );
  } finally {
    await mock.close();
  }
});

test("ESM build (dist/index.mjs), snake_case aliases, deleteAll, and missing API key validation", async () => {
  const esm = await import("../dist/index.mjs");
  assert.equal(typeof esm.SlashMLMemory, "function");
  assert.equal(typeof esm.MemoryClient, "function");
  assert.equal(typeof esm.Memory, "function");

  const noKeyClient = new esm.SlashMLMemory({ apiKey: "" });
  await assert.rejects(
    async () => {
      await noKeyClient.add("should fail without key");
    },
    (err) => {
      assert.equal(err.name, "SlashMLAPIError");
      assert.match(err.message, /API key is required/);
      return true;
    }
  );

  const mock = await createMockServer((req, res) => {
    res.writeHead(200, { "Content-Type": "application/json" });
    if (req.method === "GET" && req.url.startsWith("/v1/memories?")) {
      res.end(JSON.stringify({ results: [{ id: "m_snake", memory: "snake_case works" }] }));
    } else if (req.method === "DELETE" && req.url.startsWith("/v1/memories?")) {
      res.end(JSON.stringify({ deleted: true, scope: req.url }));
    }
  });

  try {
    const client = new esm.Memory({ apiKey: "sml_esm_key", baseUrl: mock.baseUrl });
    const listRes = await client.get_all({ user_id: "u_esm" });
    assert.equal(listRes.results[0].id, "m_snake");

    const delAllRes = await client.delete_all({ user_id: "u_esm" });
    assert.equal(delAllRes.deleted, true);
  } finally {
    await mock.close();
  }
});

test("CLI --init writes /ml-memory MCP config to Cursor and Windsurf (including --skill ml-memory / /ml-memory and --workspace)", async () => {
  const tmpHome = fs.mkdtempSync(path.join(os.tmpdir(), "slashml-cli-init-"));
  const cliPath = path.resolve(__dirname, "../bin/cli.js");
  // Pre-create .mcp.json so generic --skill /ml-memory also updates project .mcp.json
  fs.writeFileSync(path.join(tmpHome, ".mcp.json"), JSON.stringify({ mcpServers: {} }), "utf8");
  await new Promise((resolve, reject) => {
    const proc = spawn(
      process.execPath,
      [cliPath, "--init", "--skill", "ml-memory", "--workspace", "/workspace/demo", "--api-key", "sml_init_test"],
      {
        cwd: tmpHome,
        env: { ...process.env, HOME: tmpHome },
        stdio: "pipe",
      }
    );
    proc.on("error", reject);
    proc.on("exit", (code) => {
      try {
        assert.equal(code, 0);
        const cursorCfg = JSON.parse(
          fs.readFileSync(path.join(tmpHome, ".cursor", "mcp.json"), "utf8")
        );
        assert.ok(cursorCfg.mcpServers["ml-memory"]);
        assert.equal(cursorCfg.mcpServers["ml-memory"].env.SLASHML_API_KEY, "sml_init_test");
        assert.deepEqual(cursorCfg.mcpServers["ml-memory"].args, ["-y", "@slashml/mcp", "--workspace", "/workspace/demo"]);

        const windsurfCfg = JSON.parse(
          fs.readFileSync(path.join(tmpHome, ".codeium", "windsurf", "mcp_config.json"), "utf8")
        );
        assert.ok(windsurfCfg.mcpServers["ml-memory"]);

        const claudeMcpCfg = JSON.parse(
          fs.readFileSync(path.join(tmpHome, ".mcp.json"), "utf8")
        );
        assert.ok(claudeMcpCfg.mcpServers["ml-memory"]);
        resolve();
      } catch (e) {
        reject(e);
      } finally {
        fs.rmSync(tmpHome, { recursive: true, force: true });
      }
    });
  });
});

test("SDK recall({ query, userId, topK }) and CLI --signup / --verify onboarding E2E", async () => {
  const requests = [];
  const mock = await createMockServer((req, res) => {
    requests.push(req);
    res.writeHead(200, { "Content-Type": "application/json" });
    if (req.url === "/v1/memories/search") {
      res.end(JSON.stringify({ results: [{ id: "m_recall", memory: "Recalled via .recall()", score: 0.99 }] }));
      return;
    }
    if (req.url === "/api/auth/magic-link/request") {
      res.end(JSON.stringify({ status: "sent", email: req.body.email, message: "Verification code sent." }));
      return;
    }
    if (req.url === "/api/auth/magic-link/verify") {
      res.end(
        JSON.stringify({
          status: "authenticated",
          initial_api_key: "sml_live_verified_onboard_key_99",
          user: { email: req.body.email },
        })
      );
      return;
    }
    res.end(JSON.stringify({ ok: true }));
  });

  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "slashml-onboard-"));
  fs.writeFileSync(path.join(tmpDir, ".gitignore"), "node_modules/\n", "utf8");
  const cliPath = path.resolve(__dirname, "../bin/cli.js");

  try {
    // 1. Test .recall() with both object-first and string-first signatures
    const client = new SlashMLMemory({ apiKey: "sml_test_recall", baseUrl: mock.baseUrl });
    const r1 = await client.recall({ query: "What did we recall?", userId: "u_42", topK: 5 });
    assert.equal(r1.results[0].id, "m_recall");
    assert.equal(requests[0].body.query, "What did we recall?");
    assert.equal(requests[0].body.user_id, "u_42");
    assert.equal(requests[0].body.limit, 5);

    const r2 = await client.recall("Second recall query", { userId: "u_42", topK: 3 });
    assert.equal(r2.results[0].id, "m_recall");
    assert.equal(requests[1].body.query, "Second recall query");
    assert.equal(requests[1].body.limit, 3);

    // 2. Test CLI --help and --version (must exit 0 immediately without hanging)
    const helpOut = await new Promise((resolve, reject) => {
      let stdout = "";
      const proc = spawn(process.execPath, [cliPath, "--help"], { cwd: tmpDir, stdio: "pipe" });
      proc.stdout.on("data", (c) => (stdout += c.toString("utf8")));
      proc.on("error", reject);
      proc.on("exit", (code) => (code === 0 ? resolve(stdout) : reject(new Error(`help exit ${code}`))));
    });
    assert.match(helpOut, /claude mcp add --scope user ml-memory/);

    // 2b. Test CLI --signup rejects public consumer domains (@gmail.com, @hotmail.com) and directs to Google/GitHub Sign-In
    const gmailRejectErr = await new Promise((resolve, reject) => {
      let stderr = "";
      const proc = spawn(
        process.execPath,
        [cliPath, "--signup", "randomuser@gmail.com", "--console-url", mock.baseUrl],
        { cwd: tmpDir, env: { ...process.env, HOME: tmpDir }, stdio: "pipe" }
      );
      proc.stderr.on("data", (c) => (stderr += c.toString("utf8")));
      proc.on("error", reject);
      proc.on("exit", (code) => (code !== 0 ? resolve(stderr) : reject(new Error("expected non-zero exit for public domain"))));
    });
    assert.match(gmailRejectErr, /Google or GitHub Sign-In/);

    // 3. Test CLI --signup with work/custom domain
    await new Promise((resolve, reject) => {
      const proc = spawn(
        process.execPath,
        [cliPath, "--signup", "founder@slashml.ai", "--console-url", mock.baseUrl],
        { cwd: tmpDir, env: { ...process.env, HOME: tmpDir }, stdio: "pipe" }
      );
      proc.on("error", reject);
      proc.on("exit", (code) => (code === 0 ? resolve() : reject(new Error(`signup exit ${code}`))));
    });
    assert.equal(requests[2].url, "/api/auth/magic-link/request");
    assert.equal(requests[2].body.email, "founder@slashml.ai");

    // 4. Test CLI --verify WITHOUT --init (must NOT write .env or .cursor/mcp.json)
    await new Promise((resolve, reject) => {
      const proc = spawn(
        process.execPath,
        [cliPath, "--verify", "founder@slashml.ai", "654321", "--console-url", mock.baseUrl],
        { cwd: tmpDir, env: { ...process.env, HOME: tmpDir }, stdio: "pipe" }
      );
      proc.on("error", reject);
      proc.on("exit", (code) => (code === 0 ? resolve() : reject(new Error(`verify plain exit ${code}`))));
    });
    assert.equal(fs.existsSync(path.join(tmpDir, ".env")), false);
    assert.equal(fs.existsSync(path.join(tmpDir, ".cursor", "mcp.json")), false);

    // 5. Test CLI --verify <email> <code> --init
    await new Promise((resolve, reject) => {
      const proc = spawn(
        process.execPath,
        [cliPath, "--verify", "founder@slashml.ai", "654321", "--init", "--console-url", mock.baseUrl],
        { cwd: tmpDir, env: { ...process.env, HOME: tmpDir }, stdio: "pipe" }
      );
      proc.on("error", reject);
      proc.on("exit", (code) => (code === 0 ? resolve() : reject(new Error(`verify exit ${code}`))));
    });
    assert.equal(requests[4].url, "/api/auth/magic-link/verify");
    assert.equal(requests[4].body.email, "founder@slashml.ai");
    assert.equal(requests[4].body.otp_code, "654321");
    assert.equal(requests[4].body.issue_cli_key, true);

    const envContent = fs.readFileSync(path.join(tmpDir, ".env"), "utf8");
    assert.match(envContent, /SLASHML_API_KEY=sml_live_verified_onboard_key_99/);
    const gitignoreContent = fs.readFileSync(path.join(tmpDir, ".gitignore"), "utf8");
    assert.match(gitignoreContent, /\.env/);
    const cursorCfg = JSON.parse(fs.readFileSync(path.join(tmpDir, ".cursor", "mcp.json"), "utf8"));
    assert.equal(
      cursorCfg.mcpServers["ml-memory"].env.SLASHML_API_KEY,
      "sml_live_verified_onboard_key_99"
    );
  } finally {
    fs.rmSync(tmpDir, { recursive: true, force: true });
    await mock.close();
  }
});

function createStatefulReferenceServer() {
  const store = new Map();
  let seq = 0;
  return createMockServer((req, res) => {
    res.writeHead(200, { "Content-Type": "application/json" });
    const urlObj = new URL(req.url, "http://127.0.0.1");
    const pathname = urlObj.pathname.replace(/\/+$/, "") || "/";

    if (req.method === "POST" && pathname === "/v1/memory/ingest") {
      const docs = req.body.documents || [];
      const ids = [];
      for (const d of docs) {
        const id = (typeof d === "object" && d.id) || `doc_${++seq}`;
        const text = typeof d === "string" ? d : d.text || "";
        const metadata = (typeof d === "object" && d.metadata) || req.body.metadata || {};
        store.set(id, { id, memory: text, text, user_id: req.body.user_id || "default", metadata });
        ids.push(id);
      }
      res.end(JSON.stringify({ status: "ingested", count: ids.length, ids }));
      return;
    }

    if (req.method === "POST" && pathname === "/v1/memory/query") {
      const q = String(req.body.query || "").toLowerCase();
      const topK = Number(req.body.top_k || 5);
      const hits = [];
      for (const item of store.values()) {
        if (!q || item.text.toLowerCase().includes(q) || q.split(/\s+/).some((w) => w && item.text.toLowerCase().includes(w))) {
          hits.push({ ...item, score: 0.95 });
        }
      }
      res.end(JSON.stringify({ results: hits.slice(0, topK) }));
      return;
    }

    if (req.method === "DELETE" && pathname === "/v1/memory/forget") {
      const target = req.body?.target || urlObj.searchParams.get("memory_id");
      if (target) store.delete(target);
      for (const id of req.body?.document_ids || []) store.delete(id);
      res.end(JSON.stringify({ status: "forgotten", forgotten: true, deleted: true }));
      return;
    }

    if (req.method === "POST" && pathname === "/v1/memories") {
      const id = req.body.memory_id || req.body.id || `mem_${++seq}`;
      const text =
        typeof req.body.messages === "string"
          ? req.body.messages
          : Array.isArray(req.body.messages)
            ? req.body.messages.map((m) => m.content).join("\n")
            : req.body.text || "";
      const item = {
        id,
        memory: text,
        text,
        user_id: req.body.user_id || "default",
        metadata: req.body.metadata || {},
      };
      store.set(id, item);
      res.end(JSON.stringify({ results: [{ id, memory: text, event: "ADD" }] }));
      return;
    }

    if (req.method === "POST" && (pathname === "/v1/memories/search" || pathname === "/v2/memories/search")) {
      const q = String(req.body.query || "").toLowerCase();
      const limit = Number(req.body.limit || req.body.top_k || 5);
      const hits = [];
      for (const item of store.values()) {
        const words = q.split(/\s+/).filter(Boolean);
        const matchCount = words.filter((w) => item.text.toLowerCase().includes(w)).length;
        if (matchCount > 0 || store.size <= limit) {
          hits.push({ ...item, score: 0.5 + matchCount * 0.1 });
        }
      }
      hits.sort((a, b) => b.score - a.score);
      res.end(JSON.stringify({ results: hits.slice(0, limit) }));
      return;
    }

    if (req.method === "GET" && pathname === "/v1/memories") {
      const uid = urlObj.searchParams.get("user_id");
      const limit = Number(urlObj.searchParams.get("limit") || 50);
      const results = Array.from(store.values())
        .filter((x) => !uid || x.user_id === uid)
        .slice(0, limit);
      res.end(JSON.stringify({ results }));
      return;
    }

    if (req.method === "DELETE" && pathname.startsWith("/v1/memories/")) {
      const id = decodeURIComponent(pathname.slice("/v1/memories/".length));
      store.delete(id);
      res.end(JSON.stringify({ id, deleted: true }));
      return;
    }

    res.end(JSON.stringify({ ok: true }));
  });
}

async function runMcpSession(binPath, args, rpcMessages, env = {}) {
  return new Promise((resolve, reject) => {
    const proc = spawn(process.execPath, [binPath, ...args], {
      env: { ...process.env, ...env },
      stdio: ["pipe", "pipe", "pipe"],
    });
    const responses = [];
    let buffer = "";
    const expectedResponses = rpcMessages.filter((m) => m.id !== undefined).length;

    proc.stdout.on("data", (chunk) => {
      buffer += chunk.toString("utf8");
      let idx;
      while ((idx = buffer.indexOf("\n")) !== -1) {
        const line = buffer.slice(0, idx).trim();
        buffer = buffer.slice(idx + 1);
        if (line) {
          responses.push(JSON.parse(line));
          if (responses.length >= expectedResponses) {
            proc.stdin.end();
          }
        }
      }
    });
    proc.on("error", reject);
    proc.on("close", () => resolve(responses));

    for (const msg of rpcMessages) {
      proc.stdin.write(JSON.stringify(msg) + "\n");
    }
  });
}

test("E2E Node MCP Server (@slashml/mcp and @slashml/memory bin): all 7 tools + --code-mode + --code-only", async () => {
  const server = await createStatefulReferenceServer();
  const sampleRepo = fs.mkdtempSync(path.join(os.tmpdir(), "slashml-mcp-repo-"));
  fs.writeFileSync(
    path.join(sampleRepo, "auth.ts"),
    "export function verifyJwtToken(token: string) { if (!token) throw new Error('TokenExpiredError'); return true; }\n",
    "utf8"
  );

  const candidateMcpBins = [
    path.resolve(__dirname, "../../mcp/bin/slashml-mcp.js"),
    path.resolve(__dirname, "../../npm-slashml-mcp/bin/slashml-mcp.js"),
    path.resolve(__dirname, "../bin/cli.js"),
  ];
  const mcpBins = candidateMcpBins.filter((p, idx, arr) => fs.existsSync(p) && arr.indexOf(p) === idx);

  try {
    for (const binPath of mcpBins) {
      // 1. Standard 7-tool mode
      const responses = await runMcpSession(
        binPath,
        ["--api-key", "sml_mcp_e2e", "--base-url", server.baseUrl, "--user-id", "u_mcp"],
        [
          { jsonrpc: "2.0", id: 1, method: "initialize", params: {} },
          { jsonrpc: "2.0", method: "notifications/initialized" },
          { jsonrpc: "2.0", id: 2, method: "ping" },
          { jsonrpc: "2.0", id: 3, method: "tools/list" },
          {
            jsonrpc: "2.0",
            id: 4,
            method: "tools/call",
            params: {
              name: "add_memory",
              arguments: { text: "Always use RS256 for production JWT tokens", memory_id: "m_jwt" },
            },
          },
          {
            jsonrpc: "2.0",
            id: 5,
            method: "tools/call",
            params: { name: "search_memories", arguments: { query: "JWT tokens", limit: 3 } },
          },
          {
            jsonrpc: "2.0",
            id: 6,
            method: "tools/call",
            params: { name: "get_memories", arguments: { limit: 10 } },
          },
          {
            jsonrpc: "2.0",
            id: 7,
            method: "tools/call",
            params: { name: "index_repository", arguments: { path: sampleRepo } },
          },
          {
            jsonrpc: "2.0",
            id: 8,
            method: "tools/call",
            params: { name: "search_code_by_behavior", arguments: { query: "verifyJwtToken", top_k: 3 } },
          },
          {
            jsonrpc: "2.0",
            id: 9,
            method: "tools/call",
            params: {
              name: "find_bug_candidates",
              arguments: { bug_description: "TokenExpiredError when token is empty", stack_trace: "at verifyJwtToken (auth.ts:1)" },
            },
          },
          {
            jsonrpc: "2.0",
            id: 10,
            method: "tools/call",
            params: { name: "forget_memory", arguments: { memory_id: "m_jwt" } },
          },
          {
            jsonrpc: "2.0",
            id: 11,
            method: "tools/call",
            params: { name: "nonexistent_tool", arguments: {} },
          },
        ]
      );

      assert.equal(responses.length, 11);
      assert.equal(responses[0].result.serverInfo.name, "ml-memory");
      assert.deepEqual(responses[1].result, {});
      assert.equal(responses[2].result.tools.length, 7);

      const addOut = JSON.parse(responses[3].result.content[0].text);
      assert.equal(addOut.results[0].id, "m_jwt");

      const searchOut = JSON.parse(responses[4].result.content[0].text);
      assert.ok(searchOut.results.length >= 1);

      const getOut = JSON.parse(responses[5].result.content[0].text);
      assert.ok(getOut.results.length >= 1);

      const idxOut = JSON.parse(responses[6].result.content[0].text);
      assert.equal(idxOut.indexed_files, 1);

      const codeOut = JSON.parse(responses[7].result.content[0].text);
      assert.ok(codeOut.results.length >= 1);

      const bugOut = JSON.parse(responses[8].result.content[0].text);
      assert.ok(bugOut.results.length >= 1);

      const forgetOut = JSON.parse(responses[9].result.content[0].text);
      assert.equal(forgetOut.deleted, true);

      assert.equal(responses[10].result.isError, true);

      // 2. --code-mode (execute_memory_code meta-tool)
      const codeModeRes = await runMcpSession(
        binPath,
        ["--code-mode", "--api-key", "sml_mcp_e2e", "--base-url", server.baseUrl],
        [
          { jsonrpc: "2.0", id: 1, method: "tools/list" },
          {
            jsonrpc: "2.0",
            id: 2,
            method: "tools/call",
            params: {
              name: "execute_memory_code",
              arguments: { action: "add_memory", params: { text: "Code mode memory", memory_id: "m_cm" } },
            },
          },
        ]
      );
      assert.equal(codeModeRes[0].result.tools.length, 1);
      assert.equal(codeModeRes[0].result.tools[0].name, "execute_memory_code");
      const cmAdd = JSON.parse(codeModeRes[1].result.content[0].text);
      assert.equal(cmAdd.results[0].id, "m_cm");

      // 3. --code-only (3 code tools)
      const codeOnlyRes = await runMcpSession(
        binPath,
        ["--code-only", "--api-key", "sml_mcp_e2e", "--base-url", server.baseUrl],
        [{ jsonrpc: "2.0", id: 1, method: "tools/list" }]
      );
      assert.equal(codeOnlyRes[0].result.tools.length, 3);
    }
  } finally {
    fs.rmSync(sampleRepo, { recursive: true, force: true });
    await server.close();
  }
});

test("Throughput & concurrency stress benchmark: TypeScript SDK + Node MCP Server", async () => {
  const server = await createStatefulReferenceServer();
  try {
    const client = new SlashMLMemory({ apiKey: "sml_bench_key", baseUrl: server.baseUrl });

    // 1. Sequential SDK latency & throughput (100 ops)
    const seqLatencies = [];
    const tSeqStart = performance.now();
    for (let i = 0; i < 100; i++) {
      const t0 = performance.now();
      await client.add(`Sequential fact #${i}: zero LLM extraction tax`, {
        user_id: "bench_u",
        memory_id: `seq_${i}`,
      });
      seqLatencies.push(performance.now() - t0);
    }
    const seqTotalMs = performance.now() - tSeqStart;
    seqLatencies.sort((a, b) => a - b);
    const seqOpsPerSec = (100 / (seqTotalMs / 1000)).toFixed(1);
    const seqP50 = seqLatencies[Math.floor(seqLatencies.length * 0.5)].toFixed(2);
    const seqP95 = seqLatencies[Math.floor(seqLatencies.length * 0.95)].toFixed(2);

    // 2. Concurrent SDK throughput (200 parallel requests across add/search/get)
    const tConcStart = performance.now();
    const tasks = [];
    for (let i = 0; i < 100; i++) {
      tasks.push(client.add(`Concurrent fact #${i}`, { user_id: "bench_u", memory_id: `conc_${i}` }));
      tasks.push(client.search("Concurrent fact", { user_id: "bench_u", limit: 3 }));
    }
    const results = await Promise.all(tasks);
    const concTotalMs = performance.now() - tConcStart;
    const concOpsPerSec = (tasks.length / (concTotalMs / 1000)).toFixed(1);
    assert.equal(results.length, 200);

    // 3. Node MCP stdio pipelined throughput (100 RPC calls)
    const mcpBinCandidates = [
      path.resolve(__dirname, "../../mcp/bin/slashml-mcp.js"),
      path.resolve(__dirname, "../../npm-slashml-mcp/bin/slashml-mcp.js"),
      path.resolve(__dirname, "../bin/cli.js"),
    ];
    const mcpBin = mcpBinCandidates.find((p) => fs.existsSync(p));
    const rpcs = [];
    for (let i = 1; i <= 100; i++) {
      rpcs.push({
        jsonrpc: "2.0",
        id: i,
        method: "tools/call",
        params: {
          name: i % 2 === 0 ? "search_memories" : "add_memory",
          arguments: i % 2 === 0 ? { query: "fact", limit: 2 } : { text: `MCP fact ${i}` },
        },
      });
    }
    const tMcpStart = performance.now();
    const mcpRes = await runMcpSession(
      mcpBin,
      ["--api-key", "sml_bench_key", "--base-url", server.baseUrl],
      rpcs
    );
    const mcpTotalMs = performance.now() - tMcpStart;
    const mcpOpsPerSec = (100 / (mcpTotalMs / 1000)).toFixed(1);
    assert.equal(mcpRes.length, 100);

    console.log(
      `[TS Benchmark] Seq: ${seqOpsPerSec} ops/s (P50=${seqP50}ms, P95=${seqP95}ms) | Concurrent(200): ${concOpsPerSec} ops/s | MCP Stdio(100): ${mcpOpsPerSec} ops/s`
    );
    assert.ok(Number(seqOpsPerSec) > 50, `Expected >50 seq ops/s, got ${seqOpsPerSec}`);
    assert.ok(Number(concOpsPerSec) > 100, `Expected >100 concurrent ops/s, got ${concOpsPerSec}`);
  } finally {
    await server.close();
  }
});

test("Full Mem0 Cloud drop-in parity: AsyncMemoryClient, AsyncMemory, batch, users, feedback, project, webhooks, camelCase options", async () => {
  const mock = await createMockServer((req, res) => {
    res.writeHead(200, { "Content-Type": "application/json" });
    const urlObj = new URL(req.url, "http://127.0.0.1");
    const pathname = urlObj.pathname;

    if (req.method === "POST" && pathname === "/v1/memories") {
      res.end(JSON.stringify({ results: [{ id: "m_camel", user_id: req.body.user_id, agent_id: req.body.agent_id }] }));
    } else if (req.method === "PUT" && pathname === "/v1/batch") {
      res.end(JSON.stringify({ updated: req.body.memories.map((m) => m.memory_id) }));
    } else if (req.method === "DELETE" && pathname === "/v1/batch") {
      res.end(JSON.stringify({ deleted: req.body.memories.map((m) => m.memory_id) }));
    } else if (req.method === "GET" && pathname === "/v1/entities") {
      res.end(JSON.stringify({ results: [{ id: "u_1", type: "user" }] }));
    } else if (req.method === "DELETE" && pathname === "/v1/entities") {
      res.end(JSON.stringify({ deleted: true, user_id: urlObj.searchParams.get("user_id") }));
    } else if (req.method === "POST" && pathname === "/v1/feedback") {
      res.end(JSON.stringify({ status: "recorded", memory_id: req.body.memory_id, feedback: req.body.feedback }));
    } else if (pathname.startsWith("/v1/project")) {
      res.end(JSON.stringify({ project: "proj_1", method: req.method, path: pathname, body: req.body }));
    } else if (pathname.startsWith("/v1/webhooks")) {
      res.end(JSON.stringify({ webhook: "wh_1", method: req.method, path: pathname, body: req.body }));
    } else {
      res.end(JSON.stringify({ ok: true }));
    }
  });

  try {
    const asyncClient = new AsyncMemoryClient({ apiKey: "sml_parity", baseUrl: mock.baseUrl });
    const asyncMem = await AsyncMemory.fromConfig({ apiKey: "sml_parity", baseUrl: mock.baseUrl });
    assert.ok(asyncMem instanceof AsyncMemory);

    // camelCase userId / agentId mapping
    const added = await asyncClient.add("Hello camelCase", { userId: "u_camel", agentId: "ag_1" });
    assert.equal(added.results[0].user_id, "u_camel");
    assert.equal(added.results[0].agent_id, "ag_1");

    // Batch update & delete
    const bUpd = await asyncClient.batchUpdate([{ memoryId: "m1", text: "updated" }]);
    assert.deepEqual(bUpd.updated, ["m1"]);
    const bDel = await asyncClient.batchDelete(["m1", { memory_id: "m2" }]);
    assert.deepEqual(bDel.deleted, ["m1", "m2"]);

    // Entities / users
    const users = await asyncClient.users();
    assert.equal(users.results[0].id, "u_1");
    const delUser = await asyncClient.deleteUsers({ userId: "u_1" });
    assert.equal(delUser.deleted, true);
    assert.equal(delUser.user_id, "u_1");

    // Feedback
    const fb = await asyncClient.feedback({ memoryId: "m1", feedback: "POSITIVE", feedbackReason: "Accurate" });
    assert.equal(fb.status, "recorded");
    assert.equal(fb.feedback, "POSITIVE");

    // Project sub-resource & top-level helpers
    const pGet = await asyncClient.project.get({ fields: ["custom_instructions"] });
    assert.equal(pGet.project, "proj_1");
    const pUpd = await asyncClient.updateProject({ customInstructions: "Extract code facts" });
    assert.equal(pUpd.body.custom_instructions, "Extract code facts");
    const pMem = await asyncClient.project.addMember({ email: "dev@slashml.ai", role: "admin" });
    assert.equal(pMem.body.email, "dev@slashml.ai");

    // Webhooks
    const whCreated = await asyncClient.createWebhook({ name: "hook1", url: "https://example.com/wh", eventTypes: ["memory.add"] });
    assert.equal(whCreated.webhook, "wh_1");
    const whList = await asyncClient.getWebhooks();
    assert.equal(whList.webhook, "wh_1");
    const whUpd = await asyncClient.updateWebhook({ webhookId: "wh_1", name: "hook1_v2" });
    assert.equal(whUpd.path, "/v1/webhooks/wh_1");
    const whDel = await asyncClient.deleteWebhook("wh_1");
    assert.equal(whDel.method, "DELETE");
  } finally {
    await mock.close();
  }
});
