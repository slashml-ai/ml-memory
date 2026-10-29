"""Thin HTTP Cloud Client for / ml (`https://api.slashml.ai`).

Provides `MemoryClient` / `SlashMLMemory` (100% 1:1 Mem0 Cloud Client & `/ ml` Native API drop-in)
with zero native binary dependencies (`urllib.request` standard library only).
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
    """HTTP/1.1 keep-alive connection with TCP_NODELAY enabled to prevent 40ms Nagle/Delayed-ACK stalls."""

    def connect(self) -> None:
        super().connect()
        if self.sock is not None:
            try:
                self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except OSError:
                pass


class _FastHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS/1.1 keep-alive connection with TCP_NODELAY enabled to prevent 40ms Nagle/Delayed-ACK stalls."""

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
        self.api_key = str(resolved_key).strip()
        self.base_url = str(resolved_url).rstrip("/")
        self.host = self.base_url
        self.org_id = org_id or os.environ.get("SLASHML_ORG_ID")
        self.project_id = project_id or os.environ.get("SLASHML_PROJECT_ID")
        self.model = model
        self.timeout_s = float(timeout_s)
        self._transport = transport
        self._parsed_base = urllib.parse.urlparse(self.base_url)
        self._tls_local = threading.local()
        self.project = _ProjectManager(self)

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

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "slashml-python-sdk/1.0.0",
            "X-SlashML-Model": self.model,
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            headers["X-API-Key"] = self.api_key
        if self.org_id:
            headers["X-SlashML-Org-Id"] = self.org_id
        if self.project_id:
            headers["X-SlashML-Project-Id"] = self.project_id
        return headers

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        query_params: dict[str, Any] | None = None,
    ) -> Any:
        clean_path = path if path.startswith("/") else f"/{path}"
        if query_params:
            filtered = {
                k: str(v)
                for k, v in query_params.items()
                if v is not None and v != ""
            }
            if filtered:
                qs = urllib.parse.urlencode(filtered)
                sep = "&" if "?" in clean_path else "?"
                clean_path = f"{clean_path}{sep}{qs}"

        headers = self._headers()
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
    # 1. Native `/ ml` Engine Routes (`/v1/memory/{ingest,query,forget}`)
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
        res = self._request("POST", "/v1/memory/ingest", payload)
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
        res = self._request("POST", "/v1/memory/query", payload)
        return res if isinstance(res, dict) else {"results": res}

    def forget(
        self,
        document_ids: list[str] | str | None = None,
        *,
        memory_id: str | None = None,
        user_id: str | None = None,
        namespace: str | None = None,
    ) -> dict[str, Any]:
        """Physically unlearn documents in O(1) via `DELETE /v1/memory/forget`."""
        ids: list[str] = []
        if isinstance(document_ids, str):
            ids.append(document_ids)
        elif isinstance(document_ids, list):
            ids.extend(str(x) for x in document_ids if x)
        if memory_id:
            ids.append(str(memory_id))
        payload: dict[str, Any] = {"document_ids": ids}
        if isinstance(document_ids, str):
            payload["target"] = document_ids
        if namespace is not None:
            payload["namespace"] = namespace
        if memory_id:
            payload["memory_id"] = memory_id
        if user_id:
            payload["user_id"] = user_id
        res = self._request(
            "DELETE",
            "/v1/memory/forget",
            payload,
            query_params={"memory_id": memory_id, "user_id": user_id},
        )
        return res if isinstance(res, dict) else {"deleted": True}

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

        res = self._request("POST", "/v1/memories/", payload)
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

        endpoint = "/v2/memories/search/" if str(version).lower() == "v2" else "/v1/memories/search/"
        res = self._request("POST", endpoint, payload)
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
        **kwargs: Any,
    ) -> dict[str, Any]:
        """List memories via `GET /v1/memories/`."""
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
        if filters:
            params["filters"] = json.dumps(filters)
        params.update(kwargs)
        res = self._request("GET", "/v1/memories/", query_params=params)
        if isinstance(res, list):
            return {"results": res}
        return res if isinstance(res, dict) else {"results": []}

    def get(self, memory_id: str) -> dict[str, Any] | None:
        """Fetch a single memory by ID via `GET /v1/memories/{memory_id}/`."""
        try:
            res = self._request("GET", f"/v1/memories/{urllib.parse.quote(str(memory_id))}/")
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
        res = self._request(
            "PUT",
            f"/v1/memories/{urllib.parse.quote(str(memory_id))}/",
            payload,
        )
        return res if isinstance(res, dict) else {"id": memory_id}

    def delete(self, memory_id: str) -> dict[str, Any]:
        """Delete a single memory via `DELETE /v1/memories/{memory_id}/`."""
        res = self._request(
            "DELETE",
            f"/v1/memories/{urllib.parse.quote(str(memory_id))}/",
        )
        return res if isinstance(res, dict) else {"id": memory_id, "deleted": True}

    def delete_all(
        self,
        *,
        user_id: str | None = None,
        agent_id: str | None = None,
        app_id: str | None = None,
        run_id: str | None = None,
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
        res = self._request("DELETE", "/v1/memories/", query_params=params)
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

    def batch_update(self, memories: list[dict[str, Any]]) -> dict[str, Any]:
        """Batch update multiple memories via `PUT /v1/batch/`."""
        res = self._request("PUT", "/v1/batch/", {"memories": memories})
        return res if isinstance(res, dict) else {"results": res}

    def batch_delete(self, memories: list[str | dict[str, Any]]) -> dict[str, Any]:
        """Batch delete multiple memories via `DELETE /v1/batch/`."""
        normalized = [
            m if isinstance(m, dict) else {"memory_id": str(m), "id": str(m)}
            for m in memories
        ]
        res = self._request("DELETE", "/v1/batch/", {"memories": normalized})
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

    # CamelCase aliases for JS/TS cross-compatibility
    getAll = get_all
    deleteAll = delete_all
    batchUpdate = batch_update
    batchDelete = batch_delete
    deleteUsers = delete_users


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
            model=model,
            timeout_s=timeout_s,
            transport=transport,
        )
        self.api_key = self._sync.api_key
        self.base_url = self._sync.base_url
        self.host = self._sync.host
        self.org_id = self._sync.org_id
        self.project_id = self._sync.project_id
        self.model = self._sync.model
        self.timeout_s = self._sync.timeout_s
        self.project = _AsyncProjectManager(self._sync.project)

    async def close(self) -> None:
        await asyncio.to_thread(self._sync.close)

    async def __aenter__(self) -> "AsyncMemoryClient":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def ingest(self, documents: Any, **kwargs: Any) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.ingest, documents, **kwargs)

    async def query(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.query, prompt, **kwargs)

    async def forget(self, **kwargs: Any) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.forget, **kwargs)

    async def add(self, messages: Any, **kwargs: Any) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.add, messages, **kwargs)

    async def search(self, query: str, **kwargs: Any) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.search, query, **kwargs)

    async def recall(self, query: str, **kwargs: Any) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.recall, query, **kwargs)

    async def get_all(self, **kwargs: Any) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.get_all, **kwargs)

    async def get(self, memory_id: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._sync.get, memory_id)

    async def update(
        self,
        memory_id: str,
        data: str | dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.update, memory_id, data, **kwargs)

    async def delete(self, memory_id: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.delete, memory_id)

    async def delete_all(self, **kwargs: Any) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.delete_all, **kwargs)

    async def reset(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.reset)

    async def history(self, memory_id: str) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._sync.history, memory_id)

    async def batch_update(self, memories: list[dict[str, Any]]) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.batch_update, memories)

    async def batch_delete(self, memories: list[str | dict[str, Any]]) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.batch_delete, memories)

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

    getAll = get_all
    deleteAll = delete_all
    batchUpdate = batch_update
    batchDelete = batch_delete
    deleteUsers = delete_users


SlashMLClient = MemoryClient
SlashMLMemory = MemoryClient
AsyncSlashMLClient = AsyncMemoryClient
AsyncSlashMLMemory = AsyncMemoryClient
