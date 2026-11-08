"""Model Context Protocol (MCP) Server for `/ ml` (`https://api.slashml.ai`).

Runs locally over JSON-RPC 2.0 `stdio` and forwards all memory and code search
operations to the `/ ml` Cloud API (`https://api.slashml.ai`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from slashml.client import MemoryClient, TransportCallable
from slashml.repo_indexer import (
    RepositoryIndexer,
    find_bug_candidates,
    search_code_by_behavior,
)


DEFAULT_CONSOLE_URL = "https://app.slashml.ai"
GENERIC_SKILL_NAMES = {"ml-memory", "/ml-memory", "slashml", "all", "default"}
PUBLIC_CONSUMER_EMAIL_DOMAINS = {
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
}


def _assert_cli_work_email(raw_email: str) -> str:
    cleaned = (raw_email or "").strip().lower()
    if "@" not in cleaned or "." not in cleaned.split("@", 1)[1]:
        raise SystemExit("Error: Please provide a valid work email address (e.g. you@company.com).")
    _local_part, domain_part = cleaned.split("@", 1)
    canonical_domain = "gmail.com" if domain_part == "googlemail.com" else domain_part
    if canonical_domain in PUBLIC_CONSUMER_EMAIL_DOMAINS:
        raise SystemExit(
            "Error: Public email domains (@gmail.com, @hotmail.com, @outlook.com, @yahoo.com, @icloud.com, etc.) "
            "require Google or GitHub Sign-In at https://app.slashml.ai/auth/google. "
            "For CLI OTP signup (--signup), please use a work or custom domain email (you@company.com)."
        )
    return cleaned


def _save_api_key_to_env(api_key: str, cwd: Path | None = None) -> Path:
    base_dir = cwd or Path.cwd()
    env_path = base_dir / ".env"
    content = ""
    if env_path.exists():
        try:
            content = env_path.read_text(encoding="utf-8")
        except Exception:
            content = ""
    line = f"SLASHML_API_KEY={api_key}"
    lines = content.splitlines()
    replaced = False
    for idx, existing in enumerate(lines):
        if existing.startswith("SLASHML_API_KEY="):
            lines[idx] = line
            replaced = True
            break
    if not replaced:
        lines.append(line)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    gitignore_path = base_dir / ".gitignore"
    if gitignore_path.exists():
        try:
            gi = gitignore_path.read_text(encoding="utf-8")
            gi_lines = [x.strip() for x in gi.splitlines()]
            if ".env" not in gi_lines and ".env*" not in gi_lines:
                gitignore_path.write_text(gi.rstrip("\n") + "\n.env\n", encoding="utf-8")
        except Exception:
            pass
    return env_path


def configure_mcp_targets(
    *,
    skill: str | None = None,
    api_key: str | None = None,
    repo: str | None = None,
    write_env: bool = False,
) -> list[str]:
    home = Path.home()
    cwd = Path.cwd()
    targets = [
        home / ".cursor" / "mcp.json",
        home / ".codeium" / "windsurf" / "mcp_config.json",
    ]
    claude_cfg = cwd / ".mcp.json"
    norm_skill = skill.strip().lower() if skill else None
    is_generic = not norm_skill or norm_skill in GENERIC_SKILL_NAMES

    if claude_cfg.exists() or (norm_skill and ("claude" in norm_skill or "mcp.json" in norm_skill)):
        targets.append(claude_cfg)

    resolved_targets = [
        t for t in targets if is_generic or (norm_skill and norm_skill in str(t).lower())
    ]

    args = ["-y", "@slashml/mcp"]
    if repo:
        args.extend(["--workspace", repo])
    server_entry: dict[str, Any] = {
        "command": "npx",
        "args": args,
    }
    resolved_key = api_key or os.environ.get("SLASHML_API_KEY")
    if resolved_key:
        server_entry["env"] = {"SLASHML_API_KEY": resolved_key}
    if write_env and resolved_key:
        _save_api_key_to_env(resolved_key, cwd)

    written: list[str] = []
    for target in resolved_targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = {}
        if target.exists():
            try:
                data = json.loads(target.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        if not isinstance(data.get("mcpServers"), dict):
            data["mcpServers"] = {}
        data["mcpServers"].pop("/ml-memory", None)
        data["mcpServers"]["ml-memory"] = server_entry
        target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"Configured ml-memory MCP in {target}")
        written.append(str(target))
    return written


def _console_post(console_url: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = f"{console_url.rstrip('/')}{path}"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "slashml-mcp-python/1.0.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20.0) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            err_data = json.loads(raw)
            msg = err_data.get("error") or err_data.get("message") or raw
        except Exception:
            msg = raw or str(exc)
        raise RuntimeError(f"{msg} (HTTP {exc.code})") from exc


class SlashMLMCPServer:
    """JSON-RPC 2.0 MCP Server connecting coding agents to `/ ml` Cloud (`https://api.slashml.ai`)."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        user_id: str = "default",
        code_only: bool = False,
        code_mode: bool = False,
        repo_path: str | Path | None = None,
        transport: TransportCallable | None = None,
    ) -> None:
        self.client = MemoryClient(
            api_key=api_key,
            base_url=base_url,
            transport=transport,
        )
        self.user_id = user_id
        self.code_only = code_only
        self.code_mode = code_mode
        self.repo_path = Path(repo_path).resolve() if repo_path else None
        self.indexer = RepositoryIndexer(self.client, user_id=self.user_id)

    def list_tools(self) -> list[dict[str, Any]]:
        if self.code_mode:
            return [
                {
                    "name": "execute_memory_code",
                    "description": (
                        "Compact meta-tool (91% token savings) dispatching memory & code actions "
                        "(`add_memory`, `search_memories`, `get_memories`, `forget_memory`, "
                        "`index_repository`, `search_code_by_behavior`, `find_bug_candidates`, "
                        "`intervene_memory`) "
                        "to `/ ml` Cloud."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": [
                                    "add_memory",
                                    "add_scoped_rule",
                                    "search_memories",
                                    "get_memories",
                                    "get_cache_aligned_prompt",
                                    "forget_memory",
                                    "index_repository",
                                    "search_code_by_behavior",
                                    "find_bug_candidates",
                                    "intervene_memory",
                                    "dismiss_intervention",
                                ],
                            },
                            "params": {"type": "object"},
                        },
                        "required": ["action"],
                    },
                }
            ]

        code_tools = [
            {
                "name": "index_repository",
                "description": (
                    "Parse and index source code files (Python, TypeScript/JS, Rust, Go) "
                    "in a repository directory into the `/ ml` Cloud memory engine."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Repository directory path"},
                        "repo_path": {"type": "string", "description": "Alias for path"},
                        "max_files": {"type": "integer", "default": 10000},
                        "force": {"type": "boolean", "default": False},
                    },
                },
            },
            {
                "name": "search_code_by_behavior",
                "description": (
                    "Search indexed functions, classes, and modules by computational behavior "
                    "or architectural role, even when identifiers differ."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Behavioral or code query"},
                        "top_k": {"type": "integer", "default": 5},
                        "language": {"type": "string"},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "find_bug_candidates",
                "description": (
                    "Localize likely buggy functions or modules from a symptom description "
                    "or stack trace."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "bug_description": {"type": "string"},
                        "stack_trace": {"type": "string"},
                        "top_k": {"type": "integer", "default": 5},
                    },
                    "required": ["bug_description"],
                },
            },
        ]
        if self.code_only:
            return code_tools

        memory_tools = [
            {
                "name": "add_memory",
                "description": (
                    "Store a persistent fact, architectural decision, user preference, or code "
                    "snippet in `/ ml` Cloud."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "user_id": {"type": "string"},
                        "memory_id": {"type": "string"},
                        "metadata": {"type": "object"},
                        "record_tier": {"type": "string", "enum": ["fact", "rule"]},
                        "slot_key": {"type": "string"},
                        "scope": {"type": "object"},
                    },
                    "required": ["text"],
                },
            },
            {
                "name": "add_scoped_rule",
                "description": (
                    "Store an operational rule or constraint (Tier B) with optional negative "
                    "contrastive enforcement (DO / DON'T) and execution scope."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Natural language rule or constraint text"},
                        "rule_id": {"type": "string", "description": "Optional unique rule identifier"},
                        "do": {"type": "string", "description": "Positive behavior statement"},
                        "dont": {"type": "string", "description": "Negative prohibition statement"},
                        "scope": {
                            "type": "object",
                            "description": "Rule scope matching criteria (file_paths, tool_names, environments, git_branches)",
                        },
                        "user_id": {"type": "string"},
                        "metadata": {"type": "object"},
                    },
                    "required": ["text"],
                },
            },
            {
                "name": "search_memories",
                "description": (
                    "Retrieve relevant conversational memories, user constraints, and project decisions "
                    "(excludes indexed code_symbol chunks by default unless include_code=true)."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "user_id": {"type": "string"},
                        "limit": {"type": "integer", "default": 5},
                        "include_code": {"type": "boolean", "default": False},
                        "record_tier": {"type": "string", "enum": ["fact", "rule"]},
                        "filters": {"type": "object"},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "get_cache_aligned_prompt",
                "description": (
                    "Retrieve scoped rules and dynamic facts formatted into Zone 1 (static rules) "
                    "and Zone 2 (dynamic facts) with cache breakpoint delimiter for optimal KV prefix reuse."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "user_turn": {"type": "string", "description": "Current user prompt or task turn"},
                        "context": {
                            "type": "object",
                            "description": "Active environment context (file_path, tool_name, environment, git_branch)",
                        },
                        "top_k": {"type": "integer", "default": 5},
                        "user_id": {"type": "string"},
                        "enable_cache_breakpoint": {"type": "boolean", "default": True},
                    },
                    "required": ["user_turn"],
                },
            },
            {
                "name": "get_memories",
                "description": (
                    "List stored conversational memories for a user or project scope "
                    "(excludes indexed code_symbol chunks by default unless include_code=true)."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"},
                        "limit": {"type": "integer", "default": 50},
                        "include_code": {"type": "boolean", "default": False},
                        "filters": {"type": "object"},
                    },
                },
            },
            {
                "name": "forget_memory",
                "description": "Delete a specific memory by ID.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "memory_id": {"type": "string"},
                    },
                    "required": ["memory_id"],
                },
            },
        ]
        return memory_tools + code_tools

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        args = dict(arguments or {})
        if name == "execute_memory_code":
            action = str(args.get("action") or "")
            sub_params = args.get("params") or {}
            return self.call_tool(action, sub_params)

        uid = str(args.get("user_id") or self.user_id)

        if name == "add_memory":
            extra_kwargs: dict[str, Any] = {}
            if "record_tier" in args:
                extra_kwargs["record_tier"] = args["record_tier"]
            if "slot_key" in args:
                extra_kwargs["slot_key"] = args["slot_key"]
            if "scope" in args:
                extra_kwargs["scope"] = args["scope"]
            res = self.client.add(
                str(args["text"]),
                user_id=uid,
                memory_id=args.get("memory_id"),
                metadata=args.get("metadata"),
                **extra_kwargs,
            )
            return {"content": [{"type": "text", "text": json.dumps(res)}]}

        if name == "add_scoped_rule":
            raw_text = str(args.get("text") or args.get("rule") or "")
            res = self.client.add_rule(
                raw_text,
                rule_id=args.get("rule_id"),
                do=args.get("do"),
                dont=args.get("dont"),
                scope=args.get("scope"),
                user_id=uid,
                metadata=args.get("metadata"),
            )
            return {"content": [{"type": "text", "text": json.dumps(res)}]}

        if name == "search_memories":
            merged_filters: dict[str, Any] = dict(args.get("filters") or {})
            if "include_code" in args and args["include_code"] is not None:
                merged_filters["include_code"] = bool(args["include_code"])
            if "record_tier" in args and args["record_tier"] is not None:
                merged_filters["record_tier"] = str(args["record_tier"])
            res = self.client.search(
                str(args["query"]),
                user_id=uid,
                limit=int(args.get("limit", 5)),
                filters=merged_filters if merged_filters else None,
            )
            return {"content": [{"type": "text", "text": json.dumps(res)}]}

        if name == "get_cache_aligned_prompt":
            turn = str(args.get("user_turn") or args.get("query") or args.get("prompt") or "")
            ctx = args.get("context")
            if not ctx or not isinstance(ctx, dict):
                ctx = {
                    k: v
                    for k, v in args.items()
                    if k not in ("user_turn", "query", "prompt", "top_k", "user_id", "enable_cache_breakpoint")
                }
            aligned = self.client.get_cache_aligned_prompt(
                turn,
                active_context=ctx,
                top_k=int(args.get("top_k", 5)),
                user_id=uid,
                enable_cache_breakpoint=bool(args.get("enable_cache_breakpoint", True)),
            )
            out = {
                "full_prompt_text": aligned.full_prompt_text,
                "zone1_rules_text": aligned.zone1_rules_text,
                "zone2_facts_text": aligned.zone2_facts_text,
                "whisper_block": aligned.whisper_block,
                "has_cache_breakpoint": aligned.has_cache_breakpoint,
                "token_economics": aligned.token_economics,
            }
            return {"content": [{"type": "text", "text": json.dumps(out)}]}

        if name == "get_memories":
            merged_filters = dict(args.get("filters") or {})
            if "include_code" in args and args["include_code"] is not None:
                merged_filters["include_code"] = bool(args["include_code"])
            res = self.client.get_all(
                user_id=uid,
                limit=int(args.get("limit", 50)),
                filters=merged_filters if merged_filters else None,
            )
            return {"content": [{"type": "text", "text": json.dumps(res)}]}

        if name == "forget_memory":
            res = self.client.forget(memory_id=str(args["memory_id"]), user_id=uid)
            return {"content": [{"type": "text", "text": json.dumps(res)}]}

        if name == "index_repository":
            target = args.get("path") or args.get("repo_path") or self.repo_path or "."
            max_files = int(args.get("max_files") or 10000)
            summary = self.indexer.index_directory(target, max_files=max_files)
            return {"content": [{"type": "text", "text": json.dumps(summary)}]}

        if name == "search_code_by_behavior":
            hits = search_code_by_behavior(
                self.client,
                str(args["query"]),
                top_k=int(args.get("top_k", 5)),
                user_id=uid,
                language=args.get("language"),
            )
            return {"content": [{"type": "text", "text": json.dumps({"results": hits})}]}

        if name == "find_bug_candidates":
            hits = find_bug_candidates(
                self.client,
                str(args["bug_description"]),
                stack_trace=str(args.get("stack_trace", "")),
                top_k=int(args.get("top_k", 5)),
                user_id=uid,
            )
            return {"content": [{"type": "text", "text": json.dumps({"results": hits})}]}

        if name == "intervene_memory":
            raw_text = str(args.get("text") or args.get("prompt") or "")
            resolved_project = (
                args.get("project_id")
                or args.get("projectId")
                or os.environ.get("SLASHML_PROJECT_ID")
            )
            resolved_session = (
                args.get("session_id")
                or args.get("sessionId")
                or os.environ.get("SLASHML_SESSION_ID")
            )
            overridden_ids = [
                str(x)
                for x in [
                    *(args.get("overridden_memory_ids") or []),
                    *(args.get("dismiss_memory_ids") or []),
                    *([args["override_memory_id"]] if args.get("override_memory_id") else []),
                ]
                if x
            ]
            res = self.client.intervene(
                raw_text,
                hook_event_name=str(args.get("hook_event_name") or "UserPromptSubmit"),
                prompt=str(args.get("prompt") or raw_text),
                tool_name=args.get("tool_name"),
                tool_input=args.get("tool_input"),
                tool_response=args.get("tool_response"),
                overridden_memory_ids=overridden_ids or None,
                user_id=uid,
                project_id=str(resolved_project) if resolved_project else None,
                session_id=str(resolved_session) if resolved_session else None,
                model=args.get("model") or os.environ.get("SLASHML_MODEL"),
                commit_writes=bool(args.get("commit_writes", True)),
                top_k=int(args.get("top_k") or args.get("limit") or 5),
            )
            return {"content": [{"type": "text", "text": json.dumps(res)}]}

        if name == "dismiss_intervention":
            mem_ids = [
                str(x)
                for x in [
                    *([args["memory_id"]] if args.get("memory_id") else []),
                    *(args.get("memory_ids") or []),
                    *(args.get("overridden_memory_ids") or []),
                ]
                if x
            ]
            if not mem_ids:
                raise ValueError("dismiss_intervention requires memory_id or memory_ids")
            reason = str(args.get("reason") or "Dismissed false-positive intervention for session")
            dedup_path = Path(
                os.environ.get("SLASHML_HOOK_STATE_PATH")
                or (Path.home() / ".slashml" / "hook_state.json")
            )
            try:
                dedup_state: dict[str, Any] = {"hashes": []}
                if dedup_path.exists():
                    dedup_state = json.loads(dedup_path.read_text(encoding="utf-8")) or {"hashes": []}
                ov_map = dedup_state.get("overridden_by_session")
                if not isinstance(ov_map, dict):
                    ov_map = {}
                    dedup_state["overridden_by_session"] = ov_map
                prev_glob = ov_map.get("_global") if isinstance(ov_map.get("_global"), list) else []
                ov_map["_global"] = list(dict.fromkeys([*prev_glob, *mem_ids]))[-64:]
                sess_key = str(args.get("session_id") or args.get("sessionId") or os.environ.get("SLASHML_SESSION_ID") or "").strip()
                if sess_key:
                    prev_s = ov_map.get(sess_key) if isinstance(ov_map.get(sess_key), list) else []
                    ov_map[sess_key] = list(dict.fromkeys([*prev_s, *mem_ids]))[-64:]
                dedup_path.parent.mkdir(parents=True, exist_ok=True)
                dedup_path.write_text(json.dumps(dedup_state), encoding="utf-8")
            except Exception:
                pass
            resolved_project = args.get("project_id") or args.get("projectId") or os.environ.get("SLASHML_PROJECT_ID")
            resolved_session = args.get("session_id") or args.get("sessionId") or os.environ.get("SLASHML_SESSION_ID")
            try:
                self.client.intervene(
                    f"Dismiss intervention for {', '.join(mem_ids)}: {reason}",
                    hook_event_name="UserPromptSubmit",
                    overridden_memory_ids=mem_ids,
                    dismiss_memory_ids=mem_ids,
                    user_id=uid,
                    project_id=str(resolved_project) if resolved_project else None,
                    session_id=str(resolved_session) if resolved_session else None,
                    commit_writes=False,
                )
            except Exception:
                pass
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(
                            {
                                "status": "dismissed",
                                "overridden_memory_ids": mem_ids,
                                "reason": reason,
                            }
                        ),
                    }
                ]
            }

        raise ValueError(f"Unknown MCP tool: {name!r}")

    def handle_rpc(self, request: dict[str, Any]) -> dict[str, Any] | None:
        method = request.get("method", "")
        req_id = request.get("id")
        params = request.get("params") or {}

        if (
            req_id is None
            or method == "notifications/initialized"
            or (isinstance(method, str) and method.startswith("notifications/"))
        ):
            return None

        if method == "ping":
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}

        if method == "initialize":
            proto = params.get("protocolVersion") or "2024-11-05"
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": proto,
                    "serverInfo": {"name": "ml-memory", "version": "1.0.10"},
                    "capabilities": {"tools": {}},
                },
            }

        if method == "resources/list":
            return {"jsonrpc": "2.0", "id": req_id, "result": {"resources": []}}

        if method == "resources/templates/list":
            return {"jsonrpc": "2.0", "id": req_id, "result": {"resourceTemplates": []}}

        if method == "prompts/list":
            return {"jsonrpc": "2.0", "id": req_id, "result": {"prompts": []}}

        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": self.list_tools()},
            }

        if method == "tools/call":
            try:
                out = self.call_tool(params.get("name", ""), params.get("arguments"))
                return {"jsonrpc": "2.0", "id": req_id, "result": out}
            except Exception as exc:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "isError": True,
                        "content": [{"type": "text", "text": str(exc)}],
                    },
                }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    def serve_stdio(self) -> None:
        for line in sys.stdin:
            raw = line.strip()
            if not raw:
                continue
            try:
                req = json.loads(raw)
            except json.JSONDecodeError:
                continue
            resp = self.handle_rpc(req)
            if resp is not None:
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()


