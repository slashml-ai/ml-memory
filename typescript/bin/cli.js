#!/usr/bin/env node
/**
 * @slashml/memory — Self-Contained CLI & MCP Stdio Server (/ml-memory)
 */

const fs = require("fs");
const os = require("os");
const path = require("path");
const readline = require("readline");

const DEFAULT_BASE_URL = "https://api.slashml.ai";
const DEFAULT_CONSOLE_URL = "https://app.slashml.ai";

function parseCliArgs(argv) {
  let isInit = false;
  let skill = null;
  let apiKey = process.env.SLASHML_API_KEY || null;
  let baseUrl = (process.env.SLASHML_BASE_URL || DEFAULT_BASE_URL).replace(/\/+$/, "");
  let consoleUrl = (process.env.SLASHML_CONSOLE_URL || DEFAULT_CONSOLE_URL).replace(/\/+$/, "");
  let userId = process.env.SLASHML_USER_ID || "default";
  let codeOnly = false;
  let codeMode = false;
  let repo = null;
  let signupEmail = null;
  let verifyEmail = null;
  let verifyCode = null;
  let writeEnv = false;

  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === "init" || arg === "--init") {
      isInit = true;
    } else if (arg === "--skill" && i + 1 < argv.length) {
      skill = argv[++i];
    } else if (arg === "--api-key" && i + 1 < argv.length) {
      apiKey = argv[++i];
    } else if (arg === "--base-url" && i + 1 < argv.length) {
      baseUrl = argv[++i].replace(/\/+$/, "");
    } else if (arg === "--console-url" && i + 1 < argv.length) {
      consoleUrl = argv[++i].replace(/\/+$/, "");
    } else if (arg === "--user-id" && i + 1 < argv.length) {
      userId = argv[++i];
    } else if ((arg === "--repo" || arg === "--workspace") && i + 1 < argv.length) {
      repo = argv[++i];
    } else if (arg === "--signup" && i + 1 < argv.length) {
      signupEmail = argv[++i];
    } else if (arg === "--verify" && i + 1 < argv.length) {
      verifyEmail = argv[++i];
      if (i + 1 < argv.length && !argv[i + 1].startsWith("-")) {
        verifyCode = argv[++i];
      }
    } else if (arg === "--code" && i + 1 < argv.length) {
      verifyCode = argv[++i];
    } else if (arg === "--write-env") {
      writeEnv = true;
    } else if (arg === "--code-only") {
      codeOnly = true;
    } else if (arg === "--code-mode") {
      codeMode = true;
    }
  }
  return {
    isInit,
    skill,
    apiKey,
    baseUrl,
    consoleUrl,
    userId,
    codeOnly,
    codeMode,
    repo,
    signupEmail,
    verifyEmail,
    verifyCode,
    writeEnv,
  };
}

function saveApiKeyToEnvFile(apiKey, cwd = process.cwd()) {
  if (!apiKey) return;
  const envPath = path.join(cwd, ".env");
  let content = "";
  if (fs.existsSync(envPath)) {
    try {
      content = fs.readFileSync(envPath, "utf8");
    } catch {
      content = "";
    }
  }
  const line = `SLASHML_API_KEY=${apiKey}`;
  if (/^SLASHML_API_KEY=.*$/m.test(content)) {
    content = content.replace(/^SLASHML_API_KEY=.*$/m, line);
  } else {
    content = content ? `${content.replace(/\n*$/, "")}\n${line}\n` : `${line}\n`;
  }
  fs.writeFileSync(envPath, content, "utf8");

  const gitignorePath = path.join(cwd, ".gitignore");
  if (fs.existsSync(gitignorePath)) {
    try {
      const gi = fs.readFileSync(gitignorePath, "utf8");
      if (!gi.split(/\r?\n/).some((l) => l.trim() === ".env" || l.trim() === ".env*")) {
        fs.writeFileSync(gitignorePath, `${gi.replace(/\n*$/, "")}\n.env\n`, "utf8");
      }
    } catch {
      // ignore
    }
  }
}

const GENERIC_SKILL_NAMES = new Set(["ml-memory", "/ml-memory", "slashml", "all", "default"]);

