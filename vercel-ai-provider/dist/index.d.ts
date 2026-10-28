export declare const DEFAULT_BASE_URL = "https://api.slashml.ai";
export declare const DEFAULT_SYSTEM_PREFIX = "System Memory Context (User Preferences & Past Facts):";

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

export declare function normalizePromptToQuery(prompt: PromptInput): string;
export declare function normalizeMessages(
  messages: PromptInput,
): Array<{ role: string; content: string }>;

export declare function getMemories(
  promptOrConfig?: PromptInput | VercelMemoryConfig,
  maybeConfig?: VercelMemoryConfig,
): Promise<Array<Record<string, unknown>>>;

export declare const searchMemories: typeof getMemories;

export declare function retrieveMemories(
  prompt: PromptInput,
  config?: VercelMemoryConfig,
): Promise<string>;

export declare function addMemories(
  messages: PromptInput,
  config?: VercelMemoryConfig,
): Promise<Record<string, unknown>>;

export declare class SlashMLAILanguageModel {
  readonly specificationVersion = "v1";
  readonly defaultObjectGenerationMode = "json";
  readonly provider: string;
  readonly modelId: string;
  readonly config: VercelMemoryConfig;
  constructor(
    modelId: string,
    providerSettings?: SlashMLProviderSettings,
    modelConfig?: SlashMLProviderSettings,
  );
  retrieveMemories(prompt: PromptInput): Promise<string>;
  getMemories(prompt?: PromptInput): Promise<Array<Record<string, unknown>>>;
  addMemories(messages: PromptInput): Promise<Record<string, unknown>>;
  doGenerate(options?: Record<string, unknown>): Promise<Record<string, unknown>>;
  doStream(options?: Record<string, unknown>): Promise<Record<string, unknown>>;
}

export declare const Mem0AILanguageModel: typeof SlashMLAILanguageModel;

export declare function createSlashML(providerSettings?: SlashMLProviderSettings): {
  (modelId: string, settings?: SlashMLProviderSettings): SlashMLAILanguageModel;
  languageModel: (modelId: string, settings?: SlashMLProviderSettings) => SlashMLAILanguageModel;
  chat: (modelId: string, settings?: SlashMLProviderSettings) => SlashMLAILanguageModel;
  completion: (modelId: string, settings?: SlashMLProviderSettings) => SlashMLAILanguageModel;
};

export declare const createMem0: typeof createSlashML;
export declare const slashml: ReturnType<typeof createSlashML>;
export declare const mem0: ReturnType<typeof createSlashML>;

export default createSlashML;