HOOK_READ_ONLY_TOOLS = {
    "read",
    "read_file",
    "view_file",
    "grep",
    "rg",
    "glob",
    "find",
    "ls",
    "list_dir",
    "web_search",
    "search_web",
    "todowrite",
    "todoread",
    "get_memories",
    "search_memories",
    "search_code_by_behavior",
    "find_bug_candidates",
}


def install_ambient_hooks(api_key: str | None = None) -> Path:
    claude_settings_path = Path.home() / ".claude" / "settings.json"
    claude_settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings: dict[str, Any] = {}
    if claude_settings_path.exists():
        try:
            settings = json.loads(claude_settings_path.read_text(encoding="utf-8"))
        except Exception:
            settings = {}
    if not isinstance(settings.get("hooks"), dict):
        settings["hooks"] = {}
    hook_cmd = "slashml-mcp --hook"
    for event_name in ("UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"):
        settings["hooks"][event_name] = [
            {
                "matcher": ".*",
                "hooks": [{"type": "command", "command": hook_cmd, "timeout": 5}],
            }
        ]
    if api_key:
        env_dict = settings.get("env") if isinstance(settings.get("env"), dict) else {}
        settings["env"] = {**env_dict, "SLASHML_API_KEY": api_key}
    claude_settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    print(f"Configured / ml ambient lifecycle hooks in {claude_settings_path}")
    return claude_settings_path