function nativeNodeInit(skill, apiKey, repo = null, writeEnv = false) {
  const home = os.homedir();
  const cwd = process.cwd();
  const targets = [
    path.join(home, ".cursor", "mcp.json"),
    path.join(home, ".codeium", "windsurf", "mcp_config.json"),
  ];
  const claudeConfig = path.join(cwd, ".mcp.json");
  const normalizedSkill = skill ? skill.trim().toLowerCase() : null;
  const isGenericSkill = !normalizedSkill || GENERIC_SKILL_NAMES.has(normalizedSkill);

  if (
    fs.existsSync(claudeConfig) ||
    (normalizedSkill && (normalizedSkill.includes("claude") || normalizedSkill.includes("mcp.json")))
  ) {
    targets.push(claudeConfig);
  }

  const resolvedTargets = targets.filter((t) => {
    if (isGenericSkill) return true;
    return t.toLowerCase().includes(normalizedSkill);
  });

  const args = ["-y", "@slashml/mcp"];
  if (repo) {
    args.push("--workspace", repo);
  }
  const serverEntry = {
    command: "npx",
    args,
  };
  const resolvedKey = apiKey || process.env.SLASHML_API_KEY;
  if (resolvedKey) {
    serverEntry.env = {
      SLASHML_API_KEY: resolvedKey,
    };
  }
  if (writeEnv && resolvedKey) {
    saveApiKeyToEnvFile(resolvedKey, cwd);
  }

  for (const target of resolvedTargets) {
    fs.mkdirSync(path.dirname(target), { recursive: true });
    let data = {};
    if (fs.existsSync(target)) {
      try {
        data = JSON.parse(fs.readFileSync(target, "utf8"));
      } catch {
        data = {};
      }
    }
    if (!data.mcpServers || typeof data.mcpServers !== "object") {
      data.mcpServers = {};
    }
    data.mcpServers["/ml-memory"] = serverEntry;
    fs.writeFileSync(target, JSON.stringify(data, null, 2) + "\n", "utf8");
    console.log(`Configured /ml-memory MCP in ${target}`);
  }
}

async function runCliSignup(email, consoleUrl) {
  const res = await fetch(`${consoleUrl}/api/auth/magic-link/request`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "User-Agent": "slashml-cli-node/1.0.0",
    },
    body: JSON.stringify({ email: email.trim(), source: "cli" }),
  });
  const text = await res.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { raw: text };
  }
  if (!res.ok) {
    throw new Error(data.error || data.message || `Signup request failed (HTTP ${res.status})`);
  }
  console.log(
    JSON.stringify({
      status: "verification_code_sent",
      email: email.trim(),
      message: `A 6-digit verification code has been sent to ${email.trim()}. Ask the user for the 6-digit code and run: npx -y @slashml/memory --verify ${email.trim()} <6-digit-code> --init`,
      ...(data.dev_otp_code ? { dev_otp_code: data.dev_otp_code } : {}),
    })
  );
}

async function runCliVerify(email, code, parsedArgs) {
  if (!code) {
    throw new Error("Missing 6-digit verification code. Usage: npx -y @slashml/memory --verify <email> <6-digit-code> --init");
  }
  const res = await fetch(`${parsedArgs.consoleUrl}/api/auth/magic-link/verify`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "User-Agent": "slashml-cli-node/1.0.0",
    },
    body: JSON.stringify({
      email: email.trim(),
      otp_code: String(code).trim(),
      code: String(code).trim(),
      issue_cli_key: true,
    }),
  });
  const text = await res.text();
  let data = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { raw: text };
  }
  if (!res.ok) {
    throw new Error(data.error || data.message || `Verification failed (HTTP ${res.status})`);
  }
  const provisionedKey = data.initial_api_key || data.api_key || data.apiKey;
  if (!provisionedKey) {
    throw new Error(
      data.message ||
        "Account verified, but no new API key was returned. Create a key at https://app.slashml.ai and set SLASHML_API_KEY."
    );
  }
  saveApiKeyToEnvFile(provisionedKey, process.cwd());
  nativeNodeInit(parsedArgs.skill, provisionedKey, parsedArgs.repo, false);
  console.log(
    JSON.stringify({
      status: "authenticated",
      email: email.trim(),
      api_key: provisionedKey,
      env_saved: path.join(process.cwd(), ".env"),
      mcp_server: "/ml-memory",
    })
  );
}

const parsed = parseCliArgs(process.argv.slice(2));

if (parsed.signupEmail) {
  runCliSignup(parsed.signupEmail, parsed.consoleUrl)
    .then(() => process.exit(0))
    .catch((err) => {
      console.error(`Error: ${err.message || err}`);
      process.exit(1);
    });
  return;
}

