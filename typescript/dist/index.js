"use strict";
/**
 * @slashml/memory -- Official HTTP TypeScript / Node.js SDK for / ml (https://api.slashml.ai)
 *
 * 100% drop-in replacement for `mem0ai` (`MemoryClient`, `AsyncMemoryClient`, `Memory`, `AsyncMemory`).
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.AsyncSlashMLClient = exports.AsyncSlashMLMemory = exports.SlashMLClient = exports.SlashMLMemory = exports.AsyncMemory = exports.AsyncMemoryClient = exports.Memory = exports.MemoryClient = exports.ProjectManager = exports.SlashMLAPIError = exports.RuleScope = exports.DEFAULT_TIMEOUT_MS = exports.DEFAULT_MODEL = exports.DEFAULT_BASE_URL = void 0;
exports.extractCanonicalSlotKey = extractCanonicalSlotKey;
exports.compileContrastiveRule = compileContrastiveRule;
exports.formatCacheAlignedPrompt = formatCacheAlignedPrompt;
exports.DEFAULT_BASE_URL = "https://api.slashml.ai";
exports.DEFAULT_MODEL = "slashml-1.5-fast";
exports.DEFAULT_TIMEOUT_MS = 30_000;
class RuleScope {
    file_paths;
    tool_names;
    environments;
    git_branches;
    constructor(patterns = {}) {
        this.file_paths = patterns.file_paths ?? [];
        this.tool_names = patterns.tool_names ?? [];
        this.environments = patterns.environments ?? [];
        this.git_branches = patterns.git_branches ?? [];
    }
    matches(context) {
        if (!context)
            return true;
        const hasAnyConstraint = this.file_paths.length > 0 ||
            this.tool_names.length > 0 ||
            this.environments.length > 0 ||
            this.git_branches.length > 0;
        if (!hasAnyConstraint)
            return true;
        if (this.file_paths.length > 0 && context.file_path) {
            const p = String(context.file_path).toLowerCase();
            if (!this.file_paths.some((pattern) => p.includes(pattern.toLowerCase())))
                return false;
        }
        if (this.tool_names.length > 0 && context.tool_name) {
            const t = String(context.tool_name).toLowerCase();
            if (!this.tool_names.some((tn) => tn.toLowerCase() === t))
                return false;
        }
        if (this.environments.length > 0 && context.environment) {
            const e = String(context.environment).toLowerCase();
            if (!this.environments.some((env) => env.toLowerCase() === e))
                return false;
        }
        if (this.git_branches.length > 0 && context.git_branch) {
            const b = String(context.git_branch).toLowerCase();
            if (!this.git_branches.some((br) => br.toLowerCase() === b))
                return false;
        }
        return true;
    }
    toJSON() {
        return {
            file_paths: this.file_paths,
            tool_names: this.tool_names,
            environments: this.environments,
            git_branches: this.git_branches,
        };
    }
}
exports.RuleScope = RuleScope;
function extractCanonicalSlotKey(text, metadata) {
    if (metadata && metadata.slot_key) {
        return String(metadata.slot_key).trim().toLowerCase();
    }
    return null;
}
function compileContrastiveRule(text, ruleId, scope, options) {
    const cleanText = text.trim();
    const rid = ruleId || `rule_${Math.floor(Math.random() * 900000 + 100000)}`;
    const parsedScope = scope instanceof RuleScope ? scope : new RuleScope(scope);
    return {
        rule_id: rid,
        do: options?.do || cleanText,
        dont: options?.dont || "",
        scope: parsedScope,
        raw_text: cleanText,
    };
}
function formatCacheAlignedPrompt(rules, facts, userPrompt, options = {}) {
    const activeContext = options.activeContext;
    const enableCacheBreakpoint = options.enableCacheBreakpoint ?? true;
    const activeRules = rules.filter((r) => {
        if (!r.scope)
            return true;
        const scopeObj = r.scope instanceof RuleScope ? r.scope : new RuleScope(r.scope);
        return scopeObj.matches(activeContext);
    });
    const zone1Lines = [];
    if (activeRules.length > 0) {
        zone1Lines.push("<rules>");
        for (const r of activeRules) {
            zone1Lines.push(`  <rule id="${r.rule_id}">\n    <do>${r.do}</do>\n    <dont>${r.dont}</dont>\n  </rule>`);
        }
        zone1Lines.push("</rules>");
    }
    const zone1Text = zone1Lines.join("\n");
    const zone2Lines = [];
    if (facts.length > 0) {
        zone2Lines.push("<facts>");
        for (const f of facts) {
            const fText = typeof f === "string" ? f : f?.text ?? f?.memory ?? "";
            if (fText) {
                zone2Lines.push(`  <fact>${fText}</fact>`);
            }
        }
        zone2Lines.push("</facts>");
    }
    const zone2Text = zone2Lines.join("\n");
    let whisperText = "";
    if (options.whisperRule) {
        whisperText = `<whisper>\n  [CRITICAL CONSTRAINT ACTIVE]\n  DO: ${options.whisperRule.do}\n  DON'T: ${options.whisperRule.dont}\n</whisper>`;
    }
    const parts = [];
    if (zone1Text)
        parts.push(zone1Text);
    if (enableCacheBreakpoint && zone1Text)
        parts.push("<!-- cache_control: ephemeral_breakpoint -->");
    if (zone2Text)
        parts.push(zone2Text);
    if (whisperText)
        parts.push(whisperText);
    parts.push(userPrompt);
    const fullPrompt = parts.filter(Boolean).join("\n\n");
    const z1Tok = zone1Text ? Math.max(1, Math.floor(zone1Text.length / 4)) : 0;
    const z2Tok = zone2Text ? Math.max(1, Math.floor(zone2Text.length / 4)) : 0;
    const uTok = Math.max(1, Math.floor(userPrompt.length / 4));
    const totTok = z1Tok + z2Tok + uTok;
    return {
        zone1_rules_text: zone1Text,
        zone2_facts_text: zone2Text,
        user_turn: userPrompt,
        whisper_block: whisperText,
        full_prompt_text: fullPrompt,
        has_cache_breakpoint: enableCacheBreakpoint && Boolean(zone1Text),
        token_economics: {
            zone1_tokens_estimated: z1Tok,
            zone2_tokens_estimated: z2Tok,
            user_tokens_estimated: uTok,
            total_tokens_estimated: totTok,
            prefix_cache_eligible_ratio: totTok > 0 ? Number((z1Tok / totTok).toFixed(3)) : 0.0,
        },
    };
}
class SlashMLAPIError extends Error {
    statusCode;
    details;
    constructor(statusCode, message, details = {}) {
        super(`SlashMLAPIError (${statusCode}): ${message}`);
        this.name = "SlashMLAPIError";
        this.statusCode = statusCode;
        this.details = details;
    }
}
exports.SlashMLAPIError = SlashMLAPIError;
function getEnv(name) {
    const proc = globalThis.process;
    if (typeof proc !== "undefined" && proc && proc.env) {
        return proc.env[name];
    }
    return undefined;
}
class ProjectManager {
    client;
    constructor(client) {
        this.client = client;
    }
    async get(fieldsOrOptions) {
        const fields = Array.isArray(fieldsOrOptions)
            ? fieldsOrOptions
            : fieldsOrOptions?.fields;
        return this.client.request("GET", "/v1/project", {
            params: {
                org_id: this.client.orgId ?? undefined,
                project_id: this.client.projectId ?? undefined,
                fields: fields && fields.length > 0 ? fields.join(",") : undefined,
            },
        });
    }
    async create(nameOrOptions, description, extra = {}) {
        const body = typeof nameOrOptions === "string"
            ? { name: nameOrOptions, description, ...extra }
            : { ...nameOrOptions };
        return this.client.request("POST", "/v1/project", {
            jsonBody: {
                org_id: this.client.orgId ?? undefined,
                ...body,
            },
        });
    }
    async update(settings = {}) {
        const payload = {
            org_id: this.client.orgId ?? undefined,
            project_id: this.client.projectId ?? undefined,
            ...settings,
        };
        if (settings.customInstructions !== undefined && payload.custom_instructions === undefined) {
            payload.custom_instructions = settings.customInstructions;
        }
        if (settings.customCategories !== undefined && payload.custom_categories === undefined) {
            payload.custom_categories = settings.customCategories;
        }
        if (settings.enableGraph !== undefined && payload.enable_graph === undefined) {
            payload.enable_graph = settings.enableGraph;
        }
        return this.client.request("PATCH", "/v1/project", {
            jsonBody: payload,
        });
    }
    async delete() {
        return this.client.request("DELETE", "/v1/project", {
            params: {
                org_id: this.client.orgId ?? undefined,
                project_id: this.client.projectId ?? undefined,
            },
        });
    }
    async getMembers() {
        return this.client.request("GET", "/v1/project/members", {
            params: {
                org_id: this.client.orgId ?? undefined,
                project_id: this.client.projectId ?? undefined,
            },
        });
    }
    async get_members() {
        return this.getMembers();
    }
    async addMember(emailOrOptions, role = "READER") {
        const email = typeof emailOrOptions === "string" ? emailOrOptions : emailOrOptions.email;
        const resolvedRole = typeof emailOrOptions === "string" ? role : (emailOrOptions.role ?? role);
        return this.client.request("POST", "/v1/project/members", {
            jsonBody: {
                email,
                role: resolvedRole,
                org_id: this.client.orgId ?? undefined,
                project_id: this.client.projectId ?? undefined,
            },
        });
    }
    async add_member(emailOrOptions, role = "READER") {
        return this.addMember(emailOrOptions, role);
    }
    async removeMember(emailOrOptions) {
        const email = typeof emailOrOptions === "string" ? emailOrOptions : emailOrOptions.email;
        return this.client.request("DELETE", "/v1/project/members", {
            params: {
                email,
                org_id: this.client.orgId ?? undefined,
                project_id: this.client.projectId ?? undefined,
            },
        });
    }
    async remove_member(emailOrOptions) {
        return this.removeMember(emailOrOptions);
    }
}
exports.ProjectManager = ProjectManager;
class MemoryClient {
    apiKey;
    baseUrl;
    orgId;
    projectId;
    model;
    timeoutMs;
    project;
    fetchImpl;
    constructor(options = {}) {
        const resolvedKey = options.apiKey ||
            options.api_key ||
            options.mem0ApiKey ||
            getEnv("SLASHML_API_KEY") ||
            getEnv("MEM0_API_KEY") ||
            "";
        const resolvedUrl = options.baseUrl ||
            options.base_url ||
            options.host ||
            getEnv("SLASHML_BASE_URL") ||
            getEnv("SLASHML_API_URL") ||
            exports.DEFAULT_BASE_URL;
        const resolvedModel = options.model ||
            getEnv("SLASHML_MODEL") ||
            exports.DEFAULT_MODEL;
        this.apiKey = resolvedKey;
        this.baseUrl = resolvedUrl.replace(/\/+$/, "");
        this.orgId = options.orgId || options.org_id || getEnv("SLASHML_ORG_ID") || null;
        this.projectId = options.projectId || options.project_id || getEnv("SLASHML_PROJECT_ID") || null;
        this.model = resolvedModel;
        this.timeoutMs = options.timeoutMs ?? exports.DEFAULT_TIMEOUT_MS;
        this.fetchImpl = options.fetchImpl ?? globalThis.fetch;
        this.project = new ProjectManager(this);
    }
    async request(method, path, options = {}) {
        if (!this.apiKey) {
            throw new SlashMLAPIError(401, "API key is required. Pass `apiKey: 'sml_...'` or set SLASHML_API_KEY.");
        }
        let url = `${this.baseUrl}${path.startsWith("/") ? path : `/${path}`}`;
        if (options.params) {
            const searchParams = new URLSearchParams();
            for (const [key, value] of Object.entries(options.params)) {
                if (value !== undefined && value !== null) {
                    searchParams.set(key, String(value));
                }
            }
            const qs = searchParams.toString();
            if (qs) {
                url = `${url}?${qs}`;
            }
        }
        const headers = {
            Accept: "application/json",
            "Content-Type": "application/json",
            "User-Agent": "slashml-memory-ts/1.0.10",
        };
        if (this.apiKey) {
            headers.Authorization = `Bearer ${this.apiKey}`;
            headers["X-API-Key"] = this.apiKey;
        }
        if (this.orgId) {
            headers["X-SlashML-Org-Id"] = this.orgId;
        }
        if (this.projectId) {
            headers["X-SlashML-Project-Id"] = this.projectId;
        }
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), this.timeoutMs);
        try {
            const response = await this.fetchImpl(url, {
                method: method.toUpperCase(),
                headers,
                body: options.jsonBody !== undefined ? JSON.stringify(options.jsonBody) : undefined,
                signal: controller.signal,
            });
            const rawText = await response.text();
            let parsed = {};
            if (rawText) {
                try {
                    parsed = JSON.parse(rawText);
                }
                catch {
                    parsed = { raw: rawText };
                }
            }
            if (!response.ok) {
                const message = parsed.error ||
                    parsed.detail ||
                    parsed.message ||
                    response.statusText ||
                    "HTTP Error";
                throw new SlashMLAPIError(response.status, message, parsed);
            }
            return parsed;
        }
        catch (err) {
            if (err instanceof SlashMLAPIError) {
                throw err;
            }
            const message = err instanceof Error ? err.message : String(err);
            throw new SlashMLAPIError(0, `Failed to reach / ml API at ${url}: ${message}`);
        }
        finally {
            clearTimeout(timer);
        }
    }
    // ---------------------------------------------------------------------------
    // Native / ml Memory Endpoints (/v1/memory/*)
    // ---------------------------------------------------------------------------
    async ingest(documents, options = {}) {
        const docs = typeof documents === "string" ? [documents] : Array.from(documents);
        const meta = { ...(options.metadata ?? {}) };
        const effectiveTier = options.record_tier ?? options.recordTier ?? meta.record_tier ?? meta.tier;
        if (effectiveTier)
            meta.record_tier = String(effectiveTier);
        let effectiveSlot = options.slot_key ?? options.slotKey ?? meta.slot_key;
        if (!effectiveSlot && typeof documents === "string") {
            effectiveSlot = extractCanonicalSlotKey(documents, meta) ?? undefined;
        }
        if (effectiveSlot)
            meta.slot_key = String(effectiveSlot);
        if (options.scope) {
            meta.scope = options.scope instanceof RuleScope ? options.scope.toJSON() : options.scope;
        }
        if (options.contrastive) {
            meta.contrastive = {
                do: options.contrastive.do,
                dont: options.contrastive.dont,
                context: options.contrastive.context,
            };
        }
        return this.request("POST", "/v1/memory/ingest", {
            jsonBody: {
                namespace: options.namespace ?? "default",
                model: options.model ?? this.model,
                documents: docs,
                metadata: meta,
                ...(meta.record_tier ? { record_tier: meta.record_tier } : {}),
                ...(meta.slot_key ? { slot_key: meta.slot_key } : {}),
            },
        });
    }
    async query(prompt, options = {}) {
        const payload = {
            namespace: options.namespace ?? "default",
            model: options.model ?? this.model,
            prompt,
            query: prompt,
            top_k: options.top_k ?? 5,
        };
        const effectiveTier = options.record_tier ?? options.recordTier;
        if (effectiveTier)
            payload.record_tier = String(effectiveTier);
        if (options.context)
            payload.context = options.context;
        if (options.include_rules !== undefined)
            payload.include_rules = Boolean(options.include_rules);
        return this.request("POST", "/v1/memory/query", {
            jsonBody: payload,
        });
    }
    async forget(target, options = {}) {
        return this.request("POST", "/v1/memory/forget", {
            jsonBody: {
                namespace: options.namespace ?? "default",
                target,
            },
        });
    }
    async intervene(textOrPayload, options = {}) {
        const opts = typeof textOrPayload === "string"
            ? { ...options, prompt: options.prompt ?? textOrPayload, text: options.text ?? textOrPayload }
            : { ...textOrPayload, ...options };
        const resolvedText = opts.text ?? opts.prompt ?? "";
        const resolvedModel = opts.model ?? this.model;
        const resolvedProjectId = opts.project_id ?? opts.projectId ?? this.projectId ?? null;
        const resolvedSessionId = opts.session_id ?? opts.sessionId ?? null;
        const lastAssistantMsg = opts.last_assistant_message ?? opts.lastAssistantMessage ?? undefined;
        const stopHookActive = opts.stop_hook_active ?? opts.stopHookActive ?? undefined;
        const whisperedIds = opts.whispered_memory_ids ?? opts.whisperedMemoryIds ?? undefined;
        return this.request("POST", "/v1/memory/intervene", {
            jsonBody: {
                hook_event_name: opts.hook_event_name ?? opts.hookEventName ?? "UserPromptSubmit",
                prompt: opts.prompt ?? resolvedText,
                text: resolvedText,
                ...(lastAssistantMsg !== undefined ? { last_assistant_message: lastAssistantMsg } : {}),
                ...(stopHookActive !== undefined ? { stop_hook_active: Boolean(stopHookActive) } : {}),
                ...(whisperedIds && whisperedIds.length > 0 ? { whispered_memory_ids: whisperedIds } : {}),
                tool_name: opts.tool_name ?? opts.toolName ?? null,
                tool_input: opts.tool_input ?? opts.toolInput ?? null,
                tool_response: opts.tool_response ?? opts.toolResponse ?? null,
                user_id: opts.user_id ?? opts.userId ?? "default",
                ...(resolvedProjectId ? { project_id: resolvedProjectId } : {}),
                ...(resolvedSessionId ? { session_id: resolvedSessionId } : {}),
                model: resolvedModel,
                commit_writes: opts.commit_writes ?? opts.commitWrites ?? true,
                top_k: opts.top_k ?? opts.topK ?? 5,
                client_raw_tokens_delta: opts.client_raw_tokens_delta ?? opts.clientRawTokensDelta ?? 0,
                client_dropped_tokens_delta: opts.client_dropped_tokens_delta ?? opts.clientDroppedTokensDelta ?? 0,
                client_dropped_events_delta: opts.client_dropped_events_delta ?? opts.clientDroppedEventsDelta ?? 0,
            },
        });
    }
    async status(options = {}) {
        const uid = options.user_id ?? options.userId ?? "default";
        const rawDelta = options.client_raw_tokens_delta ?? options.clientRawTokensDelta ?? 0;
        const droppedTokDelta = options.client_dropped_tokens_delta ?? options.clientDroppedTokensDelta ?? 0;
        const droppedEvDelta = options.client_dropped_events_delta ?? options.clientDroppedEventsDelta ?? 0;
        if (rawDelta > 0 || droppedTokDelta > 0 || droppedEvDelta > 0) {
            return this.request("POST", "/v1/memory/status", {
                jsonBody: {
                    user_id: uid,
                    client_raw_tokens_delta: rawDelta,
                    client_dropped_tokens_delta: droppedTokDelta,
                    client_dropped_events_delta: droppedEvDelta,
                },
            });
        }
        return this.request("GET", "/v1/memory/status", {
            params: { user_id: uid },
        });
    }
    // ---------------------------------------------------------------------------
    // Phase 30 Dual-Tier & Prompt-Cache Features
    // ---------------------------------------------------------------------------
    async addRule(text, options = {}) {
        const compiled = compileContrastiveRule(text, options.rule_id || options.ruleId, options.scope);
        if (options.do)
            compiled.do = options.do;
        if (options.dont)
            compiled.dont = options.dont;
        const meta = {
            ...(options.metadata ?? {}),
            rule_id: compiled.rule_id,
            scope: compiled.scope instanceof RuleScope ? compiled.scope.toJSON() : compiled.scope,
            contrastive: { do: compiled.do, dont: compiled.dont },
            record_tier: "rule",
        };
        return this.ingest(text, {
            record_tier: "rule",
            metadata: meta,
            scope: compiled.scope,
            contrastive: compiled,
        });
    }
    async add_rule(text, options = {}) {
        return this.addRule(text, options);
    }
    async getCacheAlignedPrompt(userTurn, options = {}) {
        const rulesRes = await this.query(userTurn, {
            top_k: 20,
            record_tier: "rule",
            context: options.activeContext,
        });
        const rawRules = rulesRes?.results || rulesRes?.memories || [];
        const rulesList = rawRules.map((r) => {
            const rMeta = r.metadata || {};
            const cInfo = rMeta.contrastive || {};
            const sInfo = rMeta.scope || {};
            return {
                rule_id: String(r.id || rMeta.rule_id || "rule"),
                do: String(cInfo.do || r.text || ""),
                dont: String(cInfo.dont || ""),
                context: String(cInfo.context || ""),
                scope: new RuleScope(sInfo),
                raw_text: String(r.text || ""),
            };
        });
        const factsRes = await this.query(userTurn, {
            top_k: options.top_k || 5,
            record_tier: "fact",
        });
        const rawFacts = factsRes?.results || factsRes?.memories || [];
        const factsList = rawFacts.map((f) => String(f.text || f.memory || ""));
        return formatCacheAlignedPrompt(rulesList, factsList, userTurn, {
            activeContext: options.activeContext,
            enableCacheBreakpoint: options.enableCacheBreakpoint ?? true,
        });
    }
    async get_cache_aligned_prompt(userTurn, options = {}) {
        return this.getCacheAlignedPrompt(userTurn, options);
    }
    // ---------------------------------------------------------------------------
    // Mem0-Compatible REST Endpoints (/v1/memories/*)
    // ---------------------------------------------------------------------------
    async add(messages, options = {}) {
        const memId = options.memory_id ?? options.memoryId;
        const normalizedMessages = typeof messages === "string"
            ? [{ role: "user", content: messages, ...(memId ? { id: memId } : {}) }]
            : Array.isArray(messages)
                ? messages
                : [messages];
        const meta = { ...(options.metadata ?? {}) };
        const effectiveTier = options.record_tier ?? options.recordTier ?? meta.record_tier ?? meta.tier;
        if (effectiveTier)
            meta.record_tier = String(effectiveTier);
        let effectiveSlot = options.slot_key ?? options.slotKey ?? meta.slot_key;
        if (!effectiveSlot && typeof messages === "string") {
            effectiveSlot = extractCanonicalSlotKey(messages, meta) ?? undefined;
        }
        if (effectiveSlot)
            meta.slot_key = String(effectiveSlot);
        if (options.scope) {
            meta.scope = options.scope instanceof RuleScope ? options.scope.toJSON() : options.scope;
        }
        if (options.contrastive) {
            meta.contrastive = {
                do: options.contrastive.do,
                dont: options.contrastive.dont,
                context: options.contrastive.context,
            };
        }
        const payload = {
            messages: normalizedMessages,
            ...(typeof messages === "string" ? { text: messages } : {}),
            user_id: options.user_id ?? options.userId ?? null,
            agent_id: options.agent_id ?? options.agentId ?? null,
            app_id: options.app_id ?? options.appId ?? null,
            run_id: options.run_id ?? options.runId ?? null,
            metadata: meta,
            ...(meta.record_tier ? { record_tier: meta.record_tier } : {}),
            ...(meta.slot_key ? { slot_key: meta.slot_key } : {}),
            infer: options.infer ?? true,
            model: this.model,
        };
        if (memId) {
            payload.memory_id = memId;
            payload.id = memId;
        }
        return this.request("POST", "/v1/memories", { jsonBody: payload });
    }
    async search(queryOrOptions, options = {}) {
        const isObj = typeof queryOrOptions === "object" && queryOrOptions !== null;
        const query = isObj ? queryOrOptions.query : queryOrOptions;
        const opts = isObj ? queryOrOptions : options;
        const effectiveLimit = opts.top_k ?? opts.topK ?? opts.limit ?? 5;
        return this.request("POST", "/v1/memories/search", {
            jsonBody: {
                query,
                user_id: opts.user_id ?? opts.userId ?? null,
                agent_id: opts.agent_id ?? opts.agentId ?? null,
                app_id: opts.app_id ?? opts.appId ?? null,
                run_id: opts.run_id ?? opts.runId ?? null,
                limit: effectiveLimit,
                top_k: effectiveLimit,
                filters: opts.filters ?? opts.metadata ?? null,
                threshold: opts.threshold ?? null,
                model: this.model,
            },
        });
    }
    async recall(queryOrOptions, options = {}) {
        return this.search(queryOrOptions, options);
    }
    async getAll(options = {}) {
        return this.request("GET", "/v1/memories", {
            params: {
                user_id: options.user_id ?? options.userId ?? undefined,
                agent_id: options.agent_id ?? options.agentId ?? undefined,
                app_id: options.app_id ?? options.appId ?? undefined,
                run_id: options.run_id ?? options.runId ?? undefined,
                limit: options.limit ?? 100,
            },
        });
    }
    async get_all(options = {}) {
        return this.getAll(options);
    }
    async get(memoryId) {
        try {
            return await this.request("GET", `/v1/memories/${encodeURIComponent(memoryId)}`);
        }
        catch (err) {
            if (err instanceof SlashMLAPIError && err.statusCode === 404) {
                return null;
            }
            throw err;
        }
    }
    async update(memoryId, data) {
        const body = typeof data === "string"
            ? { text: data }
            : { text: data.text ?? "", metadata: data.metadata };
        return this.request("PUT", `/v1/memories/${encodeURIComponent(memoryId)}`, {
            jsonBody: body,
        });
    }
    async delete(memoryId) {
        return this.request("DELETE", `/v1/memories/${encodeURIComponent(memoryId)}`);
    }
    async deleteAll(options = {}) {
        return this.request("DELETE", "/v1/memories", {
            params: {
                user_id: options.user_id ?? options.userId ?? undefined,
                agent_id: options.agent_id ?? options.agentId ?? undefined,
                app_id: options.app_id ?? options.appId ?? undefined,
                run_id: options.run_id ?? options.runId ?? undefined,
            },
        });
    }
    async delete_all(options = {}) {
        return this.deleteAll(options);
    }
    async reset() {
        return this.request("POST", "/v1/memories/reset", { jsonBody: {} });
    }
    async history(memoryId) {
        const resp = await this.request("GET", `/v1/memories/${encodeURIComponent(memoryId)}/history`);
        if (Array.isArray(resp)) {
            return resp;
        }
        if (Array.isArray(resp.history)) {
            return resp.history;
        }
        if (Array.isArray(resp.results)) {
            return resp.results;
        }
        return [];
    }
    async batchUpdate(memories) {
        const normalized = memories.map((m) => ({
            ...m,
            memory_id: m.memory_id ?? m.memoryId ?? m.id,
        }));
        return this.request("PUT", "/v1/batch", { jsonBody: { memories: normalized } });
    }
    async batch_update(memories) {
        return this.batchUpdate(memories);
    }
    async batchDelete(memories) {
        const normalized = memories.map((m) => typeof m === "string"
            ? { memory_id: m, id: m }
            : { ...m, memory_id: m.memory_id ?? m.memoryId ?? m.id });
        return this.request("DELETE", "/v1/batch", { jsonBody: { memories: normalized } });
    }
    async batch_delete(memories) {
        return this.batchDelete(memories);
    }
    async users() {
        return this.request("GET", "/v1/entities", {
            params: {
                org_id: this.orgId ?? undefined,
                project_id: this.projectId ?? undefined,
            },
        });
    }
    async deleteUsers(options = {}) {
        return this.request("DELETE", "/v1/entities", {
            params: {
                user_id: options.user_id ?? options.userId ?? undefined,
                agent_id: options.agent_id ?? options.agentId ?? undefined,
                app_id: options.app_id ?? options.appId ?? undefined,
                run_id: options.run_id ?? options.runId ?? undefined,
                org_id: this.orgId ?? undefined,
                project_id: this.projectId ?? undefined,
            },
        });
    }
    async delete_users(options = {}) {
        return this.deleteUsers(options);
    }
    async feedback(memoryIdOrPayload, feedback, feedbackReason) {
        const payload = typeof memoryIdOrPayload === "string"
            ? {
                memory_id: memoryIdOrPayload,
                feedback: feedback ?? null,
                feedback_reason: feedbackReason ?? null,
            }
            : {
                memory_id: memoryIdOrPayload.memory_id ?? memoryIdOrPayload.memoryId,
                feedback: memoryIdOrPayload.feedback ?? null,
                feedback_reason: memoryIdOrPayload.feedback_reason ?? memoryIdOrPayload.feedbackReason ?? null,
            };
        return this.request("POST", "/v1/feedback", { jsonBody: payload });
    }
    async getProject(fields) {
        return this.project.get(fields);
    }
    async get_project(fields) {
        return this.project.get(fields);
    }
    async updateProject(settings = {}) {
        return this.project.update(settings);
    }
    async update_project(settings = {}) {
        return this.project.update(settings);
    }
    async getWebhooks(projectId) {
        return this.request("GET", "/v1/webhooks", {
            params: { project_id: projectId ?? this.projectId ?? undefined },
        });
    }
    async get_webhooks(projectId) {
        return this.getWebhooks(projectId);
    }
    async createWebhook(options) {
        return this.request("POST", "/v1/webhooks", {
            jsonBody: {
                url: options.url,
                name: options.name,
                event_types: options.event_types ?? options.eventTypes ?? [],
                project_id: options.project_id ?? options.projectId ?? this.projectId ?? undefined,
            },
        });
    }
    async create_webhook(options) {
        return this.createWebhook(options);
    }
    async updateWebhook(webhookIdOrOptions, options = {}) {
        const isObj = typeof webhookIdOrOptions === "object" && webhookIdOrOptions !== null;
        const wid = isObj
            ? (webhookIdOrOptions.webhook_id ?? webhookIdOrOptions.webhookId)
            : webhookIdOrOptions;
        const opts = isObj ? webhookIdOrOptions : options;
        return this.request("PUT", `/v1/webhooks/${encodeURIComponent(String(wid))}`, {
            jsonBody: {
                name: opts.name,
                url: opts.url,
                event_types: opts.event_types ?? opts.eventTypes,
                project_id: opts.project_id ?? opts.projectId ?? this.projectId ?? undefined,
            },
        });
    }
    async update_webhook(webhookIdOrOptions, options = {}) {
        return this.updateWebhook(webhookIdOrOptions, options);
    }
    async deleteWebhook(webhookIdOrOptions) {
        const wid = typeof webhookIdOrOptions === "object" && webhookIdOrOptions !== null
            ? (webhookIdOrOptions.webhook_id ?? webhookIdOrOptions.webhookId)
            : webhookIdOrOptions;
        return this.request("DELETE", `/v1/webhooks/${encodeURIComponent(String(wid))}`);
    }
    async delete_webhook(webhookIdOrOptions) {
        return this.deleteWebhook(webhookIdOrOptions);
    }
}
exports.MemoryClient = MemoryClient;
/**
 * Drop-in Mem0-compatible `Memory` class backed by the / ml Cloud API.
 */