def _telemetry_path() -> Path:
    return Path(
        os.environ.get("SLASHML_TELEMETRY_PATH")
        or (Path.home() / ".slashml" / "hook_telemetry.json")
    )


def _estimate_tokens(raw_str: str) -> int:
    s = (raw_str or "").strip()
    if not s:
        return 0
    return max(1, round(len(s) / 4))


def _load_hook_telemetry() -> dict[str, int]:
    defaults: dict[str, int] = {
        "pending_raw_tokens": 0,
        "pending_dropped_tokens": 0,
        "pending_dropped_events": 0,
        "local_total_raw_tokens": 0,
        "local_total_dropped_tokens": 0,
        "local_total_dropped_events": 0,
        "local_total_forwarded_events": 0,
        "local_memories_assimilated": 0,
        "local_memories_superseded": 0,
        "local_amnesia_intercepted": 0,
    }
    p = _telemetry_path()
    try:
        if p.exists():
            parsed = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(parsed, dict):
                for k in defaults:
                    if k in parsed:
                        defaults[k] = int(parsed[k] or 0)
    except Exception:
        pass
    return defaults


def _save_hook_telemetry(state: dict[str, int]) -> None:
    p = _telemetry_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(state), encoding="utf-8")
    except Exception:
        pass


def _record_local_hook_drop(raw_tokens: int) -> None:
    t = max(1, int(raw_tokens or 1))
    state = _load_hook_telemetry()
    state["pending_raw_tokens"] += t
    state["pending_dropped_tokens"] += t
    state["pending_dropped_events"] += 1
    state["local_total_raw_tokens"] += t
    state["local_total_dropped_tokens"] += t
    state["local_total_dropped_events"] += 1
    _save_hook_telemetry(state)