if (parsed.verifyEmail) {
  runCliVerify(parsed.verifyEmail, parsed.verifyCode, parsed)
    .then(() => process.exit(0))
    .catch((err) => {
      console.error(`Error: ${err.message || err}`);
      process.exit(1);
    });
  return;
}

if (parsed.isInit) {
  nativeNodeInit(parsed.skill, parsed.apiKey, parsed.repo, parsed.writeEnv);
  process.exit(0);
}

const STANDARD_TOOLS = [
  {
    name: "add_memory",
    description:
      "Store a persistent fact, architectural decision, user preference, or code snippet in `/ ml` Cloud ($0 LLM extraction cost).",
    inputSchema: {
      type: "object",
      properties: {
        text: { type: "string" },
        user_id: { type: "string" },
        memory_id: { type: "string" },
        metadata: { type: "object" },
      },
      required: ["text"],
    },
  },
  {
    name: "search_memories",
    description: "Retrieve relevant memories and code context for a natural-language query.",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string" },
        user_id: { type: "string" },
        limit: { type: "integer", default: 5 },
      },
      required: ["query"],
    },
  },
  {
    name: "get_memories",
    description: "List stored memories for a user or project scope.",
    inputSchema: {
      type: "object",
      properties: {
        user_id: { type: "string" },
        limit: { type: "integer", default: 50 },
      },
    },
  },
  {
    name: "forget_memory",
    description: "Physically unlearn and delete a specific memory ID in O(1).",
    inputSchema: {
      type: "object",
      properties: {
        memory_id: { type: "string" },
      },
      required: ["memory_id"],
    },
  },
  {
    name: "index_repository",
    description:
      "Parse and index source code files (Python, TypeScript/JS, Rust, Go) in a repository directory into the `/ ml` Cloud memory engine.",
    inputSchema: {
      type: "object",
      properties: {
        path: { type: "string", description: "Repository directory path" },
      },
      required: ["path"],
    },
  },
  {
    name: "search_code_by_behavior",
    description:
      "Search indexed functions, classes, and modules by computational behavior or architectural role, even when identifiers differ.",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", description: "Behavioral or code query" },
        top_k: { type: "integer", default: 5 },
        language: { type: "string" },
      },
      required: ["query"],
    },
  },
  {
    name: "find_bug_candidates",
    description:
      "Localize likely buggy functions or modules from a symptom description or stack trace.",
    inputSchema: {
      type: "object",
      properties: {
        bug_description: { type: "string" },
        stack_trace: { type: "string" },
        top_k: { type: "integer", default: 5 },
      },
      required: ["bug_description"],
    },
  },
];

const CODE_MODE_TOOLS = [
  {
    name: "execute_memory_code",
    description:
      "Compact meta-tool (91% token savings) dispatching memory & code actions (`add_memory`, `search_memories`, `get_memories`, `forget_memory`, `index_repository`, `search_code_by_behavior`, `find_bug_candidates`) to `/ ml` Cloud.",
    inputSchema: {
      type: "object",
      properties: {
        action: {
          type: "string",
          enum: [
            "add_memory",
            "search_memories",
            "get_memories",
            "forget_memory",
            "index_repository",
            "search_code_by_behavior",
            "find_bug_candidates",
          ],
        },
        params: { type: "object" },
      },
      required: ["action"],
    },
  },
];

