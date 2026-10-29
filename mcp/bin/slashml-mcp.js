#!/usr/bin/env node
/**
 * @slashml/mcp — Self-Contained Official MCP Stdio Server for SlashML (/ml-memory).
 *
 * Zero external dependencies. Runs locally over JSON-RPC 2.0 stdio and connects
 * to the SlashML Cloud API (https://api.slashml.ai).
 */

const fs = require("fs");
const os = require("os");
const path = require("path");
const readline = require("readline");

const DEFAULT_BASE_URL = "https://api.slashml.ai";
const DEFAULT_CONSOLE_URL = "https://app.slashml.ai";
const PACKAGE_VERSION = "1.0.2";
const GENERIC_SKILL_NAMES = new Set(["ml-memory", "/ml-memory", "slashml", "all", "default"]);

function printHelp() {
  console.log(`@slashml/mcp v${PACKAGE_VERSION} — Official MCP Stdio Server for / ml (SlashML · https://slashml.ai)
Publisher: SlashML / FractionML (slashml.ai · fractionml.com)

Usage:
  npx -y @slashml/mcp [options]

When invoked without CLI flags, starts the JSON-RPC 2.0 MCP server over stdio.

Claude Code Registration (User Scope):
  claude mcp add --scope user ml-memory -e SLASHML_API_KEY="$SLASHML_API_KEY" -- npx -y @slashml/mcp

Options:
  -h, --help                     Show this help message and exit
  -v, --version                  Print package version and exit
  --api-key <key>                SlashML API key (or set SLASHML_API_KEY env var)
  --workspace, --repo <path>     Optional workspace directory to scope/index (defaults to process.cwd() at runtime)
  --user-id <id>                 Default user/workspace namespace (default: SLASHML_USER_ID or "default")
  --code-only                    Expose only code & bug-localization MCP tools
  --code-mode                    Expose compact single meta-tool (execute_memory_code)
  --init                         Write ml-memory MCP entry to Cursor, Windsurf, or .mcp.json
  --skill <name>                 Filter IDE config target during --init (default: ml-memory)
  --write-env                    Save SLASHML_API_KEY to .env in the current directory
  --signup <work-email>          Request a 6-digit OTP to provision a / ml free API key (requires work/custom domain @company.com; for @gmail.com / @hotmail.com sign in with Google/GitHub at https://app.slashml.ai)
  --verify <work-email> <code>   Verify 6-digit code and print the new SLASHML_API_KEY to stdout`);
}

const PUBLIC_CONSUMER_EMAIL_DOMAINS = new Set([
  "gmail.com",
  "googlemail.com",
  "hotmail.com",
  "hotmail.co.uk",
  "hotmail.fr",
  "hotmail.de",
  "hotmail.es",
  "hotmail.it",
  "outlook.com",
  "outlook.co.uk",
  "outlook.fr",
  "outlook.de",
  "live.com",
  "live.co.uk",
  "msn.com",
  "yahoo.com",
  "yahoo.co.uk",
  "yahoo.co.jp",
  "yahoo.fr",
  "yahoo.de",
  "yahoo.ca",
  "yahoo.com.br",
  "yahoo.in",
  "ymail.com",
  "rocketmail.com",
  "myyahoo.com",
  "icloud.com",
  "me.com",
  "mac.com",
  "aol.com",
  "proton.me",
  "protonmail.com",
  "protonmail.ch",
  "pm.me",
  "zoho.com",
  "zohomail.com",
  "gmx.com",
  "gmx.de",
  "gmx.net",
  "mail.com",
  "email.com",
  "fastmail.com",
  "fastmail.fm",
  "hey.com",
  "tutanota.com",
  "tuta.com",
  "tuta.io",
  "yandex.com",
  "yandex.ru",
  "mail.ru",
  "bk.ru",
  "inbox.ru",
  "list.ru",
  "qq.com",
  "163.com",
  "126.com",
  "foxmail.com",
  "naver.com",
  "daum.net",
  "hanmail.net",
]);

function assertCliWorkEmail(rawEmail) {
  const cleaned = String(rawEmail || "").trim().toLowerCase();
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(cleaned)) {
    throw new Error("Please provide a valid work email address (e.g. you@company.com).");
  }
  const [, domainPart] = cleaned.split("@");
  const canonicalDomain = domainPart === "googlemail.com" ? "gmail.com" : domainPart;
  if (PUBLIC_CONSUMER_EMAIL_DOMAINS.has(canonicalDomain)) {
    throw new Error(
      "Public email domains (@gmail.com, @hotmail.com, @outlook.com, @yahoo.com, @icloud.com, etc.) require Google or GitHub Sign-In at https://app.slashml.ai/auth/google. For CLI OTP signup (--signup), please use a work or custom domain email (you@company.com)."
    );
  }
  return cleaned;
}