def run_status_command(
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    user_id: str = "default",
    as_json: bool = False,
    transport: TransportCallable | None = None,
) -> int:
    local_state = _load_hook_telemetry()
    server_stats: dict[str, Any] | None = None
    resolved_key = api_key or os.environ.get("SLASHML_API_KEY")
    if resolved_key:
        try:
            client = MemoryClient(api_key=resolved_key, base_url=base_url, transport=transport)
            server_stats = client.status(
                user_id=user_id,
                client_raw_tokens_delta=local_state["pending_raw_tokens"],
                client_dropped_tokens_delta=local_state["pending_dropped_tokens"],
                client_dropped_events_delta=local_state["pending_dropped_events"],
            )
            if isinstance(server_stats, dict):
                local_state["pending_raw_tokens"] = 0
                local_state["pending_dropped_tokens"] = 0
                local_state["pending_dropped_events"] = 0
                _save_hook_telemetry(local_state)
        except Exception:
            server_stats = None

    total_tokens = (
        int(server_stats["conversation_tokens_processed"])
        if server_stats and isinstance(server_stats.get("conversation_tokens_processed"), (int, float))
        else int(local_state["local_total_raw_tokens"])
    )
    noise_tokens = (
        int(server_stats["noise_tokens_filtered"])
        if server_stats and isinstance(server_stats.get("noise_tokens_filtered"), (int, float))
        else int(local_state["local_total_dropped_tokens"])
    )
    noise_pct = (
        float(server_stats["stream_noise_filtered_pct"])
        if server_stats and isinstance(server_stats.get("stream_noise_filtered_pct"), (int, float))
        else (round((noise_tokens / total_tokens) * 100.0, 1) if total_tokens > 0 else 0.0)
    )
    assimilated = (
        int(server_stats["memories_assimilated"])
        if server_stats and isinstance(server_stats.get("memories_assimilated"), (int, float))
        else int(local_state["local_memories_assimilated"])
    )
    superseded = (
        int(server_stats["memories_superseded"])
        if server_stats and isinstance(server_stats.get("memories_superseded"), (int, float))
        else int(local_state["local_memories_superseded"])
    )
    intercepted = (
        int(server_stats["amnesia_episodes_intercepted"])
        if server_stats and isinstance(server_stats.get("amnesia_episodes_intercepted"), (int, float))
        else int(local_state["local_amnesia_intercepted"])
    )
    active_vault = (
        int(server_stats["active_vault_memories"])
        if server_stats and isinstance(server_stats.get("active_vault_memories"), (int, float))
        else assimilated
    )
    summary_line = (
        str(server_stats["summary_line"])
        if server_stats and server_stats.get("summary_line")
        else f"{assimilated} rules learned passively • {intercepted} amnesia episodes intercepted • {round(noise_pct)}% stream noise filtered"
    )

    payload: dict[str, Any] = {
        "status": "ok",
        "user_id": user_id,
        "conversation_tokens_processed": total_tokens,
        "noise_tokens_filtered": noise_tokens,
        "stream_noise_filtered_pct": noise_pct,
        "memories_assimilated": assimilated,
        "memories_superseded": superseded,
        "amnesia_episodes_intercepted": intercepted,
        "active_vault_memories": active_vault,
        "summary_line": summary_line,
        "recent_assimilated": (server_stats or {}).get("recent_assimilated") or [],
        "recent_intercepted": (server_stats or {}).get("recent_intercepted") or [],
    }
    if as_json:
        print(json.dumps(payload, indent=2))
        return 0

    print(f"/ ml Ambient Stream Status ({user_id})")
    print(f"  {summary_line}\n")
    print(f"  # Conversation Tokens Processed : {total_tokens:,}")
    print(f"  % Stream Noise Filtered         : {noise_pct:.1f}% ({noise_tokens:,} tokens dropped)")
    superseded_suffix = f" ({superseded} superseded in-place)" if superseded > 0 else ""
    print(f"  # New Memories Assimilated      : {assimilated}{superseded_suffix}")
    print(f"  # Amnesia Episodes Intercepted  : {intercepted}")
    return 0


