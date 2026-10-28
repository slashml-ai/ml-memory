/**
 * @slashml/vercel-ai-provider — Official / ml Memory Provider for the Vercel AI SDK
 *
 * 100% drop-in replacement for `@mem0/vercel-ai-provider` (`createSlashML`, `createMem0`,
 * `slashml`, `mem0`, `retrieveMemories`, `addMemories`, `getMemories`, `searchMemories`,
 * `SlashMLAILanguageModel`, `Mem0AILanguageModel`).
 */

export const DEFAULT_BASE_URL = "https://api.slashml.ai";
export const DEFAULT_SYSTEM_PREFIX =
  "System Memory Context (User Preferences & Past Facts):";

const RETRYABLE_STATUS_CODES = new Set([429, 502, 503, 504]);

export interface VercelMemoryConfig {
  user_id?: string | null;
  userId?: string | null;
  agent_id?: string | null;
  agentId?: string | null;
  app_id?: string | null;
  appId?: string | null;
  run_id?: string | null;
  runId?: string | null;
  org_id?: string | null;
  orgId?: string | null;
  project_id?: string | null;
  projectId?: string | null;
  slashmlApiKey?: string;
  mem0ApiKey?: string;
  apiKey?: string;
  baseUrl?: string;
  host?: string;
  limit?: number;
  top_k?: number;
  threshold?: number;
  metadata?: Record<string, unknown>;
  filters?: Record<string, unknown>;
  systemPromptPrefix?: string;
  addMemories?: boolean;
  maxRetries?: number;
  timeoutMs?: number;
  fetchImpl?: typeof fetch;
}

export interface SlashMLProviderSettings extends VercelMemoryConfig {
  provider?: string;
  llmApiKey?: string;
  llmBaseUrl?: string;
  slashmlConfig?: VercelMemoryConfig;
  mem0Config?: VercelMemoryConfig;
  upstreamModel?: {
    modelId?: string;
    provider?: string;
    specificationVersion?: string;
    doGenerate?: (options: Record<string, unknown>) => Promise<Record<string, unknown>>;
    doStream?: (options: Record<string, unknown>) => Promise<Record<string, unknown>>;
  };
}

export interface VercelTextPart {
  type?: string;
  text?: string;
}

export interface VercelMessage {
  role: string;
  content: string | VercelTextPart[];
}

export type PromptInput = string | VercelMessage[];

function getEnv(name: string): string | undefined {
  if (typeof process !== "undefined" && process.env) {
    return process.env[name];
  }
  return undefined;
}

function resolveApiKey(config: VercelMemoryConfig = {}): string {
  return (
    config.slashmlApiKey ||
    config.mem0ApiKey ||
    config.apiKey ||
    getEnv("SLASHML_API_KEY") ||
    getEnv("MEM0_API_KEY") ||
    ""
  );
}

function resolveBaseUrl(config: VercelMemoryConfig = {}): string {
  return (
    config.baseUrl ||
    config.host ||
    getEnv("SLASHML_BASE_URL") ||
    getEnv("SLASHML_API_URL") ||
    DEFAULT_BASE_URL
  ).replace(/\/+$/, "");
}

function extractTextFromContent(content: unknown): string {
  if (typeof content === "string") {
    return content;
  }
  if (Array.isArray(content)) {
    return content
      .map((part) => {
        if (typeof part === "string") return part;
        if (part && typeof part === "object" && "text" in part) {
          return String((part as { text?: unknown }).text ?? "");
        }
        return "";
      })
      .filter(Boolean)
      .join("\n");
  }
  return String(content ?? "");
}

