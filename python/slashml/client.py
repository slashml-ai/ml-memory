"""Official HTTP Python SDK for / ml (`https://api.slashml.ai`).

Provides `MemoryClient` / `SlashMLMemory` (100% 1:1 Mem0 Cloud Client & `/ ml` API drop-in).
"""

from __future__ import annotations

import asyncio
import http.client
import json
import os
import socket
import ssl
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

DEFAULT_BASE_URL = "https://api.slashml.ai"


def _normalize_redact_policy(
    value: str | list[str] | tuple[str, ...] | None,
) -> str | list[str] | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        return cleaned if cleaned else None
    raw = str(value).strip()
    if not raw:
        return None
    if "," in raw:
        parts = [part.strip() for part in raw.split(",") if part.strip()]
        return parts if parts else None
    return raw


def _build_ssl_context() -> ssl.SSLContext:
    """Build an SSLContext that works out-of-the-box on macOS Python.framework builds."""
    ctx = ssl.create_default_context()
    try:
        import certifi  # type: ignore[import-not-found]

        ctx.load_verify_locations(cafile=certifi.where())
        return ctx
    except Exception:
        pass
    for cafile in ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt"):
        if os.path.isfile(cafile):
            try:
                ctx.load_verify_locations(cafile=cafile)
                break
            except Exception:
                pass
    return ctx


class _FastHTTPConnection(http.client.HTTPConnection):
    """Persistent HTTP/1.1 connection."""

    def connect(self) -> None:
        super().connect()
        if self.sock is not None:
            try:
                self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except OSError:
                pass


class _FastHTTPSConnection(http.client.HTTPSConnection):
    """Persistent HTTPS/1.1 connection."""

    def connect(self) -> None:
        super().connect()
        if self.sock is not None:
            try:
                self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except OSError:
                pass

TransportCallable = Callable[
    [str, str, dict[str, Any] | None, dict[str, str]],
    dict[str, Any] | list[Any],
]