def _resolve_hook_project_id(payload: dict[str, Any], repo: str | None = None) -> str:
    for val in (
        payload.get("project_id"),
        payload.get("projectId"),
        os.environ.get("SLASHML_PROJECT_ID"),
    ):
        if isinstance(val, str) and val.strip():
            return val.strip()
    ws_paths = payload.get("workspacePaths") or payload.get("workspace_paths")
    first_ws = ws_paths[0] if isinstance(ws_paths, list) and ws_paths else None
    for d in (repo, first_ws, payload.get("cwd"), os.getcwd()):
        if isinstance(d, str) and d.strip():
            cleaned = d.strip().rstrip("/\\")
            base = os.path.basename(cleaned)
            if base and base not in (".", "/"):
                return base
    return ""


def run_ambient_hook_mode(
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    user_id: str = "default",
    repo: str | None = None,
    transport: TransportCallable | None = None,
) -> int:
    raw_input = sys.stdin.read().strip()
    if not raw_input:
        sys.stdout.write("{}\n")
        sys.stdout.flush()
        return 0
    try:
        payload = json.loads(raw_input)
        if not isinstance(payload, dict):
            payload = {"hook_event_name": "UserPromptSubmit", "prompt": str(raw_input)}
    except Exception:
        payload = {"hook_event_name": "UserPromptSubmit", "prompt": raw_input}

    raw_event_name = str(
        payload.get("hook_event_name")
        or payload.get("hook_event")
        or payload.get("event")
        or "UserPromptSubmit"
    )
    is_gemini_hook = bool(
        payload.get("conversationId")
        or payload.get("stepIdx") is not None
        or payload.get("invocationNum") is not None
        or raw_event_name in ("PreInvocation", "BeforeTool", "AfterTool", "AfterAgent")
    )
    event_map = {
        "PreInvocation": "UserPromptSubmit",
        "BeforeTool": "PreToolUse",
        "AfterTool": "PostToolUse",
        "AfterAgent": "Stop",
    }
    hook_event = event_map.get(raw_event_name, raw_event_name)
    if not is_gemini_hook and raw_event_name == "Stop" and payload.get("stop_hook_active"):
        sys.stdout.write("{}\n")
        sys.stdout.flush()
        return 0
    tool_call_obj = payload.get("toolCall") if isinstance(payload.get("toolCall"), dict) else None
    tool_name_raw = payload.get("tool_name") or (tool_call_obj.get("name") if tool_call_obj else None)
    tool_name = str(tool_name_raw).strip() if tool_name_raw else None

    tool_in = (
        payload.get("tool_input")
        if isinstance(payload.get("tool_input"), dict)
        else (tool_call_obj.get("args") if tool_call_obj and isinstance(tool_call_obj.get("args"), dict) else None)
    )

    dedup_path = Path(
        os.environ.get("SLASHML_HOOK_STATE_PATH")
        or (Path.home() / ".slashml" / "hook_state.json")
    )
    dedup_state: dict[str, Any] = {"hashes": []}
    try:
        if dedup_path.exists():
            dedup_state = json.loads(dedup_path.read_text(encoding="utf-8")) or {"hashes": []}
    except Exception:
        dedup_state = {"hashes": []}

    session_id = str(
        payload.get("conversationId")
        or payload.get("session_id")
        or payload.get("sessionId")
        or os.environ.get("SLASHML_SESSION_ID")
        or ""
    ).strip()
    project_id = _resolve_hook_project_id(payload, repo=repo)
    scope_state_key = f"{project_id or '_default'}:{session_id or '_default'}"

    # / ml (SlashML · https://slashml.ai · github.com/slashml-ai/ml-memory · support@slashml.ai)
    def _persist_pending_tool_context() -> None:
        if not isinstance(tool_in, dict):
            return
        ref_obj = {
            k: str(tool_in[k]).strip()[:400]
            for k in ("file_path", "path", "Path", "command", "CommandLine")
            if isinstance(tool_in.get(k), str) and str(tool_in[k]).strip()
        }
        if not ref_obj:
            return
        pending = dedup_state.get("pending_tool_input_by_session")
        if not isinstance(pending, dict):
            pending = {}
            dedup_state["pending_tool_input_by_session"] = pending
        pending[scope_state_key] = ref_obj
        try:
            dedup_path.parent.mkdir(parents=True, exist_ok=True)
            dedup_path.write_text(json.dumps(dedup_state), encoding="utf-8")
        except Exception:
            pass

    if hook_event in ("PreToolUse", "PostToolUse") and tool_name:
        if tool_name.lower() in HOOK_READ_ONLY_TOOLS:
            _persist_pending_tool_context()
            _record_local_hook_drop(_estimate_tokens(raw_input))
            sys.stdout.write("{}\n")
            sys.stdout.flush()
            return 0

    tool_summary = (
        tool_in.get("command")
        or tool_in.get("CommandLine")
        or tool_in.get("Replacement")
        or tool_in.get("new_string")
        or tool_in.get("Content")
        or tool_in.get("content")
        or json.dumps(tool_in)
        if tool_in
        else ""
    )
    if (
        hook_event in ("PreToolUse", "PostToolUse")
        and tool_name
        and re.match(r"^(bash|run_command|shell)$", tool_name, re.IGNORECASE)
    ):
        cmd_check = re.sub(r"^\s*cd\s+[^&;]+(?:&&|;)\s*", "", str(tool_summary or "").strip().lower()).strip()
        is_read_only_cmd = bool(
            re.match(
                r"^(ls\b|pwd\b|cat\s|head\s|tail\s|grep\s|rg\s|find\s|git\s+(status|log|diff|branch|show|worktree|rev-parse|remote|tag|describe)\b|which\s|whoami\b|stat\s|wc\s)",
                cmd_check,
            )
            and not re.search(r"[>]|(\brm\s|\bmv\s|\bcp\s|git\s+(push|commit)|\binstall\b)", cmd_check)
        )
        if is_read_only_cmd:
            _persist_pending_tool_context()
            _record_local_hook_drop(_estimate_tokens(raw_input))
            sys.stdout.write("{}\n")
            sys.stdout.flush()
            return 0

    transcript_file = payload.get("transcriptPath") or payload.get("transcript_path")
    transcript_reply = ""
    if hook_event == "Stop" and not payload.get("last_assistant_message") and isinstance(transcript_file, str) and transcript_file.strip():
        try:
            tp = Path(transcript_file.strip())
            if tp.exists():
                raw_tail = tp.read_bytes()[-65536:].decode("utf-8", errors="ignore")
                for t_line in reversed(raw_tail.splitlines()):
                    t_line = t_line.strip()
                    if not t_line.startswith("{"):
                        continue
                    try:
                        entry = json.loads(t_line)
                    except Exception:
                        continue
                    if not isinstance(entry, dict):
                        continue
                    if entry.get("type") == "PLANNER_RESPONSE" and isinstance(entry.get("content"), str) and entry["content"].strip():
                        transcript_reply = entry["content"].strip()
                        break
                    msg_obj = entry.get("message") if isinstance(entry.get("message"), dict) else entry
                    if isinstance(msg_obj, dict) and msg_obj.get("role") == "assistant":
                        m_content = msg_obj.get("content")
                        if isinstance(m_content, str) and m_content.strip():
                            transcript_reply = m_content.strip()
                            break
                        if isinstance(m_content, list):
                            parts = [
                                str(b.get("text") or "").strip()
                                for b in m_content
                                if isinstance(b, dict) and (b.get("type") == "text" or isinstance(b.get("text"), str))
                            ]
                            parts = [p for p in parts if p]
                            if parts:
                                transcript_reply = "\n".join(parts).strip()
                                break
        except Exception:
            pass

    raw_delta = str(
        payload.get("prompt")
        or payload.get("text")
        or payload.get("user_prompt")
        or payload.get("last_assistant_message")
        or payload.get("assistant_message")
        or payload.get("response")
        or transcript_reply
        or tool_summary
        or (json.dumps(payload["tool_response"]) if payload.get("tool_response") else "")
    )
    delta_text = re.sub(r"<thinking>[\s\S]*?</thinking>", " ", raw_delta, flags=re.IGNORECASE)
    delta_text = re.sub(r"[\u2500-\u257f]+", " ", delta_text)
    delta_text = re.sub(r"\s+", " ", delta_text).strip()[:1024]

    if (
        not delta_text
        or len(delta_text) < 4
        or re.match(r"^(ok|okay|thanks|thank you|yes|no|sure|cool|lgtm)[.!]*$", delta_text, re.IGNORECASE)
    ):
        _record_local_hook_drop(_estimate_tokens(raw_delta or raw_input))
        sys.stdout.write("{}\n")
        sys.stdout.flush()
        return 0

    step_key = str(
        payload.get("stepIdx")
        if payload.get("stepIdx") is not None
        else (
            payload.get("invocationNum")
            if payload.get("invocationNum") is not None
            else (payload.get("executionNum") if payload.get("executionNum") is not None else "")
        )
    )
    delta_hash = hashlib.sha1(
        f"{project_id}:{session_id}:{step_key}:{hook_event}:{tool_name or ''}:{delta_text.lower()}".encode("utf-8")
    ).hexdigest()[:16]
    hashes = dedup_state.get("hashes") if isinstance(dedup_state.get("hashes"), list) else []
    if delta_hash in hashes:
        _record_local_hook_drop(_estimate_tokens(delta_text))
        sys.stdout.write("{}\n")
        sys.stdout.flush()
        return 0

    resolved_key = api_key or os.environ.get("SLASHML_API_KEY")
    if not resolved_key:
        sys.stdout.write("{}\n")
        sys.stdout.flush()
        return 0

    local_state = _load_hook_telemetry()
    turn_tokens = _estimate_tokens(raw_delta or delta_text)

    effective_tool_in = tool_in
    pending_map = dedup_state.get("pending_tool_input_by_session")
    if not effective_tool_in and isinstance(pending_map, dict) and scope_state_key in pending_map:
        effective_tool_in = pending_map.pop(scope_state_key, None)
    elif effective_tool_in and isinstance(pending_map, dict):
        pending_map.pop(scope_state_key, None)

    whispered_by_session = dedup_state.get("whispered_by_session")
    if not isinstance(whispered_by_session, dict):
        whispered_by_session = {}
        dedup_state["whispered_by_session"] = whispered_by_session
    whispered_blocks_by_session = dedup_state.get("whispered_blocks_by_session")
    if not isinstance(whispered_blocks_by_session, dict):
        whispered_blocks_by_session = {}
        dedup_state["whispered_blocks_by_session"] = whispered_blocks_by_session
    blocked_by_session = dedup_state.get("blocked_by_session")
    if not isinstance(blocked_by_session, dict):
        blocked_by_session = {}
        dedup_state["blocked_by_session"] = blocked_by_session
    overridden_by_session = dedup_state.get("overridden_by_session")
    if not isinstance(overridden_by_session, dict):
        overridden_by_session = {}
        dedup_state["overridden_by_session"] = overridden_by_session
    blocked_actions_by_session = dedup_state.get("blocked_actions_by_session")
    if not isinstance(blocked_actions_by_session, dict):
        blocked_actions_by_session = {}
        dedup_state["blocked_actions_by_session"] = blocked_actions_by_session
    whisper_key = session_id or scope_state_key
    is_mid_turn_cont = raw_event_name == "PreInvocation" and int(payload.get("invocationNum") or 1) > 1
    target_sig = (
        str(
            tool_in.get("file_path")
            or tool_in.get("path")
            or tool_in.get("Path")
            or tool_in.get("command")
            or tool_in.get("CommandLine")
            or delta_text[:120]
        ).strip().lower()
        if isinstance(tool_in, dict)
        else delta_text[:120].lower()
    )
    if hook_event == "UserPromptSubmit" and not is_mid_turn_cont and whisper_key:
        whispered_blocks_by_session[whisper_key] = []
    if hook_event == "PreToolUse" and whisper_key:
        prev_act = blocked_actions_by_session.get(whisper_key, [])
        if isinstance(prev_act, list) and prev_act:
            suffix = f":{tool_name or ''}:{target_sig}"
            matched_ids = [
                entry[: -len(suffix)]
                for entry in prev_act
                if isinstance(entry, str) and entry.endswith(suffix) and entry[: -len(suffix)]
            ]
            if matched_ids:
                prev_ov = overridden_by_session.get(whisper_key, [])
                if not isinstance(prev_ov, list):
                    prev_ov = []
                overridden_by_session[whisper_key] = list(dict.fromkeys([*prev_ov, *matched_ids]))[-32:]
    session_whispered = (
        [str(x) for x in whispered_by_session.get(whisper_key, []) if x]
        if whisper_key and isinstance(whispered_by_session.get(whisper_key), list)
        else []
    )
    session_whispered_blocks = (
        [str(x) for x in whispered_blocks_by_session.get(whisper_key, []) if x]
        if whisper_key and isinstance(whispered_blocks_by_session.get(whisper_key), list)
        else []
    )
    session_overridden = [
        *(overridden_by_session.get(whisper_key, []) if whisper_key and isinstance(overridden_by_session.get(whisper_key), list) else []),
        *(overridden_by_session.get("_global", []) if isinstance(overridden_by_session.get("_global"), list) else []),
        *(payload.get("overridden_memory_ids") if isinstance(payload.get("overridden_memory_ids"), list) else []),
        *(tool_in.get("override_memory_ids") if isinstance(tool_in, dict) and isinstance(tool_in.get("override_memory_ids"), list) else []),
        *(tool_in.get("overridden_memory_ids") if isinstance(tool_in, dict) and isinstance(tool_in.get("overridden_memory_ids"), list) else []),
    ]
    overridden_memory_ids = list(dict.fromkeys(str(x) for x in session_overridden if x))
    stream_text_for_intervene = (
        f"{chr(10).join(session_whispered_blocks)}\n{delta_text}"
        if hook_event in ("Stop", "PreToolUse")
        and session_whispered_blocks
        and "<memory>" not in delta_text.lower()
        else delta_text
    )

    try:
        client = MemoryClient(api_key=resolved_key, base_url=base_url, transport=transport)
        resp = client.intervene(
            stream_text_for_intervene,
            hook_event_name=hook_event,
            prompt=str(payload.get("prompt") or delta_text),
            last_assistant_message=delta_text if hook_event == "Stop" else None,
            stop_hook_active=bool(payload.get("stop_hook_active")) if hook_event == "Stop" else False,
            whispered_memory_ids=session_whispered if session_whispered else None,
            overridden_memory_ids=overridden_memory_ids if overridden_memory_ids else None,
            tool_name=tool_name,
            tool_input=effective_tool_in,
            tool_response=payload.get("tool_response"),
            user_id=user_id,
            project_id=project_id or None,
            session_id=session_id or None,
            model=os.environ.get("SLASHML_MODEL"),
            commit_writes=not is_mid_turn_cont,
            client_raw_tokens_delta=local_state["pending_raw_tokens"],
            client_dropped_tokens_delta=local_state["pending_dropped_tokens"],
            client_dropped_events_delta=local_state["pending_dropped_events"],
        )
        local_state["pending_raw_tokens"] = 0
        local_state["pending_dropped_tokens"] = 0
        local_state["pending_dropped_events"] = 0
        local_state["local_total_raw_tokens"] += turn_tokens
        local_state["local_total_forwarded_events"] += 1
        is_actionable = bool(
            isinstance(resp, dict)
            and (
                resp.get("should_write")
                or resp.get("should_intervene")
                or resp.get("intervene")
                or resp.get("write_decision") in ("ADD", "SUPERSEDE")
            )
        )
        if isinstance(resp, dict):
            w_dec = resp.get("write_decision")
            if w_dec == "NOP" and not is_actionable:
                local_state["local_total_dropped_tokens"] += turn_tokens
                local_state["local_total_dropped_events"] += 1
            elif w_dec in ("ADD", "SUPERSEDE") or resp.get("should_write"):
                local_state["local_memories_assimilated"] += 1
                if w_dec == "SUPERSEDE" or resp.get("write_novelty_action") == "SUPERSEDES":
                    local_state["local_memories_superseded"] += 1
                dedup_state["hashes"] = []
            if resp.get("intervene") or resp.get("should_intervene"):
                local_state["local_amnesia_intercepted"] += 1
                triggered_ids: list[str] = []
                if isinstance(resp.get("violated_memory_ids"), list):
                    triggered_ids.extend(str(x) for x in resp["violated_memory_ids"] if x)
                if resp.get("violated_memory_id"):
                    triggered_ids.append(str(resp["violated_memory_id"]))
                if resp.get("triggered_memory_id"):
                    triggered_ids.append(str(resp["triggered_memory_id"]))
                if whisper_key and triggered_ids:
                    prev_w = whispered_by_session.get(whisper_key, [])
                    if not isinstance(prev_w, list):
                        prev_w = []
                    merged_w = list(dict.fromkeys([*prev_w, *triggered_ids]))
                    whispered_by_session[whisper_key] = merged_w[-16:]
                    if resp.get("intervention_severity") == "BLOCK":
                        prev_blk = blocked_by_session.get(whisper_key, [])
                        if not isinstance(prev_blk, list):
                            prev_blk = []
                        blocked_by_session[whisper_key] = list(dict.fromkeys([*prev_blk, *triggered_ids]))[-16:]
                        if hook_event == "PreToolUse":
                            prev_act_list = blocked_actions_by_session.get(whisper_key, [])
                            if not isinstance(prev_act_list, list):
                                prev_act_list = []
                            act_keys = [f"{mid}:{tool_name or ''}:{target_sig}" for mid in triggered_ids]
                            blocked_actions_by_session[whisper_key] = list(dict.fromkeys([*prev_act_list, *act_keys]))[-32:]
                int_msg = resp.get("intervention_message")
                if whisper_key and isinstance(int_msg, str) and int_msg:
                    msg_tags = re.findall(r"<memory>[\s\S]*?</memory>", int_msg, flags=re.IGNORECASE)
                    if msg_tags:
                        prev_b = whispered_blocks_by_session.get(whisper_key, [])
                        if not isinstance(prev_b, list):
                            prev_b = []
                        merged_b = list(dict.fromkeys([*prev_b, *(t.strip() for t in msg_tags)]))
                        whispered_blocks_by_session[whisper_key] = merged_b[-8:]
        if not is_actionable:
            dedup_state["hashes"] = [*hashes[-63:], delta_hash]
        try:
            dedup_path.parent.mkdir(parents=True, exist_ok=True)
            dedup_path.write_text(json.dumps(dedup_state), encoding="utf-8")
        except Exception:
            pass
        _save_hook_telemetry(local_state)

        hook_out = resp.get("hook_output") if isinstance(resp, dict) else {}
        if not isinstance(hook_out, dict):
            hook_out = {}
        sys.stdout.write(json.dumps(hook_out) + "\n")
        sys.stdout.flush()
    except Exception:
        sys.stdout.write("{}\n")
        sys.stdout.flush()
    return 0


