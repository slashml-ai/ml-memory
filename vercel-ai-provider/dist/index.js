"use strict";

const DEFAULT_BASE_URL = "https://api.slashml.ai";
const DEFAULT_SYSTEM_PREFIX =
  "System Memory Context (User Preferences & Past Facts):";
const RETRYABLE_STATUS_CODES = new Set([429, 502, 503, 504]);

function getEnv(name) {
  if (typeof process !== "undefined" && process.env) {
    return process.env[name];
  }
  return undefined;
}

function resolveApiKey(config = {}) {
  return (
    config.slashmlApiKey ||
    config.mem0ApiKey ||
    config.apiKey ||
    getEnv("SLASHML_API_KEY") ||
    getEnv("MEM0_API_KEY") ||
    ""
  );
}

function resolveBaseUrl(config = {}) {
  return (
    config.baseUrl ||
    config.host ||
    getEnv("SLASHML_BASE_URL") ||
    getEnv("SLASHML_API_URL") ||
    DEFAULT_BASE_URL
  ).replace(/\/+$/, "");
}

function extractTextFromContent(content) {
  if (typeof content === "string") {
    return content;
  }
  if (Array.isArray(content)) {
    return content
      .map((part) => {
        if (typeof part === "string") return part;
        if (part && typeof part === "object" && "text" in part) {
          return String(part.text ?? "");
        }
        return "";
      })
      .filter(Boolean)
      .join("\n");
  }
  return String(content ?? "");
}

function normalizePromptToQuery(prompt) {
  if (typeof prompt === "string") {
    return prompt.trim();
  }
  if (Array.isArray(prompt)) {
    const userMessages = prompt.filter((m) => m && m.role === "user");
    const target = userMessages.length > 0 ? userMessages : prompt;
    return target
      .map((m) => extractTextFromContent(m.content))
      .filter(Boolean)
      .join("\n")
      .trim();
  }
  return String(prompt ?? "").trim();
}

function normalizeMessages(messages) {
  if (typeof messages === "string") {
    return [{ role: "user", content: messages }];
  }
  if (Array.isArray(messages)) {
    return messages.map((m) => ({
      role: m.role || "user",
      content: extractTextFromContent(m.content),
    }));
  }
  return [];
}

async function callSlashML(method, path, config = {}, options = {}) {
  const apiKey = resolveApiKey(config);
  if (!apiKey) {
    throw new Error(
      "SlashMLAPIError (401): Missing API key. Set SLASHML_API_KEY (or MEM0_API_KEY) or pass slashmlApiKey / mem0ApiKey.",
    );
  }
  const baseUrl = resolveBaseUrl(config);
  let url = `${baseUrl}${path.startsWith("/") ? path : `/${path}`}`;
  if (options.params) {
    const sp = new URLSearchParams();
    for (const [k, v] of Object.entries(options.params)) {
      if (v !== undefined && v !== null) {
        sp.set(k, String(v));
      }
    }
    const qs = sp.toString();
    if (qs) url = `${url}?${qs}`;
  }

  const headers = {
    Accept: "application/json",
    "Content-Type": "application/json",
    "User-Agent": "slashml-vercel-ai-provider/1.0.0",
    Authorization: `Bearer ${apiKey}`,
    "X-API-Key": apiKey,
  };
  const orgId = config.org_id ?? config.orgId ?? getEnv("SLASHML_ORG_ID");
  const projectId = config.project_id ?? config.projectId ?? getEnv("SLASHML_PROJECT_ID");
  if (orgId) headers["X-SlashML-Org-Id"] = String(orgId);
  if (projectId) headers["X-SlashML-Project-Id"] = String(projectId);

  const fetchFn = config.fetchImpl ?? globalThis.fetch;
  const maxRetries = config.maxRetries ?? 3;
  const timeoutMs = config.timeoutMs ?? 30000;
  const rawBody = options.jsonBody !== undefined ? JSON.stringify(options.jsonBody) : undefined;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    let resp;
    try {
      resp = await fetchFn(url, {
        method: method.toUpperCase(),
        headers,
        body: rawBody,
        signal: controller.signal,
      });
    } catch (err) {
      clearTimeout(timer);
      if (attempt < maxRetries) {
        await new Promise((r) => setTimeout(r, Math.min(2000, 100 * 2 ** attempt)));
        continue;
      }
      throw new Error(
        `SlashMLAPIError (503): Network error contacting SlashML API at ${url}: ${String(err)}`,
      );
    }
    clearTimeout(timer);

    const text = await resp.text();
    let data = {};
    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = { raw: text };
      }
    }
    if (resp.ok) {
      return data;
    }
    if (RETRYABLE_STATUS_CODES.has(resp.status) && attempt < maxRetries) {
      await new Promise((r) => setTimeout(r, Math.min(2000, 100 * 2 ** attempt)));
      continue;
    }
    const msg = data.error || data.detail || data.message || resp.statusText;
    throw new Error(`SlashMLAPIError (${resp.status}): ${msg}`);
  }
  throw new Error("SlashMLAPIError (503): Exhausted retries");
}

