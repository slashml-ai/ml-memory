/**
 * @slashml/vercel-ai-provider -- Official / ml Memory Provider for the Vercel AI SDK
 *
 * 100% drop-in replacement for `@mem0/vercel-ai-provider` (`createSlashML`, `createMem0`,
 * `slashml`, `mem0`, `retrieveMemories`, `addMemories`, `getMemories`, `searchMemories`,
 * `SlashMLAILanguageModel`, `Mem0AILanguageModel`).
 */
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
export declare function normalizeMessages(messages: PromptInput): Array<{
    role: string;
    content: string;
}>;
/**
 * Fetch raw memory objects as an array for a given user/agent/run scope (or query).
 */
export declare function getMemories(promptOrConfig?: PromptInput | VercelMemoryConfig, maybeConfig?: VercelMemoryConfig): Promise<Array<Record<string, unknown>>>;
export declare const searchMemories: typeof getMemories;
/**
 * Retrieve relevant memories for a prompt and format them into a ready-to-use system prompt string.
 */
export declare function retrieveMemories(prompt: PromptInput, config?: VercelMemoryConfig): Promise<string>;
/**
 * Extract and store persistent memories from a Vercel AI SDK message array (`LanguageModelPrompt`).
 */
export declare function addMemories(messages: PromptInput, config?: VercelMemoryConfig): Promise<Record<string, unknown>>;
export declare class SlashMLAILanguageModel {
    readonly specificationVersion: "v1";
    readonly defaultObjectGenerationMode: "json";
    readonly provider: string;
    readonly modelId: string;
    readonly config: VercelMemoryConfig;
    private readonly upstreamModel?;
    constructor(modelId: string, providerSettings?: SlashMLProviderSettings, modelConfig?: SlashMLProviderSettings);
    retrieveMemories(prompt: PromptInput): Promise<string>;
    getMemories(prompt?: PromptInput): Promise<Array<Record<string, unknown>>>;
    addMemories(messages: PromptInput): Promise<Record<string, unknown>>;
    private prepareCall;
    doGenerate(options?: Record<string, unknown>): Promise<{
        sources: {};
        providerMetadata: {
            slashml: {
                memories: Record<string, unknown>[];
                systemMemory: string;
            };
        };
        text?: undefined;
        finishReason?: undefined;
        usage?: undefined;
        rawCall?: undefined;
    } | {
        text: string;
        finishReason: string;
        usage: {
            promptTokens: number;
            completionTokens: number;
        };
        rawCall: {
            rawPrompt: unknown;
            rawSettings: {};
        };
        sources: {
            sourceType: "url";
            id: string;
            url: string;
            title: string;
        }[];
        providerMetadata: {
            slashml: {
                memories: Record<string, unknown>[];
                systemMemory: string;
            };
        };
    }>;
    doStream(options?: Record<string, unknown>): Promise<{
        rawCall?: undefined;
        sources: {};
        providerMetadata: {
            slashml: {
                memories: Record<string, unknown>[];
                systemMemory: string;
            };
        };
        stream?: undefined;
    } | {
        stream: {
            [Symbol.asyncIterator](): AsyncGenerator<{
                finishReason?: undefined;
                usage?: undefined;
                type: string;
                textDelta: string;
            } | {
                textDelta?: undefined;
                type: string;
                finishReason: string;
                usage: {
                    promptTokens: number;
                    completionTokens: number;
                };
            }, void, unknown>;
        };
        rawCall: {
            rawPrompt: unknown;
            rawSettings: {};
        };
        sources: {
            sourceType: "url";
            id: string;
            url: string;
            title: string;
        }[];
        providerMetadata: {
            slashml: {
                memories: Record<string, unknown>[];
                systemMemory: string;
            };
        };
    }>;
}
export declare const Mem0AILanguageModel: typeof SlashMLAILanguageModel;
/**
 * Create a Vercel AI SDK Provider (`ProviderV1` / `ProviderV2` / `ProviderV3` compatible)
 * that automatically retrieves `/ ml` memories and injects them into `generateText` / `streamText`.
 */
export declare function createSlashML(providerSettings?: SlashMLProviderSettings): ((modelId: string, settings?: SlashMLProviderSettings) => SlashMLAILanguageModel) & {
    languageModel: (modelId: string, settings?: SlashMLProviderSettings) => SlashMLAILanguageModel;
    chat: (modelId: string, settings?: SlashMLProviderSettings) => SlashMLAILanguageModel;
    completion: (modelId: string, settings?: SlashMLProviderSettings) => SlashMLAILanguageModel;
};
/**
 * 100% 1:1 drop-in alias for `@mem0/vercel-ai-provider`'s `createMem0`.
 */
export declare const createMem0: typeof createSlashML;
export declare const slashml: ((modelId: string, settings?: SlashMLProviderSettings) => SlashMLAILanguageModel) & {
    languageModel: (modelId: string, settings?: SlashMLProviderSettings) => SlashMLAILanguageModel;
    chat: (modelId: string, settings?: SlashMLProviderSettings) => SlashMLAILanguageModel;
    completion: (modelId: string, settings?: SlashMLProviderSettings) => SlashMLAILanguageModel;
};
export declare const mem0: ((modelId: string, settings?: SlashMLProviderSettings) => SlashMLAILanguageModel) & {
    languageModel: (modelId: string, settings?: SlashMLProviderSettings) => SlashMLAILanguageModel;
    chat: (modelId: string, settings?: SlashMLProviderSettings) => SlashMLAILanguageModel;
    completion: (modelId: string, settings?: SlashMLProviderSettings) => SlashMLAILanguageModel;
};
export default createSlashML;