class Memory extends MemoryClient {
    static fromConfig(configDict = {}) {
        return new this({
            apiKey: configDict.api_key ||
                configDict.apiKey ||
                configDict.mem0ApiKey,
            baseUrl: configDict.base_url ||
                configDict.baseUrl ||
                configDict.host,
            orgId: configDict.org_id || configDict.orgId,
            projectId: configDict.project_id || configDict.projectId,
            model: configDict.model,
            timeoutMs: configDict.timeoutMs,
        });
    }
    static from_config(configDict = {}) {
        return this.fromConfig(configDict);
    }
}
exports.Memory = Memory;
class AsyncMemoryClient extends MemoryClient {
}
exports.AsyncMemoryClient = AsyncMemoryClient;
class AsyncMemory extends Memory {
}
exports.AsyncMemory = AsyncMemory;
class SlashMLMemory extends MemoryClient {
}
exports.SlashMLMemory = SlashMLMemory;
class SlashMLClient extends MemoryClient {
}
exports.SlashMLClient = SlashMLClient;
class AsyncSlashMLMemory extends MemoryClient {
}
exports.AsyncSlashMLMemory = AsyncSlashMLMemory;
class AsyncSlashMLClient extends MemoryClient {
}
exports.AsyncSlashMLClient = AsyncSlashMLClient;
exports.default = Memory;