async function getMemories(promptOrConfig, maybeConfig) {
  let query = null;
  let config = {};

  if (typeof promptOrConfig === "string" || Array.isArray(promptOrConfig)) {
    query = normalizePromptToQuery(promptOrConfig);
    config = maybeConfig ?? {};
  } else if (promptOrConfig && typeof promptOrConfig === "object") {
    config = promptOrConfig;
  }

  const userId = config.user_id ?? config.userId ?? undefined;
  const agentId = config.agent_id ?? config.agentId ?? undefined;
  const appId = config.app_id ?? config.appId ?? undefined;
  const runId = config.run_id ?? config.runId ?? undefined;
  const limit = config.top_k ?? config.limit ?? 5;

  if (query && query.length > 0) {
    const res = await callSlashML("POST", "/v1/memories/search", config, {
      jsonBody: {
        query,
        user_id: userId ?? null,
        agent_id: agentId ?? null,
        app_id: appId ?? null,
        run_id: runId ?? null,
        limit,
        top_k: limit,
        filters: config.filters ?? config.metadata ?? null,
        threshold: config.threshold ?? null,
      },
    });
    if (Array.isArray(res)) return res;
    if (Array.isArray(res.results)) return res.results;
    if (Array.isArray(res.memories)) return res.memories;
    return [];
  }

  const res = await callSlashML("GET", "/v1/memories", config, {
    params: {
      user_id: userId,
      agent_id: agentId,
      app_id: appId,
      run_id: runId,
      limit: config.limit ?? 100,
    },
  });
  if (Array.isArray(res)) return res;
  if (Array.isArray(res.results)) return res.results;
  if (Array.isArray(res.memories)) return res.memories;
  return [];
}

const searchMemories = getMemories;

async function retrieveMemories(prompt, config = {}) {
  const memories = await getMemories(prompt, config);
  if (!memories || memories.length === 0) {
    return "";
  }
  const prefix = config.systemPromptPrefix ?? DEFAULT_SYSTEM_PREFIX;
  const bulletLines = memories
    .map((m) => String(m.memory ?? m.text ?? m.content ?? "").trim())
    .filter(Boolean)
    .map((line) => `- ${line}`);
  if (bulletLines.length === 0) {
    return "";
  }
  return `${prefix}\n${bulletLines.join("\n")}`;
}

async function addMemories(messages, config = {}) {
  const normalized = normalizeMessages(messages);
  return callSlashML("POST", "/v1/memories", config, {
    jsonBody: {
      messages: normalized,
      user_id: config.user_id ?? config.userId ?? null,
      agent_id: config.agent_id ?? config.agentId ?? null,
      app_id: config.app_id ?? config.appId ?? null,
      run_id: config.run_id ?? config.runId ?? null,
      metadata: config.metadata ?? {},
      infer: true,
    },
  });
}

function mergeConfig(baseSettings = {}, callConfig = {}) {
  const nested = baseSettings.slashmlConfig ?? baseSettings.mem0Config ?? {};
  return {
    ...baseSettings,
    ...nested,
    ...callConfig,
    slashmlApiKey:
      callConfig.slashmlApiKey ||
      callConfig.mem0ApiKey ||
      callConfig.apiKey ||
      baseSettings.slashmlApiKey ||
      baseSettings.mem0ApiKey ||
      baseSettings.apiKey ||
      nested.slashmlApiKey ||
      nested.mem0ApiKey ||
      nested.apiKey ||
      getEnv("SLASHML_API_KEY") ||
      getEnv("MEM0_API_KEY"),
  };
}

class SlashMLAILanguageModel {
  constructor(modelId, providerSettings = {}, modelConfig = {}) {
    this.specificationVersion = "v1";
    this.defaultObjectGenerationMode = "json";
    this.modelId = modelId;
    this.config = mergeConfig(providerSettings, modelConfig);
    const upstreamProvider = modelConfig.provider || providerSettings.provider || "openai";
    this.provider = `slashml.${upstreamProvider}`;
    this.upstreamModel = modelConfig.upstreamModel ?? providerSettings.upstreamModel;
  }

  async retrieveMemories(prompt) {
    return retrieveMemories(prompt, this.config);
  }

  async getMemories(prompt) {
    return prompt ? getMemories(prompt, this.config) : getMemories(this.config);
  }