def main(
    argv: list[str] | None = None,
    *,
    code_only_default: bool = False,
    code_mode_default: bool = False,
) -> int:
    parser = argparse.ArgumentParser(prog="slashml-mcp")
    parser.add_argument("command", nargs="?", default=None, help="Optional command (e.g. 'init')")
    parser.add_argument("-v", "--version", action="version", version="1.0.10")
    parser.add_argument("--init", action="store_true", help="Configure ml-memory MCP in IDE configs")
    parser.add_argument("--skill", default=None, help="Skill or IDE target filter (e.g. ml-memory, cursor)")
    parser.add_argument("--api-key", default=None, help="SlashML Cloud API key (or SLASHML_API_KEY)")
    parser.add_argument("--base-url", default=None, help="SlashML Cloud base URL")
    parser.add_argument(
        "--console-url",
        default=os.environ.get("SLASHML_CONSOLE_URL", DEFAULT_CONSOLE_URL),
        help="SlashML Console URL for CLI signup/verification",
    )
    parser.add_argument("--user-id", default="default", help="Default user/workspace namespace")
    parser.add_argument("--repo", "--workspace", dest="repo", default=None, help="Repository/workspace path to auto-index")
    parser.add_argument(
        "--signup",
        default=None,
        metavar="WORK_EMAIL",
        help="Request a 6-digit verification code via work email (@company.com; for @gmail.com / @hotmail.com sign in with Google/GitHub at https://app.slashml.ai)",
    )
    parser.add_argument("--verify", nargs="+", default=None, metavar=("WORK_EMAIL", "CODE"), help="Verify work email and 6-digit code to provision SLASHML_API_KEY")
    parser.add_argument("--code", default=None, help="6-digit verification code (optional alternative to positional arg)")
    parser.add_argument("--write-env", action="store_true", help="Write SLASHML_API_KEY to .env")
    parser.add_argument("--hook", action="store_true", help="Run as a Claude Code / Cursor lifecycle hook (reads JSON on stdin, outputs hookSpecificOutput)")
    parser.add_argument("--install-hooks", action="store_true", help="Configure ambient lifecycle hooks in ~/.claude/settings.json")
    parser.add_argument("--status", action="store_true", help="Show ambient stream ROI & telemetry (tokens processed, % stream noise filtered, memories assimilated, amnesia episodes intercepted)")
    parser.add_argument("--json", action="store_true", help="Output status telemetry as raw JSON")
    parser.add_argument("--code-only", action="store_true", default=code_only_default)
    parser.add_argument("--code-mode", action="store_true", default=code_mode_default)
    args = parser.parse_args(argv)

    if args.signup:
        email = _assert_cli_work_email(args.signup)
        data = _console_post(args.console_url, "/api/auth/magic-link/request", {"email": email, "source": "cli"})
        out: dict[str, Any] = {
            "status": "verification_code_sent",
            "email": email,
            "message": (
                f"A 6-digit verification code has been sent to {email}. "
                f"Ask the user for the 6-digit code and run: slashml-mcp --verify {email} <6-digit-code>"
            ),
        }
        if data.get("dev_otp_code"):
            out["dev_otp_code"] = data["dev_otp_code"]
        print(json.dumps(out))
        return 0

    if args.verify:
        email = _assert_cli_work_email(args.verify[0])
        code = args.verify[1].strip() if len(args.verify) > 1 else (args.code or "").strip()
        if not code:
            raise SystemExit("Error: Missing 6-digit verification code. Usage: slashml-mcp --verify <email> <6-digit-code>")
        data = _console_post(
            args.console_url,
            "/api/auth/magic-link/verify",
            {"email": email, "otp_code": code, "code": code, "issue_cli_key": True},
        )
        provisioned_key = data.get("initial_api_key") or data.get("api_key") or data.get("apiKey")
        if not provisioned_key:
            raise SystemExit("Error: Account verified, but no API key was returned.")
        env_path: Path | None = None
        if args.write_env or args.init:
            env_path = _save_api_key_to_env(str(provisioned_key))
        if args.init:
            configure_mcp_targets(skill=args.skill, api_key=str(provisioned_key), repo=args.repo, write_env=False)
        res_payload: dict[str, Any] = {
            "status": "authenticated",
            "email": email,
            "api_key": provisioned_key,
            "mcp_server": "ml-memory",
        }
        if env_path is not None:
            res_payload["env_saved"] = str(env_path)
        print(json.dumps(res_payload))
        return 0

    if args.init or args.command == "init":
        configure_mcp_targets(
            skill=args.skill,
            api_key=args.api_key,
            repo=args.repo,
            write_env=args.write_env,
        )
        return 0

    if args.install_hooks or args.command == "install-hooks":
        install_ambient_hooks(api_key=args.api_key)
        return 0

    if args.status or args.command == "status":
        return run_status_command(
            api_key=args.api_key,
            base_url=args.base_url,
            user_id=args.user_id,
            as_json=args.json,
        )

    if args.hook or args.command == "hook":
        return run_ambient_hook_mode(
            api_key=args.api_key,
            base_url=args.base_url,
            user_id=args.user_id,
            repo=args.repo,
        )

    server = SlashMLMCPServer(
        api_key=args.api_key,
        base_url=args.base_url,
        user_id=args.user_id,
        code_only=args.code_only,
        code_mode=args.code_mode,
        repo_path=args.repo,
    )
    if args.repo:
        server.indexer.index_directory(args.repo)
    server.serve_stdio()
    return 0


def main_code_only(argv: list[str] | None = None) -> int:
    return main(argv, code_only_default=True)


if __name__ == "__main__":
    raise SystemExit(main())