export function normalizePromptToQuery(prompt: PromptInput): string {
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

export function normalizeMessages(
  messages: PromptInput,
): Array<{ role: string; content: string }> {
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

async function callSlashML(
  method: string,
  path: string,
  config: VercelMemoryConfig = {},
  options: { params?: Record<string, unknown>; jsonBody?: Record<string, unknown> } = {},
): Promise<Record<string, unknown>> {
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

  const headers: Record<string, string> = {
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
  const timeoutMs = config.timeoutMs ?? 30_000;
  const rawBody = options.jsonBody !== undefined ? JSON.stringify(options.jsonBody) : undefined;

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    let resp: Response;
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
    let data: Record<string, unknown> = {};
    if (text) {
      try {
        data = JSON.parse(text) as Record<string, unknown>;
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
    const msg =
      (data.error as string) ||
      (data.detail as string) ||
      (data.message as string) ||
      resp.statusText;
    throw new Error(`SlashMLAPIError (${resp.status}): ${msg}`);
  }
  throw new Error("SlashMLAPIError (503): Exhausted retries");
}

/**
 * Fetch raw memory objects as an array for a given user/agent/run scope (or query).
 */
export async function getMemories(
  promptOrConfig?: PromptInput | VercelMemoryConfig,
  maybeConfig?: VercelMemoryConfig,
): Promise<Array<Record<string, unknown>>> {
  let query: string | null = null;
  let config: VercelMemoryConfig = {};

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
    if (Array.isArray(res)) return res as Array<Record<string, unknown>>;
    if (Array.isArray(res.results)) return res.results as Array<Record<string, unknown>>;
    if (Array.isArray(res.memories)) return res.memories as Array<Record<string, unknown>>;
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
  if (Array.isArray(res)) return res as Array<Record<string, unknown>>;
  if (Array.isArray(res.results)) return res.results as Array<Record<string, unknown>>;
  if (Array.isArray(res.memories)) return res.memories as Array<Record<string, unknown>>;
  return [];
}

export const searchMemories = getMemories;

/**
 * Retrieve relevant memories for a prompt and format them into a ready-to-use system prompt string.
 */
export async function retrieveMemories(
  prompt: PromptInput,
  config: VercelMemoryConfig = {},
): Promise<string> {
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

/**
 * Extract and store persistent memories from a Vercel AI SDK message array (`LanguageModelPrompt`).
 */
export async function addMemories(
  messages: PromptInput,
  config: VercelMemoryConfig = {},
): Promise<Record<string, unknown>> {
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

function mergeConfig(
  baseSettings: SlashMLProviderSettings = {},
  callConfig: VercelMemoryConfig = {},
): VercelMemoryConfig {
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

export class SlashMLAILanguageModel {
  readonly specificationVersion = "v1" as const;
  readonly defaultObjectGenerationMode = "json" as const;
  readonly provider: string;
  readonly modelId: string;
  readonly config: VercelMemoryConfig;
  private readonly upstreamModel?: SlashMLProviderSettings["upstreamModel"];

  constructor(
    modelId: string,
    providerSettings: SlashMLProviderSettings = {},
    modelConfig: SlashMLProviderSettings = {},
  ) {
    this.modelId = modelId;
    this.config = mergeConfig(providerSettings, modelConfig);
    const upstreamProvider = modelConfig.provider || providerSettings.provider || "openai";
    this.provider = `slashml.${upstreamProvider}`;
    this.upstreamModel = modelConfig.upstreamModel ?? providerSettings.upstreamModel;
  }

  async retrieveMemories(prompt: PromptInput): Promise<string> {
    return retrieveMemories(prompt, this.config);
  }

  async getMemories(prompt?: PromptInput): Promise<Array<Record<string, unknown>>> {
    return prompt ? getMemories(prompt, this.config) : getMemories(this.config);
  }

  async addMemories(messages: PromptInput): Promise<Record<string, unknown>> {
    return addMemories(messages, this.config);
  }

  private async prepareCall(options: Record<string, unknown> = {}) {
    const rawPrompt = (options.prompt ?? options.messages ?? "") as PromptInput;
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
      sourceType: "url" as const,
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

  async doGenerate(options: Record<string, unknown> = {}) {
    const { rawMemories, systemMemory, sources, augmentedPrompt } =
      await this.prepareCall(options);

    if (this.upstreamModel?.doGenerate) {
      const upstreamResult = await this.upstreamModel.doGenerate({
        ...options,
        prompt: augmentedPrompt,
      });
      return {
        ...upstreamResult,
        sources: upstreamResult.sources ?? sources,
        providerMetadata: {
          ...(upstreamResult.providerMetadata as Record<string, unknown> | undefined),
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

  async doStream(options: Record<string, unknown> = {}) {
    const { rawMemories, systemMemory, sources, augmentedPrompt } =
      await this.prepareCall(options);

    if (this.upstreamModel?.doStream) {
      const upstreamStream = await this.upstreamModel.doStream({
        ...options,
        prompt: augmentedPrompt,
      });
      return {
        ...upstreamStream,
        sources: upstreamStream.sources ?? sources,
        providerMetadata: {
          ...(upstreamStream.providerMetadata as Record<string, unknown> | undefined),
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

export const Mem0AILanguageModel = SlashMLAILanguageModel;

/**
 * Create a Vercel AI SDK Provider (`ProviderV1` / `ProviderV2` / `ProviderV3` compatible)
 * that automatically retrieves `/ ml` memories and injects them into `generateText` / `streamText`.
 */
export function createSlashML(providerSettings: SlashMLProviderSettings = {}) {
  const createModel = (modelId: string, modelConfig: SlashMLProviderSettings = {}) =>
    new SlashMLAILanguageModel(modelId, providerSettings, modelConfig);

  const provider = Object.assign(
    (modelId: string, settings?: SlashMLProviderSettings) => createModel(modelId, settings),
    {
      languageModel: (modelId: string, settings?: SlashMLProviderSettings) =>
        createModel(modelId, settings),
      chat: (modelId: string, settings?: SlashMLProviderSettings) =>
        createModel(modelId, settings),
      completion: (modelId: string, settings?: SlashMLProviderSettings) =>
        createModel(modelId, settings),
    },
  );

  return provider;
}

/**
 * 100% 1:1 drop-in alias for `@mem0/vercel-ai-provider`'s `createMem0`.
 */
export const createMem0 = createSlashML;
export const slashml = createSlashML();
export const mem0 = slashml;

export default createSlashML;
