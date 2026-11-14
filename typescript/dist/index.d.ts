/**
 * @slashml/memory -- Official HTTP TypeScript / Node.js SDK for / ml (https://api.slashml.ai)
 *
 * 100% drop-in replacement for `mem0ai` (`MemoryClient`, `AsyncMemoryClient`, `Memory`, `AsyncMemory`).
 */
export declare const DEFAULT_BASE_URL = "https://api.slashml.ai";
export declare const DEFAULT_MODEL = "slashml-1.5-fast";
export declare const DEFAULT_TIMEOUT_MS = 30000;
export type RedactBucket = "SECRET" | "PCI_FINANCIAL" | "PII" | "PHI" | "COMMERCIAL_MNPI" | "LEGAL_HR" | "SECURITY_EXPLOIT";
export type RedactPreset = "off" | "tier1_secrets" | "soc2_coding" | "gdpr" | "hipaa" | "enterprise_strict";
export type RedactPolicy = RedactPreset | RedactBucket[] | string | string[];
export type RedactScope = "memorize_and_recall" | "recall_only";
export type AccessMode = "read_write" | "read_only";
export interface MemoryClientOptions {
    apiKey?: string;
    api_key?: string;
    mem0ApiKey?: string;
    baseUrl?: string;
    base_url?: string;
    host?: string;
    orgId?: string;
    org_id?: string;
    projectId?: string;
    project_id?: string;
    agentId?: string;
    agent_id?: string;
    callerAgentId?: string;
    caller_agent_id?: string;
    redactPolicy?: RedactPolicy;
    redact_policy?: RedactPolicy;
    redactScope?: RedactScope;
    redact_scope?: RedactScope;
    model?: string;
    timeoutMs?: number;
    fetchImpl?: typeof fetch;
}
export interface MemoryFilters {
    user_id?: string | null;
    userId?: string | null;
    agent_id?: string | null;
    agentId?: string | null;
    app_id?: string | null;
    appId?: string | null;
    run_id?: string | null;
    runId?: string | null;
    metadata?: Record<string, unknown> | null;
    filters?: Record<string, unknown> | null;
    redact_policy?: RedactPolicy;
    redactPolicy?: RedactPolicy;
    redact_scope?: RedactScope;
    redactScope?: RedactScope;
    caller_agent_id?: string | null;
    callerAgentId?: string | null;
}
export interface AddMemoryOptions extends MemoryFilters {
    infer?: boolean;
    memory_id?: string;
    memoryId?: string;
}
export interface SearchMemoryOptions extends MemoryFilters {
    limit?: number;
    top_k?: number;
    topK?: number;
    threshold?: number;
}
export interface IngestOptions {
    namespace?: string;
    model?: string;
    metadata?: Record<string, unknown>;
    redact_policy?: RedactPolicy;
    redactPolicy?: RedactPolicy;
    redact_scope?: RedactScope;
    redactScope?: RedactScope;
    caller_agent_id?: string;
    callerAgentId?: string;
}
export interface QueryOptions {
    namespace?: string;
    model?: string;
    top_k?: number;
    redact_policy?: RedactPolicy;
    redactPolicy?: RedactPolicy;
    redact_scope?: RedactScope;
    redactScope?: RedactScope;
    caller_agent_id?: string;
    callerAgentId?: string;
}
export interface ForgetOptions {
    namespace?: string;
    purge?: boolean;
    reason?: string;
    caller_agent_id?: string;
    callerAgentId?: string;
}
export interface RedactOptions {
    text?: string;
    memory_id?: string;
    memoryId?: string;
    redact_policy?: RedactPolicy;
    redactPolicy?: RedactPolicy;
    explicit_spans?: Array<Record<string, unknown>>;
    explicitSpans?: Array<Record<string, unknown>>;
    dry_run?: boolean;
    dryRun?: boolean;
    caller_agent_id?: string;
    callerAgentId?: string;
}
export interface PurgeOptions {
    dry_run?: boolean;
    dryRun?: boolean;
    reason?: string;
    caller_agent_id?: string;
    callerAgentId?: string;
}
export interface UndoOptions {
    caller_agent_id?: string;
    callerAgentId?: string;
}
export interface UpdateRedactionPolicyOptions {
    redact_policy?: RedactPolicy;
    redactPolicy?: RedactPolicy;
    redact_scope?: RedactScope;
    redactScope?: RedactScope;
    access_mode?: AccessMode;
    accessMode?: AccessMode;
    allow_write?: boolean;
    allowWrite?: boolean;
}
export interface PreviewRedactionOptions {
    text?: string;
    agent_id?: string;
    agentId?: string;
    redact_policy?: RedactPolicy;
    redactPolicy?: RedactPolicy;
    redact_scope?: RedactScope;
    redactScope?: RedactScope;
}
export interface ConfigureAgentOptions {
    agent_id?: string;
    agentId?: string;
    name?: string | null;
    access_mode?: AccessMode;
    accessMode?: AccessMode;
    allow_write?: boolean;
    allowWrite?: boolean;
    redact_policy?: RedactPolicy;
    redactPolicy?: RedactPolicy;
    redact_scope?: RedactScope;
    redactScope?: RedactScope;
    inherit_policy?: boolean;
    inheritPolicy?: boolean;
    inherit_access?: boolean;
    inheritAccess?: boolean;
    metadata?: Record<string, unknown>;
}
export interface InterveneOptions {
    hook_event_name?: string;
    hookEventName?: string;
    prompt?: string;
    text?: string;
    last_assistant_message?: string | null;
    lastAssistantMessage?: string | null;
    stop_hook_active?: boolean;
    stopHookActive?: boolean;
    whispered_memory_ids?: string[] | null;
    whisperedMemoryIds?: string[] | null;
    tool_name?: string | null;
    toolName?: string | null;
    tool_input?: Record<string, unknown> | null;
    toolInput?: Record<string, unknown> | null;
    tool_response?: Record<string, unknown> | null;
    toolResponse?: Record<string, unknown> | null;
    user_id?: string | null;
    userId?: string | null;
    project_id?: string | null;
    projectId?: string | null;
    session_id?: string | null;
    sessionId?: string | null;
    model?: string;
    commit_writes?: boolean;
    commitWrites?: boolean;
    top_k?: number;
    topK?: number;
    redact_policy?: RedactPolicy;
    redactPolicy?: RedactPolicy;
    redact_scope?: RedactScope;
    redactScope?: RedactScope;
    caller_agent_id?: string | null;
    callerAgentId?: string | null;
    client_raw_tokens_delta?: number;
    clientRawTokensDelta?: number;
    client_dropped_tokens_delta?: number;
    clientDroppedTokensDelta?: number;
    client_dropped_events_delta?: number;
    clientDroppedEventsDelta?: number;
}
export interface StatusOptions {
    user_id?: string | null;
    userId?: string | null;
    client_raw_tokens_delta?: number;
    clientRawTokensDelta?: number;
    client_dropped_tokens_delta?: number;
    clientDroppedTokensDelta?: number;
    client_dropped_events_delta?: number;
    clientDroppedEventsDelta?: number;
}
export declare class SlashMLAPIError extends Error {
    readonly statusCode: number;
    readonly status: number;
    readonly details: Record<string, unknown>;
    constructor(statusCode: number, message: string, details?: Record<string, unknown>);
}
export declare class ProjectManager {
    private readonly client;
    constructor(client: MemoryClient);
    get(fieldsOrOptions?: string[] | {
        fields?: string[];
    }): Promise<Record<string, unknown>>;
    create(nameOrOptions: string | {
        name: string;
        description?: string;
        [k: string]: unknown;
    }, description?: string, extra?: Record<string, unknown>): Promise<Record<string, unknown>>;
    update(settings?: Record<string, unknown>): Promise<Record<string, unknown>>;
    delete(): Promise<Record<string, unknown>>;
    getMembers(): Promise<Record<string, unknown>>;
    get_members(): Promise<Record<string, unknown>>;
    addMember(emailOrOptions: string | {
        email: string;
        role?: string;
    }, role?: string): Promise<Record<string, unknown>>;
    add_member(emailOrOptions: string | {
        email: string;
        role?: string;
    }, role?: string): Promise<Record<string, unknown>>;
    removeMember(emailOrOptions: string | {
        email: string;
    }): Promise<Record<string, unknown>>;
    remove_member(emailOrOptions: string | {
        email: string;
    }): Promise<Record<string, unknown>>;
}
export declare class AgentsManager {
    private readonly client;
    constructor(client: MemoryClient);
    list(): Promise<Record<string, unknown>>;
    configure(agentIdOrOptions: string | ConfigureAgentOptions, options?: ConfigureAgentOptions): Promise<Record<string, unknown>>;
    upsert(agentIdOrOptions: string | ConfigureAgentOptions, options?: ConfigureAgentOptions): Promise<Record<string, unknown>>;
    delete(agentId: string): Promise<Record<string, unknown>>;
}
export declare class MemoryClient {
    readonly apiKey: string;
    readonly baseUrl: string;
    readonly orgId: string | null;
    readonly projectId: string | null;
    readonly agentId: string | null;
    readonly callerAgentId: string | null;
    readonly redactPolicy: string | string[] | null;
    readonly redactScope: RedactScope | null;
    readonly model: string;
    readonly timeoutMs: number;
    readonly project: ProjectManager;
    readonly agents: AgentsManager;
    private readonly fetchImpl;
    constructor(options?: MemoryClientOptions);
    private applyLifecycleDefaults;
    request<T = Record<string, unknown>>(method: string, path: string, options?: {
        params?: Record<string, unknown>;
        jsonBody?: Record<string, unknown>;
        headers?: Record<string, string>;
    }): Promise<T>;
    ingest(documents: string | string[], options?: IngestOptions): Promise<Record<string, unknown>>;
    query(prompt: string, options?: QueryOptions): Promise<Record<string, unknown>>;
    forget(target: string, options?: ForgetOptions): Promise<Record<string, unknown>>;
    redact(textOrOptions: string | RedactOptions, options?: RedactOptions): Promise<Record<string, unknown>>;
    purge(memoryIds: string | string[], options?: PurgeOptions): Promise<Record<string, unknown>>;
    undo(undoToken: string, options?: UndoOptions): Promise<Record<string, unknown>>;
    getRedactionPolicy(): Promise<Record<string, unknown>>;
    get_redaction_policy(): Promise<Record<string, unknown>>;
    updateRedactionPolicy(options?: UpdateRedactionPolicyOptions): Promise<Record<string, unknown>>;
    update_redaction_policy(options?: UpdateRedactionPolicyOptions): Promise<Record<string, unknown>>;
    previewRedaction(textOrOptions: string | PreviewRedactionOptions, options?: PreviewRedactionOptions): Promise<Record<string, unknown>>;
    preview_redaction(textOrOptions: string | PreviewRedactionOptions, options?: PreviewRedactionOptions): Promise<Record<string, unknown>>;
    listAgents(): Promise<Record<string, unknown>>;
    listAgentPolicies(): Promise<Record<string, unknown>>;
    list_agents(): Promise<Record<string, unknown>>;
    list_agent_policies(): Promise<Record<string, unknown>>;
    configureAgent(agentIdOrOptions: string | ConfigureAgentOptions, options?: ConfigureAgentOptions): Promise<Record<string, unknown>>;
    upsertAgentPolicy(agentIdOrOptions: string | ConfigureAgentOptions, options?: ConfigureAgentOptions): Promise<Record<string, unknown>>;
    configure_agent(agentIdOrOptions: string | ConfigureAgentOptions, options?: ConfigureAgentOptions): Promise<Record<string, unknown>>;
    upsert_agent_policy(agentIdOrOptions: string | ConfigureAgentOptions, options?: ConfigureAgentOptions): Promise<Record<string, unknown>>;
    deleteAgent(agentId: string): Promise<Record<string, unknown>>;
    deleteAgentPolicy(agentId: string): Promise<Record<string, unknown>>;
    delete_agent(agentId: string): Promise<Record<string, unknown>>;
    delete_agent_policy(agentId: string): Promise<Record<string, unknown>>;
    intervene(textOrPayload: string | InterveneOptions, options?: InterveneOptions): Promise<Record<string, unknown>>;
    status(options?: StatusOptions): Promise<Record<string, unknown>>;
    add(messages: string | Array<Record<string, unknown>> | Record<string, unknown>, options?: AddMemoryOptions): Promise<Record<string, unknown>>;
    search(queryOrOptions: string | ({
        query: string;
    } & SearchMemoryOptions), options?: SearchMemoryOptions): Promise<Record<string, unknown>>;
    recall(queryOrOptions: string | ({
        query: string;
    } & SearchMemoryOptions), options?: SearchMemoryOptions): Promise<Record<string, unknown>>;
    getAll(options?: MemoryFilters & {
        limit?: number;
    }): Promise<Record<string, unknown>>;
    get_all(options?: MemoryFilters & {
        limit?: number;
    }): Promise<Record<string, unknown>>;
    get(memoryId: string, options?: {
        redact_policy?: RedactPolicy;
        redactPolicy?: RedactPolicy;
        redact_scope?: RedactScope;
        redactScope?: RedactScope;
        caller_agent_id?: string;
        callerAgentId?: string;
    }): Promise<Record<string, unknown> | null>;
    update(memoryId: string, data: string | {
        text?: string;
        metadata?: Record<string, unknown>;
        redact_policy?: RedactPolicy;
        redactPolicy?: RedactPolicy;
        redact_scope?: RedactScope;
        redactScope?: RedactScope;
        caller_agent_id?: string;
        callerAgentId?: string;
    }, options?: {
        redact_policy?: RedactPolicy;
        redactPolicy?: RedactPolicy;
        redact_scope?: RedactScope;
        redactScope?: RedactScope;
        caller_agent_id?: string;
        callerAgentId?: string;
    }): Promise<Record<string, unknown>>;
    delete(memoryId: string, options?: {
        caller_agent_id?: string;
        callerAgentId?: string;
    }): Promise<Record<string, unknown>>;
    deleteAll(options?: MemoryFilters): Promise<Record<string, unknown>>;
    delete_all(options?: MemoryFilters): Promise<Record<string, unknown>>;
    reset(): Promise<Record<string, unknown>>;
    history(memoryId: string): Promise<Array<Record<string, unknown>>>;
    batchUpdate(memories: Array<Record<string, unknown>>, options?: {
        redact_policy?: RedactPolicy;
        redactPolicy?: RedactPolicy;
        redact_scope?: RedactScope;
        redactScope?: RedactScope;
        caller_agent_id?: string;
        callerAgentId?: string;
    }): Promise<Record<string, unknown>>;
    batch_update(memories: Array<Record<string, unknown>>, options?: {
        redact_policy?: RedactPolicy;
        redactPolicy?: RedactPolicy;
        redact_scope?: RedactScope;
        redactScope?: RedactScope;
        caller_agent_id?: string;
        callerAgentId?: string;
    }): Promise<Record<string, unknown>>;
    batchDelete(memories: Array<string | Record<string, unknown>>, options?: {
        caller_agent_id?: string;
        callerAgentId?: string;
    }): Promise<Record<string, unknown>>;
    batch_delete(memories: Array<string | Record<string, unknown>>, options?: {
        caller_agent_id?: string;
        callerAgentId?: string;
    }): Promise<Record<string, unknown>>;
    users(): Promise<Record<string, unknown>>;
    deleteUsers(options?: MemoryFilters): Promise<Record<string, unknown>>;
    delete_users(options?: MemoryFilters): Promise<Record<string, unknown>>;
    feedback(memoryIdOrPayload: string | {
        memory_id?: string;
        memoryId?: string;
        feedback?: string;
        feedback_reason?: string;
        feedbackReason?: string;
    }, feedback?: string, feedbackReason?: string): Promise<Record<string, unknown>>;
    getProject(fields?: string[]): Promise<Record<string, unknown>>;
    get_project(fields?: string[]): Promise<Record<string, unknown>>;
    updateProject(settings?: Record<string, unknown>): Promise<Record<string, unknown>>;
    update_project(settings?: Record<string, unknown>): Promise<Record<string, unknown>>;
    getWebhooks(projectId?: string): Promise<Record<string, unknown>>;
    get_webhooks(projectId?: string): Promise<Record<string, unknown>>;
    createWebhook(options: {
        url: string;
        name: string;
        event_types?: string[];
        eventTypes?: string[];
        project_id?: string;
        projectId?: string;
    }): Promise<Record<string, unknown>>;
    create_webhook(options: {
        url: string;
        name: string;
        event_types?: string[];
        eventTypes?: string[];
        project_id?: string;
        projectId?: string;
    }): Promise<Record<string, unknown>>;
    updateWebhook(webhookIdOrOptions: string | number | {
        webhook_id?: string | number;
        webhookId?: string | number;
        name?: string;
        url?: string;
        event_types?: string[];
        eventTypes?: string[];
        project_id?: string;
        projectId?: string;
    }, options?: {
        name?: string;
        url?: string;
        event_types?: string[];
        eventTypes?: string[];
        project_id?: string;
        projectId?: string;
    }): Promise<Record<string, unknown>>;
    update_webhook(webhookIdOrOptions: string | number | {
        webhook_id?: string | number;
        webhookId?: string | number;
        name?: string;
        url?: string;
        event_types?: string[];
        eventTypes?: string[];
        project_id?: string;
        projectId?: string;
    }, options?: {
        name?: string;
        url?: string;
        event_types?: string[];
        eventTypes?: string[];
        project_id?: string;
        projectId?: string;
    }): Promise<Record<string, unknown>>;
    deleteWebhook(webhookIdOrOptions: string | number | {
        webhook_id?: string | number;
        webhookId?: string | number;
    }): Promise<Record<string, unknown>>;
    delete_webhook(webhookIdOrOptions: string | number | {
        webhook_id?: string | number;
        webhookId?: string | number;
    }): Promise<Record<string, unknown>>;
}
/**
 * Drop-in Mem0-compatible `Memory` class backed by the / ml Cloud API.
 */
export declare class Memory extends MemoryClient {
    static fromConfig<T extends typeof Memory>(this: T, configDict?: Record<string, unknown>): InstanceType<T>;
    static from_config<T extends typeof Memory>(this: T, configDict?: Record<string, unknown>): InstanceType<T>;
}
export declare class AsyncMemoryClient extends MemoryClient {
}
export declare class AsyncMemory extends Memory {
}
export declare class SlashMLMemory extends MemoryClient {
}
export declare class SlashMLClient extends MemoryClient {
}
export declare class AsyncSlashMLMemory extends MemoryClient {
}
export declare class AsyncSlashMLClient extends MemoryClient {
}
export default Memory;