async function apiRequest(opts, method, urlPath, body) {
  if (!opts.apiKey) {
    throw new Error(
      "SlashML API key is required. Set SLASHML_API_KEY in your environment or pass --api-key."
    );
  }
  const res = await fetch(`${opts.baseUrl}${urlPath}`, {
    method,
    headers: {
      Authorization: `Bearer ${opts.apiKey}`,
      "Content-Type": "application/json",
      "User-Agent": "slashml-cli-node/1.0.0",
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  const data = text ? JSON.parse(text) : {};
  if (!res.ok) {
    throw new Error(`SlashML Cloud API error (HTTP ${res.status}): ${text}`);
  }
  return data;
}

function walkCodeFiles(rootDir) {
  const exts = new Set([".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go"]);
  const skipDirs = new Set([".git", "node_modules", ".venv", "dist", "build", "target", "__pycache__"]);
  const docs = [];

  function walk(dir) {
    let entries = [];
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      if (entry.name.startsWith(".") || skipDirs.has(entry.name)) continue;
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(fullPath);
      } else if (entry.isFile() && exts.has(path.extname(entry.name))) {
        try {
          const content = fs.readFileSync(fullPath, "utf8");
          const relPath = path.relative(rootDir, fullPath);
          docs.push({
            id: `file::${relPath}`,
            text: `[FILE] ${relPath}\n${content.slice(0, 4000)}`,
            metadata: { kind: "code_symbol", file_path: relPath },
          });
        } catch {
          // ignore unreadable files
        }
      }
    }
  }
  walk(rootDir);
  return docs;
}

async function dispatchTool(opts, name, args = {}) {
  if (name === "execute_memory_code") {
    return dispatchTool(opts, args.action, args.params || {});
  }
  const uid = args.user_id || opts.userId;

  if (name === "add_memory") {
    return apiRequest(opts, "POST", "/v1/memories", {
      messages: args.text,
      user_id: uid,
      memory_id: args.memory_id,
      metadata: args.metadata || {},
    });
  }
  if (name === "search_memories") {
    return apiRequest(opts, "POST", "/v1/memories/search", {
      query: args.query,
      user_id: uid,
      limit: args.limit || 5,
    });
  }
  if (name === "get_memories") {
    const q = new URLSearchParams({ user_id: uid, limit: String(args.limit || 50) });
    return apiRequest(opts, "GET", `/v1/memories?${q.toString()}`);
  }
  if (name === "forget_memory") {
    return apiRequest(opts, "DELETE", `/v1/memories/${encodeURIComponent(args.memory_id)}`);
  }
  if (name === "index_repository") {
    const repoPath = path.resolve(args.path || opts.repo || ".");
    const documents = walkCodeFiles(repoPath);
    const res = await apiRequest(opts, "POST", "/v1/memory/ingest", {
      documents,
      user_id: uid,
    });
    return { indexed_files: documents.length, ...res };
  }
  if (name === "search_code_by_behavior") {
    return apiRequest(opts, "POST", "/v1/memories/search", {
      query: args.query,
      user_id: uid,
      limit: args.top_k || 5,
      filters: { kind: "code_symbol", ...(args.language ? { language: args.language } : {}) },
    });
  }
  if (name === "find_bug_candidates") {
    const combinedQuery = args.stack_trace
      ? `${args.bug_description}\n${args.stack_trace}`
      : args.bug_description;
    return apiRequest(opts, "POST", "/v1/memories/search", {
      query: combinedQuery,
      user_id: uid,
      limit: args.top_k || 5,
      filters: { kind: "code_symbol" },
    });
  }
  throw new Error(`Unknown MCP tool: ${name}`);
}

const rl = readline.createInterface({ input: process.stdin, terminal: false });
let rpcChain = Promise.resolve();
rl.on("line", (line) => {
  const trimmed = line.trim();
  if (!trimmed) return;
  rpcChain = rpcChain.then(async () => {
    try {
      const req = JSON.parse(trimmed);
      const { method, id, params } = req;
      if (method === "notifications/initialized") return;
      if (method === "ping") {
        process.stdout.write(JSON.stringify({ jsonrpc: "2.0", id, result: {} }) + "\n");
        return;
      }
      if (method === "initialize") {
        process.stdout.write(
          JSON.stringify({
            jsonrpc: "2.0",
            id,
            result: {
              protocolVersion: "2024-11-05",
              serverInfo: { name: "/ml-memory", version: "1.0.0" },
              capabilities: { tools: {} },
            },
          }) + "\n"
        );
        return;
      }
      if (method === "tools/list") {
        const tools = parsed.codeMode
          ? CODE_MODE_TOOLS
          : parsed.codeOnly
            ? STANDARD_TOOLS.slice(4)
            : STANDARD_TOOLS;
        process.stdout.write(JSON.stringify({ jsonrpc: "2.0", id, result: { tools } }) + "\n");
        return;
      }
      if (method === "tools/call") {
        try {
          const result = await dispatchTool(parsed, params?.name, params?.arguments);
          process.stdout.write(
            JSON.stringify({
              jsonrpc: "2.0",
              id,
              result: { content: [{ type: "text", text: JSON.stringify(result) }] },
            }) + "\n"
          );
        } catch (err) {
          process.stdout.write(
            JSON.stringify({
              jsonrpc: "2.0",
              id,
              result: {
                isError: true,
                content: [{ type: "text", text: String(err.message || err) }],
              },
            }) + "\n"
          );
        }
        return;
      }
      process.stdout.write(
        JSON.stringify({
          jsonrpc: "2.0",
          id,
          error: { code: -32601, message: `Method not found: ${method}` },
        }) + "\n"
      );
    } catch {
      // ignore malformed lines
    }
  });
});