function parseArgs(argv) {
  const opts = {
    isHelp: false,
    isVersion: false,
    isInit: false,
    skill: null,
    apiKey: process.env.SLASHML_API_KEY || null,
    baseUrl: (process.env.SLASHML_BASE_URL || DEFAULT_BASE_URL).replace(/\/+$/, ""),
    consoleUrl: (process.env.SLASHML_CONSOLE_URL || DEFAULT_CONSOLE_URL).replace(/\/+$/, ""),
    userId: process.env.SLASHML_USER_ID || "default",
    codeOnly: false,
    codeMode: false,
    repo: null,
    signupEmail: null,
    verifyEmail: null,
    verifyCode: null,
    writeEnv: false,
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "-h" || a === "--help" || a === "help") opts.isHelp = true;
    else if (a === "-v" || a === "--version" || a === "version") opts.isVersion = true;
    else if (a === "init" || a === "--init") opts.isInit = true;
    else if (a === "--skill" && i + 1 < argv.length) opts.skill = argv[++i];
    else if (a === "--api-key" && i + 1 < argv.length) opts.apiKey = argv[++i];
    else if (a === "--base-url" && i + 1 < argv.length) opts.baseUrl = argv[++i].replace(/\/+$/, "");
    else if (a === "--console-url" && i + 1 < argv.length) opts.consoleUrl = argv[++i].replace(/\/+$/, "");
    else if (a === "--user-id" && i + 1 < argv.length) opts.userId = argv[++i];
    else if ((a === "--repo" || a === "--workspace") && i + 1 < argv.length) opts.repo = argv[++i];
    else if (a === "--signup" && i + 1 < argv.length) opts.signupEmail = argv[++i];
    else if (a === "--verify" && i + 1 < argv.length) {
      opts.verifyEmail = argv[++i];
      if (i + 1 < argv.length && !argv[i + 1].startsWith("-")) {
        opts.verifyCode = argv[++i];
      }
    } else if (a === "--code" && i + 1 < argv.length) opts.verifyCode = argv[++i];
    else if (a === "--write-env") opts.writeEnv = true;
    else if (a === "--code-only") opts.codeOnly = true;
    else if (a === "--code-mode") opts.codeMode = true;
  }
  return opts;
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
    delete data.mcpServers["/ml-memory"];
    data.mcpServers["ml-memory"] = serverEntry;
    fs.writeFileSync(target, JSON.stringify(data, null, 2) + "\n", "utf8");
    console.log(`Configured ml-memory MCP in ${target}`);
  }
}

async function runCliSignup(email, consoleUrl) {
  const checkedEmail = assertCliWorkEmail(email);
  const res = await fetch(`${consoleUrl}/api/auth/magic-link/request`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "User-Agent": `slashml-mcp-node/${PACKAGE_VERSION}`,
    },
    body: JSON.stringify({ email: checkedEmail, source: "cli" }),
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
      email: checkedEmail,
      message: `A 6-digit verification code has been sent to ${checkedEmail}. Ask the user for the 6-digit code and run: npx -y @slashml/memory --verify ${checkedEmail} <6-digit-code>`,
      ...(data.dev_otp_code ? { dev_otp_code: data.dev_otp_code } : {}),
    })
  );
}