class SlashMLAPIError(RuntimeError):
    """Raised when the / ml Cloud API returns a non-2xx HTTP status or network error."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_body: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class MemoryClient:
    """100% Mem0-compatible & `/ ml` native HTTP client targeting `https://api.slashml.ai`.

    Compatible with both:
    - `from slashml import MemoryClient, SlashMLMemory, SlashMLClient`
    - `from mem0 import MemoryClient` (drop-in replacement)
    """

    def __init__(
        self,
        api_key: str | None = None,
        host: str | None = None,
        *,
        base_url: str | None = None,
        org_id: str | None = None,
        project_id: str | None = None,
        agent_id: str | None = None,
        caller_agent_id: str | None = None,
        redact_policy: str | list[str] | None = None,
        redact_scope: str | None = None,
        model: str = "slashml-nano",
        timeout_s: float = 30.0,
        transport: TransportCallable | None = None,
    ) -> None:
        resolved_key = (
            api_key
            or os.environ.get("SLASHML_API_KEY")
            or os.environ.get("MEM0_API_KEY")
            or ""
        )
        resolved_url = (
            base_url
            or host
            or os.environ.get("SLASHML_BASE_URL")
            or os.environ.get("SLASHML_API_URL")
            or DEFAULT_BASE_URL
        )
        explicit_agent_id = agent_id if agent_id is not None else caller_agent_id
        resolved_agent_id = (
            explicit_agent_id
            if explicit_agent_id is not None
            else os.environ.get("SLASHML_AGENT_ID")
        )
        resolved_redact_policy = (
            redact_policy
            if redact_policy is not None
            else os.environ.get("SLASHML_REDACT_POLICY")
        )
        resolved_redact_scope = (
            redact_scope
            if redact_scope is not None
            else os.environ.get("SLASHML_REDACT_SCOPE")
        )
        self.api_key = str(resolved_key).strip()
        self.base_url = str(resolved_url).rstrip("/")
        self.host = self.base_url
        self.org_id = org_id or os.environ.get("SLASHML_ORG_ID")
        self.project_id = project_id or os.environ.get("SLASHML_PROJECT_ID")
        self.agent_id = str(resolved_agent_id).strip() if resolved_agent_id and str(resolved_agent_id).strip() else None
        self.caller_agent_id = self.agent_id
        self.redact_policy = _normalize_redact_policy(resolved_redact_policy)
        self.redact_scope = str(resolved_redact_scope).strip() if resolved_redact_scope and str(resolved_redact_scope).strip() else None
        self.model = model
        self.timeout_s = float(timeout_s)
        self._transport = transport
        self._parsed_base = urllib.parse.urlparse(self.base_url)
        self._tls_local = threading.local()
        self.project = _ProjectManager(self)
        self.agents = _AgentsManager(self)

    def close(self) -> None:
        """Close the thread-local persistent HTTP connection."""
        self._close_connection()

    def __enter__(self) -> "MemoryClient":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def _get_connection(self) -> http.client.HTTPConnection:
        conn: http.client.HTTPConnection | None = getattr(self._tls_local, "conn", None)
        if conn is not None:
            return conn
        scheme = (self._parsed_base.scheme or "https").lower()
        host = self._parsed_base.hostname or "api.slashml.ai"
        port = self._parsed_base.port
        if scheme == "http":
            conn = _FastHTTPConnection(host, port=port or 80, timeout=self.timeout_s)
        else:
            conn = _FastHTTPSConnection(
                host,
                port=port or 443,
                timeout=self.timeout_s,
                context=_build_ssl_context(),
            )
        self._tls_local.conn = conn
        return conn

    def _close_connection(self) -> None:
        conn: http.client.HTTPConnection | None = getattr(self._tls_local, "conn", None)
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
            self._tls_local.conn = None

    def _headers(self, extra_headers: dict[str, str] | None = None) -> dict[str, str]:
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "slashml-python-sdk/1.0.13",
            "X-SlashML-Model": self.model,
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            headers["X-API-Key"] = self.api_key
        if self.org_id:
            headers["X-SlashML-Org-Id"] = self.org_id
        if self.project_id:
            headers["X-SlashML-Project-Id"] = self.project_id
        if self.agent_id:
            headers["X-SlashML-Agent-Id"] = self.agent_id
        if extra_headers:
            for key, val in extra_headers.items():
                if val is not None and str(val).strip():
                    headers[key] = str(val).strip()
        return headers

    def _apply_lifecycle_defaults(
        self,
        payload: dict[str, Any] | None = None,
        *,
        redact_policy: str | list[str] | None = None,
        redact_scope: str | None = None,
        caller_agent_id: str | None = None,
    ) -> dict[str, str] | None:
        eff_policy = (
            _normalize_redact_policy(redact_policy)
            if redact_policy is not None
            else self.redact_policy
        )
        eff_scope = redact_scope if redact_scope is not None else self.redact_scope
        eff_caller = caller_agent_id if caller_agent_id is not None else self.agent_id
        if payload is not None:
            if eff_policy is not None and "redact_policy" not in payload:
                payload["redact_policy"] = eff_policy
            if eff_scope and "redact_scope" not in payload:
                payload["redact_scope"] = eff_scope
            if eff_caller and "caller_agent_id" not in payload:
                payload["caller_agent_id"] = eff_caller
        if eff_caller:
            return {"X-SlashML-Agent-Id": str(eff_caller)}
        return None

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        query_params: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> Any:
        clean_path = path if path.startswith("/") else f"/{path}"
        if query_params:
            filtered = {
                k: json.dumps(v) if isinstance(v, (list, dict)) else str(v)
                for k, v in query_params.items()
                if v is not None and v != ""
            }
            if filtered:
                qs = urllib.parse.urlencode(filtered)
                sep = "&" if "?" in clean_path else "?"
                clean_path = f"{clean_path}{sep}{qs}"

        headers = self._headers(extra_headers=extra_headers)
        if self._transport is not None:
            return self._transport(method.upper(), clean_path, payload, headers)

        if not self.api_key:
            raise SlashMLAPIError(
                "Missing API key. Pass `api_key='sml_...'` or set the `SLASHML_API_KEY` "
                "environment variable."
            )

        url = f"{self.base_url}{clean_path}"
        base_path = self._parsed_base.path.rstrip("/")
        request_target = f"{base_path}{clean_path}" if base_path else clean_path
        body_bytes = (
            json.dumps(payload).encode("utf-8") if payload is not None else None
        )
        req_headers = dict(headers)
        req_headers["Connection"] = "keep-alive"
        if body_bytes is not None:
            req_headers["Content-Length"] = str(len(body_bytes))

        for attempt in range(2):
            conn = self._get_connection()
            try:
                conn.request(
                    method.upper(),
                    request_target,
                    body=body_bytes,
                    headers=req_headers,
                )
                resp = conn.getresponse()
                raw = resp.read().decode("utf-8", errors="replace")
                if 200 <= resp.status < 300:
                    return json.loads(raw) if raw.strip() else {}
                try:
                    err_json = json.loads(raw) if raw.strip() else {"error": resp.reason}
                except Exception:
                    err_json = {"error": raw or resp.reason}
                raise SlashMLAPIError(
                    f"HTTP {resp.status} from {method.upper()} {url}: {raw or resp.reason}",
                    status_code=resp.status,
                    response_body=err_json,
                )
            except SlashMLAPIError:
                raise
            except (
                http.client.HTTPException,
                ConnectionError,
                TimeoutError,
                OSError,
            ) as exc:
                self._close_connection()
                if attempt == 0:
                    continue
                raise SlashMLAPIError(
                    f"Network error contacting {url}: {exc}"
                ) from exc
        raise SlashMLAPIError(f"Network error contacting {url}")

    # ------------------------------------------------------------------
    # 1. Native `/ ml` Engine Routes (`/v1/memory/{ingest,query,forget,redact,purge,undo}`)
    # ------------------------------------------------------------------
    def ingest(
        self,
        documents: list[Any] | str | None = None,
        *,
        text: str | None = None,
        doc_id: str | None = None,
        user_id: str | None = None,
        namespace: str | None = None,
        model: str | None = None,
        metadata: dict[str, Any] | None = None,
        redact_policy: str | list[str] | None = None,
        redact_scope: str | None = None,
        caller_agent_id: str | None = None,
    ) -> dict[str, Any]:
        """Ingest one or more documents into `/v1/memory/ingest`."""
        payload: dict[str, Any] = {"model": model or self.model}
        if namespace is not None:
            payload["namespace"] = namespace
        if documents is not None:
            payload["documents"] = [documents] if isinstance(documents, str) else list(documents)
            if user_id:
                payload["user_id"] = user_id
            if metadata:
                payload["metadata"] = metadata
        elif text is not None:
            doc: dict[str, Any] = {"text": text}
            if doc_id:
                doc["id"] = doc_id
            if user_id:
                doc["user_id"] = user_id
            if metadata:
                doc["metadata"] = metadata
            payload["documents"] = [doc]
            payload["text"] = text
            if user_id:
                payload["user_id"] = user_id
            if metadata:
                payload["metadata"] = metadata
        else:
            raise ValueError("Either `documents` or `text` must be provided to ingest().")
        extra_hdrs = self._apply_lifecycle_defaults(
            payload,
            redact_policy=redact_policy,
            redact_scope=redact_scope,
            caller_agent_id=caller_agent_id,
        )
        res = self._request("POST", "/v1/memory/ingest", payload, extra_headers=extra_hdrs)
        return res if isinstance(res, dict) else {"results": res}

    def query(
        self,
        query: str,
        *,
        top_k: int = 5,
        user_id: str | None = None,
        namespace: str | None = None,
        model: str | None = None,
        metadata_filter: dict[str, Any] | None = None,
        redact_policy: str | list[str] | None = None,
        redact_scope: str | None = None,
        caller_agent_id: str | None = None,
    ) -> dict[str, Any]:
        """Query the `/v1/memory/query` endpoint."""
        payload: dict[str, Any] = {
            "query": query,
            "prompt": query,
            "top_k": int(top_k),
            "model": model or self.model,
        }
        if namespace is not None:
            payload["namespace"] = namespace
        if user_id is not None:
            payload["user_id"] = user_id
        if metadata_filter is not None:
            payload["metadata_filter"] = metadata_filter
        extra_hdrs = self._apply_lifecycle_defaults(
            payload,
            redact_policy=redact_policy,
            redact_scope=redact_scope,
            caller_agent_id=caller_agent_id,
        )
        res = self._request("POST", "/v1/memory/query", payload, extra_headers=extra_hdrs)
        return res if isinstance(res, dict) else {"results": res}

    def forget(
        self,
        document_ids: list[str] | str | None = None,
        *,
        memory_id: str | None = None,
        memory_ids: list[str] | None = None,
        user_id: str | None = None,
        namespace: str | None = None,
        purge: bool = False,
        reason: str | None = None,
        caller_agent_id: str | None = None,
    ) -> dict[str, Any]:
        """Delete documents from memory via `DELETE /v1/memory/forget` (or `POST /v1/memory/purge` when `purge=True`)."""
        ids: list[str] = []
        if isinstance(document_ids, str):
            ids.append(document_ids)
        elif isinstance(document_ids, list):
            ids.extend(str(x) for x in document_ids if x)
        if memory_ids:
            ids.extend(str(x) for x in memory_ids if x)
        if memory_id:
            ids.append(str(memory_id))
        if purge:
            return self.purge(ids, reason=reason, caller_agent_id=caller_agent_id)
        payload: dict[str, Any] = {"document_ids": ids}
        if isinstance(document_ids, str):
            payload["target"] = document_ids
        if namespace is not None:
            payload["namespace"] = namespace
        if memory_id:
            payload["memory_id"] = memory_id
        if user_id:
            payload["user_id"] = user_id
        if reason:
            payload["reason"] = reason
        extra_hdrs = self._apply_lifecycle_defaults(
            payload,
            caller_agent_id=caller_agent_id,
        )
        res = self._request(
            "DELETE",
            "/v1/memory/forget",
            payload,
            query_params={"memory_id": memory_id, "user_id": user_id},
            extra_headers=extra_hdrs,
        )
        return res if isinstance(res, dict) else {"deleted": True}

    def redact(
        self,
        text: str | None = None,
        *,
        memory_id: str | None = None,
        redact_policy: str | list[str] | None = None,
        explicit_spans: list[dict[str, Any]] | None = None,
        dry_run: bool = False,
        caller_agent_id: str | None = None,
    ) -> dict[str, Any]:
        """Redact sensitive spans from `text` (stateless) or `memory_id` in-place via `POST /v1/memory/redact`."""
        if text is None and not memory_id:
            raise ValueError("redact() requires `text` (stateless) or `memory_id` (in-place).")
        payload: dict[str, Any] = {}
        if text is not None:
            payload["text"] = text
        if memory_id:
            payload["memory_id"] = str(memory_id)
        if explicit_spans is not None:
            payload["explicit_spans"] = list(explicit_spans)
        if dry_run:
            payload["dry_run"] = True
        extra_hdrs = self._apply_lifecycle_defaults(
            payload,
            redact_policy=redact_policy,
            caller_agent_id=caller_agent_id,
        )
        res = self._request("POST", "/v1/memory/redact", payload, extra_headers=extra_hdrs)
        return res if isinstance(res, dict) else {"raw": res}

    def purge(
        self,
        memory_ids: list[str] | str,
        *,
        dry_run: bool = False,
        reason: str | None = None,
        caller_agent_id: str | None = None,
    ) -> dict[str, Any]:
        """Permanently purge one or more memories via `POST /v1/memory/purge`."""
        ids = [memory_ids] if isinstance(memory_ids, str) else [str(x) for x in memory_ids if x]
        payload: dict[str, Any] = {"memory_ids": ids, "dry_run": bool(dry_run)}
        if len(ids) == 1:
            payload["memory_id"] = ids[0]
        if reason is not None:
            payload["reason"] = reason
        extra_hdrs = self._apply_lifecycle_defaults(
            payload,
            caller_agent_id=caller_agent_id,
        )
        res = self._request("POST", "/v1/memory/purge", payload, extra_headers=extra_hdrs)
        return res if isinstance(res, dict) else {"purged_count": len(ids)}

    def undo(
        self,
        undo_token: str,
        *,
        caller_agent_id: str | None = None,
    ) -> dict[str, Any]:
        """Restore a recently purged, deleted, or redacted memory within the undo window via `POST /v1/memory/undo`."""
        payload: dict[str, Any] = {"undo_token": str(undo_token)}
        extra_hdrs = self._apply_lifecycle_defaults(
            payload,
            caller_agent_id=caller_agent_id,
        )
        res = self._request("POST", "/v1/memory/undo", payload, extra_headers=extra_hdrs)
        return res if isinstance(res, dict) else {"restored": True}

    def get_redaction_policy(self) -> dict[str, Any]:
        """Fetch workspace default redaction & write-access policy plus per-agent policies via `GET /v1/memory/redact/policy`."""
        res = self._request("GET", "/v1/memory/redact/policy")
        return res if isinstance(res, dict) else {}

    def update_redaction_policy(
        self,
        *,
        redact_policy: str | list[str] | None = None,
        redact_scope: str | None = None,
        access_mode: str | None = None,
        allow_write: bool | None = None,
    ) -> dict[str, Any]:
        """Update workspace default redaction & write-access policy via `PUT /v1/memory/redact/policy`."""
        payload: dict[str, Any] = {}
        if redact_policy is not None:
            payload["redact_policy"] = _normalize_redact_policy(redact_policy)
        if redact_scope is not None:
            payload["redact_scope"] = redact_scope
        if access_mode is not None:
            payload["access_mode"] = access_mode
        if allow_write is not None:
            payload["allow_write"] = bool(allow_write)
        res = self._request("PUT", "/v1/memory/redact/policy", payload)
        return res if isinstance(res, dict) else payload

    def preview_redaction(
        self,
        text: str,
        *,
        agent_id: str | None = None,
        redact_policy: str | list[str] | None = None,
        redact_scope: str | None = None,
    ) -> dict[str, Any]:
        """Run a stateless redaction & write-permission dry-run via `POST /v1/memory/redact/preview`."""
        payload: dict[str, Any] = {"text": text}
        if agent_id is not None:
            payload["agent_id"] = agent_id
        if redact_policy is not None:
            payload["redact_policy"] = _normalize_redact_policy(redact_policy)
        if redact_scope is not None:
            payload["redact_scope"] = redact_scope
        res = self._request("POST", "/v1/memory/redact/preview", payload)
        return res if isinstance(res, dict) else {"raw": res}

    def intervene(
        self,
        text: str | dict[str, Any] = "",
        *,
        hook_event_name: str = "UserPromptSubmit",
        prompt: str | None = None,
        last_assistant_message: str | None = None,
        stop_hook_active: bool = False,
        turn_blocked_memory_ids: list[str] | None = None,
        stop_retry_count: int = 0,
        whispered_memory_ids: list[str] | None = None,
        overridden_memory_ids: list[str] | None = None,
        dismiss_memory_ids: list[str] | None = None,
        tool_name: str | None = None,
        tool_input: dict[str, Any] | None = None,
        tool_response: dict[str, Any] | None = None,
        user_id: str | None = None,
        project_id: str | None = None,
        session_id: str | None = None,
        model: str | None = None,
        commit_writes: bool = True,
        top_k: int = 5,
        redact_policy: str | list[str] | None = None,
        redact_scope: str | None = None,
        caller_agent_id: str | None = None,
        client_raw_tokens_delta: int = 0,
        client_dropped_tokens_delta: int = 0,
        client_dropped_events_delta: int = 0,
    ) -> dict[str, Any]:
        """Evaluate an agent turn or tool action via `POST /v1/memory/intervene`."""
        if isinstance(text, dict):
            raw_dict = dict(text)
            resolved_text = str(raw_dict.get("text") or raw_dict.get("prompt") or "")
            resolved_prompt = str(raw_dict.get("prompt") or resolved_text)
            hook_event_name = str(raw_dict.get("hook_event_name") or hook_event_name)
            last_assistant_message = raw_dict.get("last_assistant_message", last_assistant_message)
            stop_hook_active = bool(raw_dict.get("stop_hook_active", stop_hook_active))
            whispered_memory_ids = raw_dict.get("whispered_memory_ids", whispered_memory_ids)
            overridden_memory_ids = raw_dict.get("overridden_memory_ids", overridden_memory_ids)
            dismiss_memory_ids = raw_dict.get("dismiss_memory_ids", dismiss_memory_ids)
            tool_name = raw_dict.get("tool_name", tool_name)
            tool_input = raw_dict.get("tool_input", tool_input)
            tool_response = raw_dict.get("tool_response", tool_response)
            user_id = raw_dict.get("user_id", user_id)
            project_id = (
                raw_dict.get("project_id")
                or raw_dict.get("projectId")
                or project_id
            )
            session_id = (
                raw_dict.get("session_id")
                or raw_dict.get("sessionId")
                or raw_dict.get("conversationId")
                or session_id
            )
            model = raw_dict.get("model", model)
            commit_writes = bool(raw_dict.get("commit_writes", commit_writes))
            top_k = int(raw_dict.get("top_k", top_k))
            redact_policy = raw_dict.get("redact_policy", redact_policy)
            redact_scope = raw_dict.get("redact_scope", redact_scope)
            caller_agent_id = raw_dict.get("caller_agent_id", caller_agent_id)
            client_raw_tokens_delta = int(
                raw_dict.get("client_raw_tokens_delta", client_raw_tokens_delta)
            )
            client_dropped_tokens_delta = int(
                raw_dict.get("client_dropped_tokens_delta", client_dropped_tokens_delta)
            )
            client_dropped_events_delta = int(
                raw_dict.get("client_dropped_events_delta", client_dropped_events_delta)
            )
        else:
            resolved_text = str(text or prompt or "")
            resolved_prompt = str(prompt if prompt is not None else resolved_text)

        resolved_model = model or self.model
        resolved_project_id = project_id or self.project_id
        payload: dict[str, Any] = {
            "hook_event_name": hook_event_name,
            "prompt": resolved_prompt,
            "text": resolved_text,
            "tool_name": tool_name,
            "tool_input": tool_input,
            "tool_response": tool_response,
            "user_id": user_id or "default",
            "model": resolved_model,
            "commit_writes": commit_writes,
            "top_k": top_k,
            "client_raw_tokens_delta": max(0, int(client_raw_tokens_delta)),
            "client_dropped_tokens_delta": max(0, int(client_dropped_tokens_delta)),
            "client_dropped_events_delta": max(0, int(client_dropped_events_delta)),
        }
        if last_assistant_message is not None:
            payload["last_assistant_message"] = str(last_assistant_message)
        if stop_hook_active:
            payload["stop_hook_active"] = True
        if turn_blocked_memory_ids:
            payload["turn_blocked_memory_ids"] = [str(x) for x in turn_blocked_memory_ids if x]
        if stop_retry_count > 0:
            payload["stop_retry_count"] = int(stop_retry_count)
        if whispered_memory_ids:
            payload["whispered_memory_ids"] = [str(x) for x in whispered_memory_ids if x]
        if overridden_memory_ids:
            payload["overridden_memory_ids"] = [str(x) for x in overridden_memory_ids if x]
        if dismiss_memory_ids:
            payload["dismiss_memory_ids"] = [str(x) for x in dismiss_memory_ids if x]
        if resolved_project_id:
            payload["project_id"] = str(resolved_project_id)
        if session_id:
            payload["session_id"] = str(session_id)
        extra_hdrs = self._apply_lifecycle_defaults(
            payload,
            redact_policy=redact_policy,
            redact_scope=redact_scope,
            caller_agent_id=caller_agent_id,
        )
        res = self._request("POST", "/v1/memory/intervene", payload, extra_headers=extra_hdrs)
        return res if isinstance(res, dict) else {"raw": res}

    def status(
        self,
        *,
        user_id: str | None = None,
        client_raw_tokens_delta: int = 0,
        client_dropped_tokens_delta: int = 0,
        client_dropped_events_delta: int = 0,
    ) -> dict[str, Any]:
        """Retrieve ambient stream ROI & telemetry via `GET/POST /v1/memory/status`."""
        uid = user_id or "default"
        if (
            client_raw_tokens_delta > 0
            or client_dropped_tokens_delta > 0
            or client_dropped_events_delta > 0
        ):
            res = self._request(
                "POST",
                "/v1/memory/status",
                {
                    "user_id": uid,
                    "client_raw_tokens_delta": max(0, int(client_raw_tokens_delta)),
                    "client_dropped_tokens_delta": max(0, int(client_dropped_tokens_delta)),
                    "client_dropped_events_delta": max(0, int(client_dropped_events_delta)),
                },
            )
        else:
            res = self._request("GET", "/v1/memory/status", query_params={"user_id": uid})
        return res if isinstance(res, dict) else {"raw": res}

    # ------------------------------------------------------------------
    # 2. Mem0-Compatible Routes (`/v1/memories/*`, `/v2/memories/search/`)
    # ------------------------------------------------------------------
    def add(
        self,
        messages: str | list[dict[str, str]] | dict[str, Any],
        *,
        user_id: str | None = None,
        agent_id: str | None = None,
        app_id: str | None = None,
        run_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        filters: dict[str, Any] | None = None,
        infer: bool = True,
        memory_id: str | None = None,
        doc_id: str | None = None,
        redact_policy: str | list[str] | None = None,
        redact_scope: str | None = None,
        caller_agent_id: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Add memory via `POST /v1/memories/` (100% Mem0 `MemoryClient.add` compatible)."""
        payload: dict[str, Any] = {"infer": infer}
        if isinstance(messages, str):
            payload["text"] = messages
            payload["messages"] = [{"role": "user", "content": messages}]
        elif isinstance(messages, list):
            payload["messages"] = messages
        elif isinstance(messages, dict):
            if "role" in messages and "content" in messages:
                payload["messages"] = [messages]
            else:
                payload.update(messages)
        else:
            payload["text"] = str(messages)

        if user_id is not None:
            payload["user_id"] = user_id
        if agent_id is not None:
            payload["agent_id"] = agent_id
        if app_id is not None:
            payload["app_id"] = app_id
        if run_id is not None:
            payload["run_id"] = run_id
        if self.org_id:
            payload.setdefault("org_id", self.org_id)
        if self.project_id:
            payload.setdefault("project_id", self.project_id)
        if metadata is not None:
            payload["metadata"] = metadata
        if filters is not None:
            payload["filters"] = filters
        target_id = memory_id or doc_id
        if target_id is not None:
            payload["memory_id"] = str(target_id)
            payload["id"] = str(target_id)
        if kwargs:
            payload.update(kwargs)
        extra_hdrs = self._apply_lifecycle_defaults(
            payload,
            redact_policy=redact_policy,
            redact_scope=redact_scope,
            caller_agent_id=caller_agent_id,
        )

        res = self._request("POST", "/v1/memories/", payload, extra_headers=extra_hdrs)
        return res if isinstance(res, dict) else {"results": res}

    def add_batch(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        """Batch-ingest multiple documents via `POST /v1/memory/ingest`."""
        return self.ingest(documents=items)

    def search(
        self,
        query: str,
        *,
        user_id: str | None = None,
        agent_id: str | None = None,
        app_id: str | None = None,
        run_id: str | None = None,
        limit: int = 5,
        top_k: int | None = None,
        filters: dict[str, Any] | None = None,
        threshold: float | None = None,
        version: str = "v1",
        redact_policy: str | list[str] | None = None,
        redact_scope: str | None = None,
        caller_agent_id: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Search memories via `POST /v1/memories/search/` or `POST /v2/memories/search/`."""
        k = int(top_k if top_k is not None else limit)
        payload: dict[str, Any] = {
            "query": query,
            "limit": k,
            "top_k": k,
        }
        if user_id is not None:
            payload["user_id"] = user_id
        if agent_id is not None:
            payload["agent_id"] = agent_id
        if app_id is not None:
            payload["app_id"] = app_id
        if run_id is not None:
            payload["run_id"] = run_id
        if self.org_id:
            payload.setdefault("org_id", self.org_id)
        if self.project_id:
            payload.setdefault("project_id", self.project_id)
        if filters is not None:
            payload["filters"] = filters
        if threshold is not None:
            payload["threshold"] = threshold
        if kwargs:
            payload.update(kwargs)
        extra_hdrs = self._apply_lifecycle_defaults(
            payload,
            redact_policy=redact_policy,
            redact_scope=redact_scope,
            caller_agent_id=caller_agent_id,
        )

        endpoint = "/v2/memories/search/" if str(version).lower() == "v2" else "/v1/memories/search/"
        res = self._request("POST", endpoint, payload, extra_headers=extra_hdrs)
        if isinstance(res, list):
            return {"results": res}
        return res if isinstance(res, dict) else {"results": []}

    def recall(
        self,
        query: str,
        *,
        user_id: str | None = None,
        agent_id: str | None = None,
        app_id: str | None = None,
        run_id: str | None = None,
        limit: int = 5,
        top_k: int | None = None,
        filters: dict[str, Any] | None = None,
        threshold: float | None = None,
        version: str = "v1",
        redact_policy: str | list[str] | None = None,
        redact_scope: str | None = None,
        caller_agent_id: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Recall memories (alias for `search()`)."""
        return self.search(
            query,
            user_id=user_id,
            agent_id=agent_id,
            app_id=app_id,
            run_id=run_id,
            limit=limit,
            top_k=top_k,
            filters=filters,
            threshold=threshold,
            version=version,
            redact_policy=redact_policy,
            redact_scope=redact_scope,
            caller_agent_id=caller_agent_id,
            **kwargs,
        )

    def get_all(
        self,
        *,
        user_id: str | None = None,
        agent_id: str | None = None,
        app_id: str | None = None,
        run_id: str | None = None,
        limit: int = 100,
        page: int | None = None,
        page_size: int | None = None,
        filters: dict[str, Any] | None = None,
        redact_policy: str | list[str] | None = None,
        caller_agent_id: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """List memories via `GET /v1/memories/`."""
        eff_policy = (
            _normalize_redact_policy(redact_policy)
            if redact_policy is not None
            else self.redact_policy
        )
        params: dict[str, Any] = {
            "user_id": user_id,
            "agent_id": agent_id,
            "app_id": app_id,
            "run_id": run_id,
            "org_id": self.org_id,
            "project_id": self.project_id,
            "limit": limit,
            "page": page,
            "page_size": page_size,
        }
        if eff_policy is not None:
            params["redact_policy"] = (
                ",".join(eff_policy) if isinstance(eff_policy, list) else eff_policy
            )
        if filters:
            params["filters"] = json.dumps(filters)
        params.update(kwargs)
        extra_hdrs = self._apply_lifecycle_defaults(caller_agent_id=caller_agent_id)
        res = self._request("GET", "/v1/memories/", query_params=params, extra_headers=extra_hdrs)
        if isinstance(res, list):
            return {"results": res}
        return res if isinstance(res, dict) else {"results": []}

    def get(
        self,
        memory_id: str,
        *,
        redact_policy: str | list[str] | None = None,
        caller_agent_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Fetch a single memory by ID via `GET /v1/memories/{memory_id}/`."""
        eff_policy = (
            _normalize_redact_policy(redact_policy)
            if redact_policy is not None
            else self.redact_policy
        )
        params: dict[str, Any] | None = None
        if eff_policy is not None:
            params = {
                "redact_policy": (
                    ",".join(eff_policy) if isinstance(eff_policy, list) else eff_policy
                )
            }
        extra_hdrs = self._apply_lifecycle_defaults(caller_agent_id=caller_agent_id)
        try:
            res = self._request(
                "GET",
                f"/v1/memories/{urllib.parse.quote(str(memory_id))}/",
                query_params=params,
                extra_headers=extra_hdrs,
            )
            return res if isinstance(res, dict) else None
        except SlashMLAPIError as exc:
            if exc.status_code == 404:
                return None
            raise

    def update(
        self,
        memory_id: str,
        data: str | dict[str, Any] | None = None,
        *,
        text: str | None = None,
        metadata: dict[str, Any] | None = None,
        redact_policy: str | list[str] | None = None,
        redact_scope: str | None = None,
        caller_agent_id: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Update a memory via `PUT /v1/memories/{memory_id}/`."""
        payload: dict[str, Any] = {}
        if isinstance(data, dict):
            payload.update(data)
        elif isinstance(data, str):
            payload["text"] = data
            payload["data"] = data
        if text is not None:
            payload["text"] = text
            payload.setdefault("data", text)
        if metadata is not None:
            payload["metadata"] = metadata
        if kwargs:
            payload.update(kwargs)
        extra_hdrs = self._apply_lifecycle_defaults(
            payload,
            redact_policy=redact_policy,
            redact_scope=redact_scope,
            caller_agent_id=caller_agent_id,
        )
        res = self._request(
            "PUT",
            f"/v1/memories/{urllib.parse.quote(str(memory_id))}/",
            payload,
            extra_headers=extra_hdrs,
        )
        return res if isinstance(res, dict) else {"id": memory_id}

    def delete(
        self,
        memory_id: str,
        *,
        caller_agent_id: str | None = None,
    ) -> dict[str, Any]:
        """Delete a single memory via `DELETE /v1/memories/{memory_id}/`."""
        extra_hdrs = self._apply_lifecycle_defaults(caller_agent_id=caller_agent_id)
        res = self._request(
            "DELETE",
            f"/v1/memories/{urllib.parse.quote(str(memory_id))}/",
            extra_headers=extra_hdrs,
        )
        return res if isinstance(res, dict) else {"id": memory_id, "deleted": True}

    def delete_all(
        self,
        *,
        user_id: str | None = None,
        agent_id: str | None = None,
        app_id: str | None = None,
        run_id: str | None = None,
        caller_agent_id: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Delete all memories matching a scope via `DELETE /v1/memories/`."""
        params: dict[str, Any] = {
            "user_id": user_id,
            "agent_id": agent_id,
            "app_id": app_id,
            "run_id": run_id,
            "org_id": self.org_id,
            "project_id": self.project_id,
        }
        params.update(kwargs)
        extra_hdrs = self._apply_lifecycle_defaults(caller_agent_id=caller_agent_id)
        res = self._request(
            "DELETE",
            "/v1/memories/",
            query_params=params,
            extra_headers=extra_hdrs,
        )
        return res if isinstance(res, dict) else {"deleted": True}

    def reset(self) -> dict[str, Any]:
        """Reset all memories in the current workspace scope."""
        return self.delete_all()

    def history(self, memory_id: str) -> list[dict[str, Any]]:
        """Retrieve revision history for `memory_id` via `GET /v1/memories/{memory_id}/history/`."""
        res = self._request(
            "GET",
            f"/v1/memories/{urllib.parse.quote(str(memory_id))}/history/",
        )
        if isinstance(res, list):
            return res
        if isinstance(res, dict):
            return list(res.get("history") or res.get("results") or [])
        return []

    def batch_update(
        self,
        memories: list[dict[str, Any]],
        *,
        redact_policy: str | list[str] | None = None,
        redact_scope: str | None = None,
        caller_agent_id: str | None = None,
    ) -> dict[str, Any]:
        """Batch update multiple memories via `PUT /v1/batch/`."""
        payload: dict[str, Any] = {"memories": memories}
        extra_hdrs = self._apply_lifecycle_defaults(
            payload,
            redact_policy=redact_policy,
            redact_scope=redact_scope,
            caller_agent_id=caller_agent_id,
        )
        res = self._request("PUT", "/v1/batch/", payload, extra_headers=extra_hdrs)
        return res if isinstance(res, dict) else {"results": res}

    def batch_delete(
        self,
        memories: list[str | dict[str, Any]],
        *,
        caller_agent_id: str | None = None,
    ) -> dict[str, Any]:
        """Batch delete multiple memories via `DELETE /v1/batch/`."""
        normalized = [
            m if isinstance(m, dict) else {"memory_id": str(m), "id": str(m)}
            for m in memories
        ]
        payload: dict[str, Any] = {"memories": normalized}
        extra_hdrs = self._apply_lifecycle_defaults(
            payload,
            caller_agent_id=caller_agent_id,
        )
        res = self._request("DELETE", "/v1/batch/", payload, extra_headers=extra_hdrs)
        return res if isinstance(res, dict) else {"results": res}

    def users(self, **kwargs: Any) -> dict[str, Any]:
        """Retrieve all tracked users, agents, apps, and sessions via `GET /v1/entities/`."""
        params: dict[str, Any] = {
            "org_id": self.org_id,
            "project_id": self.project_id,
        }
        params.update(kwargs)
        res = self._request("GET", "/v1/entities/", query_params=params)
        if isinstance(res, list):
            return {"results": res}
        return res if isinstance(res, dict) else {"results": []}

    def delete_users(
        self,
        *,
        user_id: str | None = None,
        agent_id: str | None = None,
        app_id: str | None = None,
        run_id: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Delete user/agent/app/run entity profiles via `DELETE /v1/entities/`."""
        params: dict[str, Any] = {
            "user_id": user_id,
            "agent_id": agent_id,
            "app_id": app_id,
            "run_id": run_id,
            "org_id": self.org_id,
            "project_id": self.project_id,
        }
        params.update(kwargs)
        res = self._request("DELETE", "/v1/entities/", query_params=params)
        return res if isinstance(res, dict) else {"deleted": True}

    def feedback(
        self,
        memory_id: str,
        feedback: str | None = None,
        feedback_reason: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Record relevance feedback (`POSITIVE`, `NEGATIVE`, `VERY_NEGATIVE`) on a memory via `POST /v1/feedback/`."""
        payload: dict[str, Any] = {
            "memory_id": memory_id,
            "feedback": feedback,
            "feedback_reason": feedback_reason,
        }
        if kwargs:
            payload.update(kwargs)
        res = self._request("POST", "/v1/feedback/", payload)
        return res if isinstance(res, dict) else {"id": memory_id, "feedback": feedback}

    def get_project(self, fields: list[str] | None = None) -> dict[str, Any]:
        """Get project details (delegates to `self.project.get()`)."""
        return self.project.get(fields=fields)

    def update_project(
        self,
        *,
        custom_instructions: str | None = None,
        custom_categories: list[Any] | None = None,
        retrieval_criteria: list[dict[str, Any]] | None = None,
        enable_graph: bool | None = None,
        version: str | None = None,
        decay: bool | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Update project settings (delegates to `self.project.update()`)."""
        return self.project.update(
            custom_instructions=custom_instructions,
            custom_categories=custom_categories,
            retrieval_criteria=retrieval_criteria,
            enable_graph=enable_graph,
            version=version,
            decay=decay,
            **kwargs,
        )

    def get_webhooks(self, project_id: str | None = None) -> dict[str, Any]:
        """List registered webhooks via `GET /v1/webhooks/`."""
        pid = project_id or self.project_id
        res = self._request("GET", "/v1/webhooks/", query_params={"project_id": pid})
        if isinstance(res, list):
            return {"results": res}
        return res if isinstance(res, dict) else {"results": []}

    def create_webhook(
        self,
        url: str,
        name: str,
        event_types: list[str] | None = None,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a webhook via `POST /v1/webhooks/`."""
        payload: dict[str, Any] = {
            "url": url,
            "name": name,
            "event_types": list(event_types or []),
            "project_id": project_id or self.project_id,
        }
        res = self._request("POST", "/v1/webhooks/", payload)
        return res if isinstance(res, dict) else {"name": name, "url": url}

    def update_webhook(
        self,
        webhook_id: int | str,
        name: str | None = None,
        url: str | None = None,
        event_types: list[str] | None = None,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """Update a webhook via `PUT /v1/webhooks/{webhook_id}/`."""
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if url is not None:
            payload["url"] = url
        if event_types is not None:
            payload["event_types"] = list(event_types)
        if project_id or self.project_id:
            payload["project_id"] = project_id or self.project_id
        res = self._request(
            "PUT",
            f"/v1/webhooks/{urllib.parse.quote(str(webhook_id))}/",
            payload,
        )
        return res if isinstance(res, dict) else {"id": webhook_id}

    def delete_webhook(self, webhook_id: int | str) -> dict[str, Any]:
        """Delete a webhook via `DELETE /v1/webhooks/{webhook_id}/`."""
        res = self._request(
            "DELETE",
            f"/v1/webhooks/{urllib.parse.quote(str(webhook_id))}/",
        )
        return res if isinstance(res, dict) else {"id": webhook_id, "deleted": True}

    # Top-level agent policy convenience delegates (`self.agents.*`)
    def list_agents(self) -> dict[str, Any]:
        """List all configured agent redaction & write-access policies (`GET /v1/agents/`)."""
        return self.agents.list()

    list_agent_policies = list_agents

    def configure_agent(self, agent_id: str, **kwargs: Any) -> dict[str, Any]:
        """Create or update an agent redaction & write-permission policy (`POST /v1/agents/`)."""
        return self.agents.configure(agent_id, **kwargs)

    upsert_agent_policy = configure_agent

    def delete_agent(self, agent_id: str) -> dict[str, Any]:
        """Remove an agent policy override (`DELETE /v1/agents/{agent_id}/`)."""
        return self.agents.delete(agent_id)

    delete_agent_policy = delete_agent

    # CamelCase aliases for JS/TS cross-compatibility
    getAll = get_all
    deleteAll = delete_all
    batchUpdate = batch_update
    batchDelete = batch_delete
    deleteUsers = delete_users
    getRedactionPolicy = get_redaction_policy
    updateRedactionPolicy = update_redaction_policy
    previewRedaction = preview_redaction
    listAgents = list_agents
    listAgentPolicies = list_agent_policies
    configureAgent = configure_agent
    upsertAgentPolicy = upsert_agent_policy
    deleteAgent = delete_agent
    deleteAgentPolicy = delete_agent_policy


class _AgentsManager:
    """Sub-client (`client.agents`) for managing per-agent redaction & write-permission policies."""

    def __init__(self, client: MemoryClient) -> None:
        self._client = client

    def list(self) -> dict[str, Any]:
        """List all configured agent redaction & write-access policies via `GET /v1/agents/`."""
        res = self._client._request("GET", "/v1/agents/")
        if isinstance(res, list):
            return {"agents": res}
        return res if isinstance(res, dict) else {"agents": []}

    def configure(
        self,
        agent_id: str,
        *,
        name: str | None = None,
        access_mode: str | None = None,
        allow_write: bool | None = None,
        redact_policy: str | list[str] | None = None,
        redact_scope: str | None = None,
        inherit_policy: bool = False,
        inherit_access: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create or update an agent redaction & write-permission policy via `POST /v1/agents/`."""
        payload: dict[str, Any] = {"agent_id": str(agent_id).strip()}
        if name is not None:
            payload["name"] = name
        if access_mode is not None:
            payload["access_mode"] = access_mode
        if allow_write is not None:
            payload["allow_write"] = bool(allow_write)
        if redact_policy is not None:
            payload["redact_policy"] = _normalize_redact_policy(redact_policy)
        if redact_scope is not None:
            payload["redact_scope"] = redact_scope
        if inherit_policy:
            payload["inherit_policy"] = True
        if inherit_access:
            payload["inherit_access"] = True
        if metadata is not None:
            payload["metadata"] = dict(metadata)
        res = self._client._request("POST", "/v1/agents/", payload)
        return res if isinstance(res, dict) else {"agent_id": agent_id}

    upsert = configure

    def delete(self, agent_id: str) -> dict[str, Any]:
        """Remove an agent policy override (reverting to workspace defaults) via `DELETE /v1/agents/{agent_id}/`."""
        res = self._client._request(
            "DELETE",
            f"/v1/agents/{urllib.parse.quote(str(agent_id).strip())}/",
        )
        return res if isinstance(res, dict) else {"agent_id": agent_id, "deleted": True}


class _AsyncAgentsManager:
    """Async counterpart to `_AgentsManager` for `AsyncMemoryClient.agents`."""

    def __init__(self, sync_agents: _AgentsManager) -> None:
        self._sync_agents = sync_agents

    async def list(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync_agents.list)

    async def configure(self, agent_id: str, **kwargs: Any) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync_agents.configure, agent_id, **kwargs)

    upsert = configure

    async def delete(self, agent_id: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync_agents.delete, agent_id)


class _ProjectManager:
    """Mem0-compatible `client.project` sub-client (`get`, `create`, `update`, `delete`, `get_members`, `add_member`, `remove_member`)."""

    def __init__(self, client: MemoryClient) -> None:
        self._client = client

    def get(self, fields: list[str] | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {
            "org_id": self._client.org_id,
            "project_id": self._client.project_id,
        }
        if fields:
            params["fields"] = ",".join(fields)
        res = self._client._request("GET", "/v1/project/", query_params=params)
        return res if isinstance(res, dict) else {}

    def create(self, name: str, description: str | None = None, **kwargs: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": name,
            "description": description,
            "org_id": self._client.org_id,
        }
        payload.update(kwargs)
        res = self._client._request("POST", "/v1/project/", payload)
        return res if isinstance(res, dict) else {"name": name}

    def update(
        self,
        *,
        custom_instructions: str | None = None,
        custom_categories: list[Any] | None = None,
        retrieval_criteria: list[dict[str, Any]] | None = None,
        enable_graph: bool | None = None,
        version: str | None = None,
        decay: bool | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "org_id": self._client.org_id,
            "project_id": self._client.project_id,
        }
        if custom_instructions is not None:
            payload["custom_instructions"] = custom_instructions
        if custom_categories is not None:
            payload["custom_categories"] = custom_categories
        if retrieval_criteria is not None:
            payload["retrieval_criteria"] = retrieval_criteria
        if enable_graph is not None:
            payload["enable_graph"] = enable_graph
        if version is not None:
            payload["version"] = version
        if decay is not None:
            payload["decay"] = decay
        payload.update(kwargs)
        res = self._client._request("PATCH", "/v1/project/", payload)
        return res if isinstance(res, dict) else payload

    def delete(self) -> dict[str, Any]:
        params = {
            "org_id": self._client.org_id,
            "project_id": self._client.project_id,
        }
        res = self._client._request("DELETE", "/v1/project/", query_params=params)
        return res if isinstance(res, dict) else {"deleted": True}

    def get_members(self) -> dict[str, Any]:
        params = {
            "org_id": self._client.org_id,
            "project_id": self._client.project_id,
        }
        res = self._client._request("GET", "/v1/project/members/", query_params=params)
        if isinstance(res, list):
            return {"results": res}
        return res if isinstance(res, dict) else {"results": []}

    def add_member(self, email: str, role: str = "READER") -> dict[str, Any]:
        payload = {
            "email": email,
            "role": role,
            "org_id": self._client.org_id,
            "project_id": self._client.project_id,
        }
        res = self._client._request("POST", "/v1/project/members/", payload)
        return res if isinstance(res, dict) else {"email": email, "role": role}

    def remove_member(self, email: str) -> dict[str, Any]:
        params = {
            "email": email,
            "org_id": self._client.org_id,
            "project_id": self._client.project_id,
        }
        res = self._client._request("DELETE", "/v1/project/members/", query_params=params)
        return res if isinstance(res, dict) else {"email": email, "deleted": True}


class _AsyncProjectManager:
    """Async counterpart to `_ProjectManager` for `AsyncMemoryClient.project`."""

    def __init__(self, sync_project: _ProjectManager) -> None:
        self._sync_project = sync_project

    async def get(self, fields: list[str] | None = None) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync_project.get, fields=fields)

    async def create(self, name: str, description: str | None = None, **kwargs: Any) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync_project.create, name, description, **kwargs)

    async def update(self, **kwargs: Any) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync_project.update, **kwargs)

    async def delete(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync_project.delete)

    async def get_members(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync_project.get_members)

    async def add_member(self, email: str, role: str = "READER") -> dict[str, Any]:
        return await asyncio.to_thread(self._sync_project.add_member, email, role)

    async def remove_member(self, email: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync_project.remove_member, email)


class AsyncMemoryClient:
    """100% Mem0-compatible asynchronous (`asyncio`) HTTP client targeting `https://api.slashml.ai`.

    Drop-in replacement for `from mem0 import AsyncMemoryClient` (`from slashml import AsyncMemoryClient`).
    """

    def __init__(
        self,
        api_key: str | None = None,
        host: str | None = None,
        *,
        base_url: str | None = None,
        org_id: str | None = None,
        project_id: str | None = None,
        agent_id: str | None = None,
        caller_agent_id: str | None = None,
        redact_policy: str | list[str] | None = None,
        redact_scope: str | None = None,
        model: str = "slashml-nano",
        timeout_s: float = 30.0,
        transport: TransportCallable | None = None,
    ) -> None:
        self._sync = MemoryClient(
            api_key=api_key,
            host=host,
            base_url=base_url,
            org_id=org_id,
            project_id=project_id,
            agent_id=agent_id,
            caller_agent_id=caller_agent_id,
            redact_policy=redact_policy,
            redact_scope=redact_scope,
            model=model,
            timeout_s=timeout_s,
            transport=transport,
        )
        self.api_key = self._sync.api_key
        self.base_url = self._sync.base_url
        self.host = self._sync.host
        self.org_id = self._sync.org_id
        self.project_id = self._sync.project_id
        self.agent_id = self._sync.agent_id
        self.caller_agent_id = self._sync.caller_agent_id
        self.redact_policy = self._sync.redact_policy
        self.redact_scope = self._sync.redact_scope
        self.model = self._sync.model
        self.timeout_s = self._sync.timeout_s
        self.project = _AsyncProjectManager(self._sync.project)
        self.agents = _AsyncAgentsManager(self._sync.agents)

    async def close(self) -> None:
        await asyncio.to_thread(self._sync.close)

    async def __aenter__(self) -> "AsyncMemoryClient":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def ingest(self, documents: Any = None, **kwargs: Any) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.ingest, documents, **kwargs)

    async def query(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.query, prompt, **kwargs)

    async def forget(self, document_ids: Any = None, **kwargs: Any) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.forget, document_ids, **kwargs)

    async def redact(self, text: str | None = None, **kwargs: Any) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.redact, text, **kwargs)

    async def purge(self, memory_ids: list[str] | str, **kwargs: Any) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.purge, memory_ids, **kwargs)

    async def undo(self, undo_token: str, **kwargs: Any) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.undo, undo_token, **kwargs)

    async def get_redaction_policy(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.get_redaction_policy)

    async def update_redaction_policy(self, **kwargs: Any) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.update_redaction_policy, **kwargs)

    async def preview_redaction(self, text: str, **kwargs: Any) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.preview_redaction, text, **kwargs)

    async def intervene(self, text: Any = "", **kwargs: Any) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.intervene, text, **kwargs)

    async def status(self, **kwargs: Any) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.status, **kwargs)

    async def add(self, messages: Any, **kwargs: Any) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.add, messages, **kwargs)

    async def search(self, query: str, **kwargs: Any) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.search, query, **kwargs)

    async def recall(self, query: str, **kwargs: Any) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.recall, query, **kwargs)

    async def get_all(self, **kwargs: Any) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.get_all, **kwargs)

    async def get(self, memory_id: str, **kwargs: Any) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._sync.get, memory_id, **kwargs)

    async def update(
        self,
        memory_id: str,
        data: str | dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.update, memory_id, data, **kwargs)

    async def delete(self, memory_id: str, **kwargs: Any) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.delete, memory_id, **kwargs)

    async def delete_all(self, **kwargs: Any) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.delete_all, **kwargs)

    async def reset(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.reset)

    async def history(self, memory_id: str) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._sync.history, memory_id)

    async def batch_update(self, memories: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.batch_update, memories, **kwargs)

    async def batch_delete(self, memories: list[str | dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.batch_delete, memories, **kwargs)

    async def users(self, **kwargs: Any) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.users, **kwargs)

    async def delete_users(self, **kwargs: Any) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.delete_users, **kwargs)

    async def feedback(
        self,
        memory_id: str,
        feedback: str | None = None,
        feedback_reason: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._sync.feedback,
            memory_id,
            feedback=feedback,
            feedback_reason=feedback_reason,
            **kwargs,
        )

    async def get_project(self, fields: list[str] | None = None) -> dict[str, Any]:
        return await self.project.get(fields=fields)

    async def update_project(self, **kwargs: Any) -> dict[str, Any]:
        return await self.project.update(**kwargs)

    async def get_webhooks(self, project_id: str | None = None) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.get_webhooks, project_id=project_id)

    async def create_webhook(
        self,
        url: str,
        name: str,
        event_types: list[str] | None = None,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._sync.create_webhook,
            url,
            name,
            event_types,
            project_id=project_id,
        )

    async def update_webhook(
        self,
        webhook_id: int | str,
        name: str | None = None,
        url: str | None = None,
        event_types: list[str] | None = None,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._sync.update_webhook,
            webhook_id,
            name=name,
            url=url,
            event_types=event_types,
            project_id=project_id,
        )

    async def delete_webhook(self, webhook_id: int | str) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.delete_webhook, webhook_id)

    async def list_agents(self) -> dict[str, Any]:
        return await self.agents.list()

    list_agent_policies = list_agents

    async def configure_agent(self, agent_id: str, **kwargs: Any) -> dict[str, Any]:
        return await self.agents.configure(agent_id, **kwargs)

    upsert_agent_policy = configure_agent

    async def delete_agent(self, agent_id: str) -> dict[str, Any]:
        return await self.agents.delete(agent_id)

    delete_agent_policy = delete_agent

    getAll = get_all
    deleteAll = delete_all
    batchUpdate = batch_update
    batchDelete = batch_delete
    deleteUsers = delete_users
    getRedactionPolicy = get_redaction_policy
    updateRedactionPolicy = update_redaction_policy
    previewRedaction = preview_redaction
    listAgents = list_agents
    listAgentPolicies = list_agent_policies
    configureAgent = configure_agent
    upsertAgentPolicy = upsert_agent_policy
    deleteAgent = delete_agent
    deleteAgentPolicy = delete_agent_policy


SlashMLClient = MemoryClient
SlashMLMemory = MemoryClient
AsyncSlashMLClient = AsyncMemoryClient
AsyncSlashMLMemory = AsyncMemoryClient
