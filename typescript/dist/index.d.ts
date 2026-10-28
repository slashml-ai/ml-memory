export declare const DEFAULT_BASE_URL = "https://api.slashml.ai";
export declare const DEFAULT_MODEL = "slashml-1.5-fast";
export declare const DEFAULT_TIMEOUT_MS = 30000;

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
}

export interface QueryOptions {
  namespace?: string;
  model?: string;
  top_k?: number;
}

export interface ForgetOptions {
  namespace?: string;
}

export declare class SlashMLAPIError extends Error {
  readonly statusCode: number;
  readonly details: Record<string, unknown>;
  constructor(statusCode: number, message: string, details?: Record<string, unknown>);
}

export declare class ProjectManager {
  constructor(client: MemoryClient);
  get(fields?: string[]): Promise<Record<string, unknown>>;
  create(
    name: string,
    description?: string,
    extra?: Record<string, unknown>,
  ): Promise<Record<string, unknown>>;
  update(settings?: Record<string, unknown>): Promise<Record<string, unknown>>;
  delete(): Promise<Record<string, unknown>>;
  getMembers(): Promise<Record<string, unknown>>;
  get_members(): Promise<Record<string, unknown>>;
  addMember(email: string, role?: string): Promise<Record<string, unknown>>;
  add_member(email: string, role?: string): Promise<Record<string, unknown>>;
  removeMember(email: string): Promise<Record<string, unknown>>;
  remove_member(email: string): Promise<Record<string, unknown>>;
}

export declare class MemoryClient {
  readonly apiKey: string;
  readonly baseUrl: string;
  readonly orgId: string | null;
  readonly projectId: string | null;
  readonly model: string;
  readonly timeoutMs: number;
  readonly project: ProjectManager;
  constructor(options?: MemoryClientOptions);
  request<T = Record<string, unknown>>(
    method: string,
    path: string,
    options?: {
      params?: Record<string, unknown>;
      jsonBody?: Record<string, unknown>;
    },
  ): Promise<T>;
  ingest(documents: string | string[], options?: IngestOptions): Promise<Record<string, unknown>>;
  query(prompt: string, options?: QueryOptions): Promise<Record<string, unknown>>;
  forget(target: string, options?: ForgetOptions): Promise<Record<string, unknown>>;
  add(
    messages: string | Array<Record<string, unknown>> | Record<string, unknown>,
    options?: AddMemoryOptions,
  ): Promise<Record<string, unknown>>;
  search(
    queryOrOptions: string | ({ query: string } & SearchMemoryOptions),
    options?: SearchMemoryOptions,
  ): Promise<Record<string, unknown>>;
  recall(
    queryOrOptions: string | ({ query: string } & SearchMemoryOptions),
    options?: SearchMemoryOptions,
  ): Promise<Record<string, unknown>>;
  getAll(options?: MemoryFilters & { limit?: number }): Promise<Record<string, unknown>>;
  get_all(options?: MemoryFilters & { limit?: number }): Promise<Record<string, unknown>>;
  get(memoryId: string): Promise<Record<string, unknown> | null>;
  update(
    memoryId: string,
    data: string | { text?: string; metadata?: Record<string, unknown> },
  ): Promise<Record<string, unknown>>;
  delete(memoryId: string): Promise<Record<string, unknown>>;
  deleteAll(options?: MemoryFilters): Promise<Record<string, unknown>>;
  delete_all(options?: MemoryFilters): Promise<Record<string, unknown>>;
  reset(): Promise<Record<string, unknown>>;
  history(memoryId: string): Promise<Array<Record<string, unknown>>>;
  batchUpdate(memories: Array<Record<string, unknown>>): Promise<Record<string, unknown>>;
  batch_update(memories: Array<Record<string, unknown>>): Promise<Record<string, unknown>>;
  batchDelete(memories: Array<string | Record<string, unknown>>): Promise<Record<string, unknown>>;
  batch_delete(memories: Array<string | Record<string, unknown>>): Promise<Record<string, unknown>>;
  users(): Promise<Record<string, unknown>>;
  deleteUsers(options?: MemoryFilters): Promise<Record<string, unknown>>;
  delete_users(options?: MemoryFilters): Promise<Record<string, unknown>>;
  feedback(
    memoryIdOrPayload:
      | string
      | {
          memory_id?: string;
          memoryId?: string;
          feedback?: string;
          feedback_reason?: string;
          feedbackReason?: string;
        },
    feedback?: string,
    feedbackReason?: string,
  ): Promise<Record<string, unknown>>;
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
  updateWebhook(
    webhookId: string | number,
    options?: {
      name?: string;
      url?: string;
      event_types?: string[];
      eventTypes?: string[];
      project_id?: string;
      projectId?: string;
    },
  ): Promise<Record<string, unknown>>;
  update_webhook(
    webhookId: string | number,
    options?: {
      name?: string;
      url?: string;
      event_types?: string[];
      eventTypes?: string[];
      project_id?: string;
      projectId?: string;
    },
  ): Promise<Record<string, unknown>>;
  deleteWebhook(webhookId: string | number): Promise<Record<string, unknown>>;
  delete_webhook(webhookId: string | number): Promise<Record<string, unknown>>;
}

export declare class Memory extends MemoryClient {
  static fromConfig(configDict?: Record<string, unknown>): Memory;
  static from_config(configDict?: Record<string, unknown>): Memory;
}

export declare class AsyncMemoryClient extends MemoryClient {}
export declare class AsyncMemory extends Memory {}
export declare class SlashMLMemory extends MemoryClient {}
export declare class SlashMLClient extends MemoryClient {}
export declare class AsyncSlashMLMemory extends MemoryClient {}
export declare class AsyncSlashMLClient extends MemoryClient {}

export default Memory;