  async addMemories(messages) {
    return addMemories(messages, this.config);
  }

  async _prepareCall(options = {}) {
    const rawPrompt = options.prompt ?? options.messages ?? "";
    const rawMemories = await getMemories(rawPrompt, this.config);
    const systemMemory =
      rawMemories.length > 0
        ? `${this.config.systemPromptPrefix ?? DEFAULT_SYSTEM_PREFIX}\n${rawMemories
            .map((m) => `- ${String(m.memory ?? m.text ?? "")}`)
            .join("\n")}`
        : "";

    if (this.config.addMemories && rawPrompt) {
      await addMemories(rawPrompt, this.config);
    }

    const sources = rawMemories.map((m, idx) => ({
      sourceType: "url",
      id: String(m.id ?? `mem_${idx}`),
      url: `slashml://memory/${String(m.id ?? idx)}`,
      title: String(m.memory ?? m.text ?? ""),
    }));

    const augmentedPrompt = Array.isArray(options.prompt)
      ? systemMemory
        ? [{ role: "system", content: systemMemory }, ...options.prompt]
        : options.prompt
      : systemMemory
        ? [
            { role: "system", content: systemMemory },
            { role: "user", content: [{ type: "text", text: String(rawPrompt) }] },
          ]
        : options.prompt;

    return { rawMemories, systemMemory, sources, augmentedPrompt };
  }

  async doGenerate(options = {}) {
    const { rawMemories, systemMemory, sources, augmentedPrompt } =
      await this._prepareCall(options);

    if (this.upstreamModel?.doGenerate) {
      const upstreamResult = await this.upstreamModel.doGenerate({
        ...options,
        prompt: augmentedPrompt,
      });
      return {
        ...upstreamResult,
        sources: upstreamResult.sources ?? sources,
        providerMetadata: {
          ...upstreamResult.providerMetadata,
          slashml: { memories: rawMemories, systemMemory },
        },
      };
    }

    return {
      text: systemMemory
        ? `[Memory-Augmented Response (${this.modelId})] ${systemMemory}`
        : `[Response (${this.modelId})]`,
      finishReason: "stop",
      usage: { promptTokens: 16, completionTokens: 16 },
      rawCall: { rawPrompt: augmentedPrompt, rawSettings: {} },
      sources,
      providerMetadata: {
        slashml: { memories: rawMemories, systemMemory },
      },
    };
  }

  async doStream(options = {}) {
    const { rawMemories, systemMemory, sources, augmentedPrompt } =
      await this._prepareCall(options);

    if (this.upstreamModel?.doStream) {
      const upstreamStream = await this.upstreamModel.doStream({
        ...options,
        prompt: augmentedPrompt,
      });
      return {
        ...upstreamStream,
        sources: upstreamStream.sources ?? sources,
        providerMetadata: {
          ...upstreamStream.providerMetadata,
          slashml: { memories: rawMemories, systemMemory },
        },
      };
    }

    const text = systemMemory
      ? `[Memory-Augmented Response (${this.modelId})] ${systemMemory}`
      : `[Response (${this.modelId})]`;
    const chunks = [
      { type: "text-delta", textDelta: text },
      {
        type: "finish",
        finishReason: "stop",
        usage: { promptTokens: 16, completionTokens: 16 },
      },
    ];
    return {
      stream: {
        async *[Symbol.asyncIterator]() {
          for (const chunk of chunks) {
            yield chunk;
          }
        },
      },
      rawCall: { rawPrompt: augmentedPrompt, rawSettings: {} },
      sources,
      providerMetadata: {
        slashml: { memories: rawMemories, systemMemory },
      },
    };
  }
}

const Mem0AILanguageModel = SlashMLAILanguageModel;

function createSlashML(providerSettings = {}) {
  const createModel = (modelId, modelConfig = {}) =>
    new SlashMLAILanguageModel(modelId, providerSettings, modelConfig);

  const provider = Object.assign(
    (modelId, settings) => createModel(modelId, settings),
    {
      languageModel: (modelId, settings) => createModel(modelId, settings),
      chat: (modelId, settings) => createModel(modelId, settings),
      completion: (modelId, settings) => createModel(modelId, settings),
    },
  );

  return provider;
}

const createMem0 = createSlashML;
const slashml = createSlashML();
const mem0 = slashml;

module.exports = {
  DEFAULT_BASE_URL,
  DEFAULT_SYSTEM_PREFIX,
  normalizePromptToQuery,
  normalizeMessages,
  getMemories,
  searchMemories,
  retrieveMemories,
  addMemories,
  SlashMLAILanguageModel,
  Mem0AILanguageModel,
  createSlashML,
  createMem0,
  slashml,
  mem0,
  default: createSlashML,
};
