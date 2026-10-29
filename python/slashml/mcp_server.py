"""Model Context Protocol (MCP) Server for `/ ml` (`https://api.slashml.ai`).

Runs locally over JSON-RPC 2.0 `stdio` and forwards all memory and code search
operations to the `/ ml` Cloud API (`https://api.slashml.ai`).
"""

from __future__ import annotations

import argparse
import json
import os
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
                        "`index_repository`, `search_code_by_behavior`, `find_bug_candidates`) "
                        "to `/ ml` Cloud."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": [
                                    "add_memory",
                                    "search_memories",
                                    "get_memories",
                                    "forget_memory",
                                    "index_repository",
                                    "search_code_by_behavior",
                                    "find_bug_candidates",
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
                    "snippet in `/ ml` Cloud (`$0` LLM extraction cost)."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "user_id": {"type": "string"},
                        "memory_id": {"type": "string"},
                        "metadata": {"type": "object"},
                    },
                    "required": ["text"],
                },
            },
            {
                "name": "search_memories",
                "description": "Retrieve relevant memories and code context for a natural-language query.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "user_id": {"type": "string"},
                        "limit": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "get_memories",
                "description": "List stored memories for a user or project scope.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"},
                        "limit": {"type": "integer", "default": 50},
                    },
                },
            },
            {
                "name": "forget_memory",
                "description": "Physically unlearn and delete a specific memory ID in O(1).",
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
            res = self.client.add(
                str(args["text"]),
                user_id=uid,
                memory_id=args.get("memory_id"),
                metadata=args.get("metadata"),
            )
            return {"content": [{"type": "text", "text": json.dumps(res)}]}

        if name == "search_memories":
            res = self.client.search(
                str(args["query"]),
                user_id=uid,
                limit=int(args.get("limit", 5)),
            )
            return {"content": [{"type": "text", "text": json.dumps(res)}]}

        if name == "get_memories":
            res = self.client.get_all(
                user_id=uid,
                limit=int(args.get("limit", 50)),
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
                    "serverInfo": {"name": "ml-memory", "version": "1.0.3"},
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


def main(
    argv: list[str] | None = None,
    *,
    code_only_default: bool = False,
    code_mode_default: bool = False,
) -> int:
    parser = argparse.ArgumentParser(prog="slashml-mcp")
    parser.add_argument("command", nargs="?", default=None, help="Optional command (e.g. 'init')")
    parser.add_argument("-v", "--version", action="version", version="1.0.3")
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