async function runCliVerify(email, code, opts) {
  const checkedEmail = assertCliWorkEmail(email);
  if (!code) {
    throw new Error("Missing 6-digit verification code. Usage: npx -y @slashml/memory --verify <email> <6-digit-code>");
  }
  const res = await fetch(`${opts.consoleUrl}/api/auth/magic-link/verify`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "User-Agent": `slashml-mcp-node/${PACKAGE_VERSION}`,
    },
    body: JSON.stringify({
      email: checkedEmail,
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
  let envSavedPath = null;
  if (opts.writeEnv || opts.isInit) {
    saveApiKeyToEnvFile(provisionedKey, process.cwd());
    envSavedPath = path.join(process.cwd(), ".env");
  }
  if (opts.isInit) {
    nativeNodeInit(opts.skill, provisionedKey, opts.repo, false);
  }
  console.log(
    JSON.stringify({
      status: "authenticated",
      email: email.trim(),
      api_key: provisionedKey,
      ...(envSavedPath ? { env_saved: envSavedPath } : {}),
      mcp_server: "ml-memory",
    })
  );
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
        path: {
          type: "string",
          description: "Repository directory path (defaults to current workspace directory)",
        },
        repo_path: {
          type: "string",
          description: "Alias for path (repository directory path)",
        },
        max_files: {
          type: "integer",
          description: "Maximum number of source files to index (default: 500)",
          default: 500,
        },
        force: {
          type: "boolean",
          description: "Force full re-index of repository files",
          default: false,
        },
      },
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
      "User-Agent": "slashml-mcp-node/1.0.0",
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

function walkCodeFiles(rootDir, maxFiles = 500, userId = "default") {
  const exts = new Set([".py", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go"]);
  const skipDirs = new Set([
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "env",
    "dist",
    "build",
    "target",
    "__pycache__",
    "upstream",
    "experiments",
    "corpus",
    "results",
    "vendor",
    "third_party",
    "coverage",
    ".next",
    ".nuxt",
    ".wrangler",
    "site",
    "artifacts",
    "tmp",
    "temp",
    "logs",
    "Pods",
    "DerivedData",
  ]);
  const lowPriorityDirs = new Set([
    "tests",
    "test",
    "__tests__",
    "audits",
    "review",
    "docs",
    "examples",
    "benchmarks",
    "scripts",
  ]);
  const docs = [];

  function walk(dir) {
    if (docs.length >= maxFiles) return;
    let entries = [];
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    entries.sort((a, b) => {
      const aLow = a.isDirectory() && lowPriorityDirs.has(a.name) ? 1 : 0;
      const bLow = b.isDirectory() && lowPriorityDirs.has(b.name) ? 1 : 0;
      if (aLow !== bLow) return aLow - bLow;
      return a.name.localeCompare(b.name);
    });
    for (const entry of entries) {
      if (docs.length >= maxFiles) break;
      if (
        entry.name.startsWith(".") ||
        skipDirs.has(entry.name) ||
        entry.name.startsWith("results-")
      ) {
        continue;
      }
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(fullPath);
      } else if (
        entry.isFile() &&
        exts.has(path.extname(entry.name)) &&
        !entry.name.endsWith(".min.js") &&
        !entry.name.endsWith(".bundle.js")
      ) {
        try {
          const stat = fs.statSync(fullPath);
          if (stat.size === 0 || stat.size > 512 * 1024) continue;
          const content = fs.readFileSync(fullPath, "utf8");
          const relPath = path.relative(rootDir, fullPath);
          docs.push({
            id: `file::${relPath}`,
            text: `[FILE] ${relPath}\n${content.slice(0, 4000)}`,
            metadata: {
              kind: "code_symbol",
              modality: "code",
              file_path: relPath,
              language: path.extname(entry.name).slice(1),
              ...(userId ? { user_id: userId } : {}),
            },
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
    const rawText = args.text !== undefined ? args.text : args.messages;
    const messagesPayload = Array.isArray(rawText)
      ? rawText
      : [
          {
            role: "user",
            content: String(rawText || ""),
            ...(args.memory_id ? { id: String(args.memory_id) } : {}),
            ...(args.metadata ? { metadata: args.metadata } : {}),
          },
        ];
    return apiRequest(opts, "POST", "/v1/memories", {
      messages: messagesPayload,
      user_id: uid,
      memory_id: args.memory_id,
      metadata: args.metadata || {},
    });
  }
  if (name === "search_memories") {
    const k = Number(args.limit || args.top_k || 5);
    return apiRequest(opts, "POST", "/v1/memories/search", {
      query: args.query,
      user_id: uid,
      limit: k,
      top_k: k,
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
    const rawPath = args.path || args.repo_path || opts.repo || ".";
    const repoPath = path.resolve(rawPath);
    const maxFiles = Math.max(1, Math.min(Number(args.max_files) || 500, 5000));
    const documents = walkCodeFiles(repoPath, maxFiles, uid);
    if (documents.length === 0) {
      return {
        status: "indexed",
        repo_path: repoPath,
        indexed_files: 0,
        ingested_count: 0,
        tokens_processed: 0,
        batches: 0,
      };
    }
    const BATCH_SIZE = 200;
    let totalIngested = 0;
    let totalTokens = 0;
    let batches = 0;
    let lastRes = {};
    for (let i = 0; i < documents.length; i += BATCH_SIZE) {
      const batch = documents.slice(i, i + BATCH_SIZE);
      const res = await apiRequest(opts, "POST", "/v1/memory/ingest", {
        documents: batch,
        update_scale_cartridge: false,
        user_id: uid,
      });
      lastRes = res || {};
      totalIngested += Number(res?.ingested_count ?? res?.count ?? batch.length);
      totalTokens += Number(res?.tokens_processed ?? 0);
      batches += 1;
    }
    return {
      ...lastRes,
      status: lastRes.status || "indexed",
      repo_path: repoPath,
      indexed_files: documents.length,
      ingested_count: totalIngested,
      tokens_processed: totalTokens,
      batches,
    };
  }
  if (name === "search_code_by_behavior") {
    const k = Number(args.top_k || args.limit || 5);
    return apiRequest(opts, "POST", "/v1/memories/search", {
      query: args.query,
      user_id: uid,
      limit: k,
      top_k: k,
      filters: { kind: "code_symbol", ...(args.language ? { language: args.language } : {}) },
    });
  }
  if (name === "find_bug_candidates") {
    const k = Number(args.top_k || args.limit || 5);
    const combinedQuery = args.stack_trace
      ? `${args.bug_description}\n${args.stack_trace}`
      : args.bug_description;
    return apiRequest(opts, "POST", "/v1/memories/search", {
      query: combinedQuery,
      user_id: uid,
      limit: k,
      top_k: k,
      filters: { kind: "code_symbol" },
    });
  }
  throw new Error(`Unknown MCP tool: ${name}`);
}

async function handleRpc(opts, req) {
  const { method, id, params } = req;
  if (
    id === undefined ||
    id === null ||
    (typeof method === "string" && method.startsWith("notifications/"))
  ) {
    return null;
  }
  if (method === "ping") return { jsonrpc: "2.0", id, result: {} };
  if (method === "initialize") {
    const clientProto =
      typeof params?.protocolVersion === "string" && params.protocolVersion
        ? params.protocolVersion
        : "2024-11-05";
    return {
      jsonrpc: "2.0",
      id,
      result: {
        protocolVersion: clientProto,
        serverInfo: { name: "ml-memory", version: PACKAGE_VERSION },
        capabilities: { tools: {} },
      },
    };
  }
  if (method === "resources/list") {
    return { jsonrpc: "2.0", id, result: { resources: [] } };
  }
  if (method === "resources/templates/list") {
    return { jsonrpc: "2.0", id, result: { resourceTemplates: [] } };
  }
  if (method === "prompts/list") {
    return { jsonrpc: "2.0", id, result: { prompts: [] } };
  }
  if (method === "tools/list") {
    const tools = opts.codeMode
      ? CODE_MODE_TOOLS
      : opts.codeOnly
        ? STANDARD_TOOLS.slice(4)
        : STANDARD_TOOLS;
    return { jsonrpc: "2.0", id, result: { tools } };
  }
  if (method === "tools/call") {
    try {
      const result = await dispatchTool(opts, params?.name, params?.arguments);
      return {
        jsonrpc: "2.0",
        id,
        result: {
          content: [{ type: "text", text: JSON.stringify(result) }],
        },
      };
    } catch (err) {
      return {
        jsonrpc: "2.0",
        id,
        result: {
          isError: true,
          content: [{ type: "text", text: String(err.message || err) }],
        },
      };
    }
  }
  return {
    jsonrpc: "2.0",
    id,
    error: { code: -32601, message: `Method not found: ${method}` },
  };
}

function main() {
  const opts = parseArgs(process.argv.slice(2));
  if (opts.isHelp) {
    printHelp();
    process.exit(0);
  }
  if (opts.isVersion) {
    console.log(PACKAGE_VERSION);
    process.exit(0);
  }
  if (opts.signupEmail) {
    runCliSignup(opts.signupEmail, opts.consoleUrl)
      .then(() => process.exit(0))
      .catch((err) => {
        console.error(`Error: ${err.message || err}`);
        process.exit(1);
      });
    return;
  }
  if (opts.verifyEmail) {
    runCliVerify(opts.verifyEmail, opts.verifyCode, opts)
      .then(() => process.exit(0))
      .catch((err) => {
        console.error(`Error: ${err.message || err}`);
        process.exit(1);
      });
    return;
  }
  if (opts.isInit) {
    nativeNodeInit(opts.skill, opts.apiKey, opts.repo, opts.writeEnv);
    process.exit(0);
  }
  const rl = readline.createInterface({ input: process.stdin, terminal: false });
  let chain = Promise.resolve();
  rl.on("line", (line) => {
    const trimmed = line.trim();
    if (!trimmed) return;
    chain = chain.then(async () => {
      try {
        const req = JSON.parse(trimmed);
        const resp = await handleRpc(opts, req);
        if (resp !== null) {
          process.stdout.write(JSON.stringify(resp) + "\n");
        }
      } catch {
        // ignore malformed JSON-RPC lines
      }
    });
  });
}

main();
