"""Official HTTP Python SDK for / ml (`https://api.slashml.ai`).

Provides `MemoryClient` / `SlashMLMemory` (100% 1:1 Mem0 Cloud Client & `/ ml` API drop-in).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import fnmatch
import http.client
import json
import os
from pathlib import PurePath
import socket
import ssl
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Sequence

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


@dataclass
class RuleScope:
    """Activation scope predicate for an operational rule or constraint."""

    file_patterns: list[str] = field(default_factory=list)
    tool_triggers: list[str] = field(default_factory=list)
    intents: list[str] = field(default_factory=list)
    custom: dict[str, Any] = field(default_factory=dict)

    def is_global(self) -> bool:
        return not (self.file_patterns or self.tool_triggers or self.intents or self.custom)

    def matches(self, context: dict[str, Any] | None) -> bool:
        if self.is_global():
            return True
        if not context:
            return False

        file_path = str(context.get("file_path") or context.get("file") or "").strip()
        if self.file_patterns:
            if not file_path:
                return False
            matched = False
            for pat in self.file_patterns:
                if fnmatch.fnmatch(file_path, pat) or fnmatch.fnmatch(PurePath(file_path).name, pat):
                    matched = True
                    break
                if pat.startswith("*.") and file_path.endswith(pat[1:]):
                    matched = True
                    break
            if not matched:
                return False

        tool_name = str(context.get("tool_name") or context.get("tool") or "").strip()
        if self.tool_triggers:
            if not tool_name or tool_name not in self.tool_triggers:
                return False

        ctx_intents = context.get("intents") or []
        if isinstance(ctx_intents, str):
            ctx_intents = [ctx_intents]
        single_intent = context.get("intent")
        if single_intent:
            ctx_intents = list(ctx_intents) + [single_intent]
        ctx_intents_set = {str(i).lower() for i in ctx_intents}

        if self.intents:
            rule_intents_set = {str(i).lower() for i in self.intents}
            if not (ctx_intents_set & rule_intents_set):
                return False

        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_patterns": list(self.file_patterns),
            "tool_triggers": list(self.tool_triggers),
            "intents": list(self.intents),
            "custom": dict(self.custom),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> RuleScope:
        if not data:
            return cls()
        return cls(
            file_patterns=list(data.get("file_patterns") or data.get("filePatterns") or []),
            tool_triggers=list(data.get("tool_triggers") or data.get("toolTriggers") or []),
            intents=list(data.get("intents") or []),
            custom=dict(data.get("custom") or {}),
        )


@dataclass
class ContrastiveRule:
    """Operational rule formulated as a contrastive triplet (context, do, dont)."""

    rule_id: str
    do: str
    dont: str
    context: str = ""
    scope: RuleScope = field(default_factory=RuleScope)
    raw_text: str = ""

    def to_compact_xml(self) -> str:
        ctx_attr = f' context="{self.context}"' if self.context else ""
        return f'<rule id="{self.rule_id}"{ctx_attr}>\n  <do>{self.do}</do>\n  <dont>{self.dont}</dont>\n</rule>'

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "do": self.do,
            "dont": self.dont,
            "context": self.context,
            "scope": self.scope.to_dict(),
            "raw_text": self.raw_text,
        }


def extract_canonical_slot_key(text: str, metadata: dict[str, Any] | None = None) -> str | None:
    """Return canonical slot key from explicit metadata if provided."""
    if metadata and metadata.get("slot_key"):
        return str(metadata["slot_key"]).strip().lower()
    return None


def compile_contrastive_rule(
    text: str,
    rule_id: str | None = None,
    scope: RuleScope | dict[str, Any] | None = None,
    do: str | None = None,
    dont: str | None = None,
) -> ContrastiveRule:
    """Structure rule parameters into a ContrastiveRule container."""
    clean_text = text.strip()
    rid = rule_id or f"rule_{abs(hash(clean_text)) % 1000000:06d}"
    parsed_scope = scope if isinstance(scope, RuleScope) else RuleScope.from_dict(scope)
    return ContrastiveRule(
        rule_id=rid,
        do=str(do or clean_text),
        dont=str(dont or ""),
        scope=parsed_scope,
        raw_text=clean_text,
    )


@dataclass
class CacheAlignedPrompt:
    """Prompt formatted according to Cache-Aligned Minimal-Intervention Delivery."""

    zone1_rules_text: str
    zone2_facts_text: str
    user_turn: str
    whisper_block: str
    full_prompt_text: str
    has_cache_breakpoint: bool
    token_economics: dict[str, Any]


def format_cache_aligned_prompt(
    rules: Sequence[ContrastiveRule | dict[str, Any]],
    facts: Sequence[str | dict[str, Any]],
    user_prompt: str,
    active_context: dict[str, Any] | None = None,
    whisper_rule: ContrastiveRule | dict[str, Any] | None = None,
    enable_cache_breakpoint: bool = True,
) -> CacheAlignedPrompt:
    """Format prompt with Zone 1 (static rules) and Zone 2 (dynamic facts)."""
    norm_rules: list[ContrastiveRule] = []
    for r in rules:
        if isinstance(r, ContrastiveRule):
            norm_rules.append(r)
        elif isinstance(r, dict):
            scope_dict = r.get("scope") if isinstance(r.get("scope"), dict) else {}
            scope_obj = RuleScope.from_dict(scope_dict)
            norm_rules.append(
                ContrastiveRule(
                    rule_id=str(r.get("rule_id") or r.get("id") or "rule"),
                    do=str(r.get("do") or r.get("text") or ""),
                    dont=str(r.get("dont") or ""),
                    context=str(r.get("context") or ""),
                    scope=scope_obj,
                    raw_text=str(r.get("raw_text") or r.get("text") or ""),
                )
            )

    active_rules = [r for r in norm_rules if r.scope.matches(active_context)]

    zone1_lines: list[str] = []
    if active_rules:
        zone1_lines.append("<rules>")
        for r in active_rules:
            zone1_lines.append(r.to_compact_xml())
        zone1_lines.append("</rules>")
    zone1_text = "\n".join(zone1_lines)

    zone2_lines: list[str] = []
    if facts:
        zone2_lines.append("<facts>")
        for f in facts:
            f_text = f if isinstance(f, str) else str(f.get("text") or f.get("memory") or "")
            if f_text:
                zone2_lines.append(f"<fact>{f_text}</fact>")
        zone2_lines.append("</facts>")
    zone2_text = "\n".join(zone2_lines)

    whisper_text = ""
    if whisper_rule:
        w_do = whisper_rule.do if isinstance(whisper_rule, ContrastiveRule) else str(whisper_rule.get("do") or "")
        w_dont = whisper_rule.dont if isinstance(whisper_rule, ContrastiveRule) else str(whisper_rule.get("dont") or "")
        whisper_text = (
            f"<whisper>\n"
            f"  [CRITICAL CONSTRAINT ACTIVE]\n"
            f"  DO: {w_do}\n"
            f"  DON'T: {w_dont}\n"
            f"</whisper>"
        )

    prompt_parts: list[str] = []
    if zone1_text:
        prompt_parts.append(zone1_text)
    if enable_cache_breakpoint and zone1_text:
        prompt_parts.append("<!-- cache_control: ephemeral_breakpoint -->")
    if zone2_text:
        prompt_parts.append(zone2_text)
    if whisper_text:
        prompt_parts.append(whisper_text)
    prompt_parts.append(user_prompt)

    full_prompt = "\n\n".join(p for p in prompt_parts if p)

    z1_tok = max(1, len(zone1_text) // 4) if zone1_text else 0
    z2_tok = max(1, len(zone2_text) // 4) if zone2_text else 0
    wh_tok = max(1, len(whisper_text) // 4) if whisper_text else 0
    tot_tok = max(1, len(full_prompt) // 4)

    token_econ = {
        "zone1_static_tokens": z1_tok,
        "zone2_dynamic_tokens": z2_tok,
        "whisper_tokens": wh_tok,
        "total_prompt_tokens": tot_tok,
        "prefix_cache_eligible_ratio": round(z1_tok / tot_tok, 4) if tot_tok > 0 else 0.0,
        "unfiltered_rule_count": len(norm_rules),
        "active_rule_count": len(active_rules),
        "scoped_suppression_count": len(norm_rules) - len(active_rules),
    }

    return CacheAlignedPrompt(
        zone1_rules_text=zone1_text,
        zone2_facts_text=zone2_text,
        user_turn=user_prompt,
        whisper_block=whisper_text,
        full_prompt_text=full_prompt,
        has_cache_breakpoint=enable_cache_breakpoint,
        token_economics=token_econ,
    )


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
            "User-Agent": "slashml-python-sdk/1.0.10",
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
        record_tier: str | None = None,
        slot_key: str | None = None,
        scope: dict[str, Any] | RuleScope | None = None,
        contrastive: dict[str, str] | ContrastiveRule | None = None,
    ) -> dict[str, Any]:
        """Ingest one or more documents into `/v1/memory/ingest`."""
        meta = dict(metadata or {})
        effective_tier = record_tier or meta.get("record_tier") or meta.get("tier")
        if effective_tier:
            meta["record_tier"] = str(effective_tier)

        effective_slot = slot_key or meta.get("slot_key")
        if not effective_slot and text:
            effective_slot = extract_canonical_slot_key(text, meta)
        if effective_slot:
            meta["slot_key"] = str(effective_slot)

        if scope is not None:
            meta["scope"] = scope.to_dict() if isinstance(scope, RuleScope) else dict(scope)
        if contrastive is not None:
            meta["contrastive"] = contrastive.to_dict() if isinstance(contrastive, ContrastiveRule) else dict(contrastive)

        payload: dict[str, Any] = {"model": model or self.model}
        if namespace is not None:
            payload["namespace"] = namespace
        if meta.get("record_tier"):
            payload["record_tier"] = meta["record_tier"]
        if meta.get("slot_key"):
            payload["slot_key"] = meta["slot_key"]

        if documents is not None:
            raw_docs = [documents] if isinstance(documents, str) else list(documents)
            proc_docs = []
            for d in raw_docs:
                if isinstance(d, dict):
                    d_copy = dict(d)
                    d_meta = dict(d_copy.get("metadata") or {})
                    for k in ("record_tier", "slot_key", "scope", "contrastive"):
                        if k in meta and k not in d_meta:
                            d_meta[k] = meta[k]
                    d_copy["metadata"] = d_meta
                    proc_docs.append(d_copy)
                else:
                    d_text = str(d)
                    d_slot = extract_canonical_slot_key(d_text, meta) if not meta.get("slot_key") else meta["slot_key"]
                    d_meta = dict(meta)
                    if d_slot:
                        d_meta["slot_key"] = d_slot
                    proc_docs.append({"text": d_text, "metadata": d_meta})
            payload["documents"] = proc_docs
            if user_id:
                payload["user_id"] = user_id
            if meta:
                payload["metadata"] = meta
        elif text is not None:
            doc: dict[str, Any] = {"text": text}
            if doc_id:
                doc["id"] = doc_id
            if user_id:
                doc["user_id"] = user_id
            if meta:
                doc["metadata"] = meta
            payload["documents"] = [doc]
            payload["text"] = text
            if user_id:
                payload["user_id"] = user_id
            if meta:
                payload["metadata"] = meta
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
        record_tier: str | None = None,
        context: dict[str, Any] | None = None,
        include_rules: bool | None = None,
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
        if record_tier is not None:
            payload["record_tier"] = str(record_tier)
        if context is not None:
            payload["context"] = dict(context)
        if include_rules is not None:
            payload["include_rules"] = bool(include_rules)
        res = self._request("POST", "/v1/memory/query", payload)
        return res if isinstance(res, dict) else {"results": res}

    def add_rule(
        self,
        text: str,
        *,
        rule_id: str | None = None,
        do: str | None = None,
        dont: str | None = None,
        scope: dict[str, Any] | RuleScope | None = None,
        user_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Ingest an operational rule or constraint (Tier B)."""
        rule = compile_contrastive_rule(text, rule_id=rule_id, scope=scope)
        if do is not None:
            rule.do = do
        if dont is not None:
            rule.dont = dont
        meta = dict(metadata or {})
        meta["rule_id"] = rule.rule_id
        meta["scope"] = rule.scope.to_dict()
        meta["contrastive"] = {"do": rule.do, "dont": rule.dont, "context": rule.context}
        return self.ingest(
            text=text,
            doc_id=rule.rule_id,
            user_id=user_id,
            metadata=meta,
            record_tier="rule",
            scope=rule.scope,
            contrastive=rule,
        )

    def get_cache_aligned_prompt(
        self,
        user_turn: str,
        *,
        active_context: dict[str, Any] | None = None,
        top_k: int = 5,
        user_id: str | None = None,
        enable_cache_breakpoint: bool = True,
    ) -> CacheAlignedPrompt:
        """Retrieve scoped rules and dynamic facts, returning a cache-aligned prompt."""
        rules_res = self.query(
            user_turn,
            top_k=20,
            user_id=user_id,
            record_tier="rule",
            context=active_context,
        )
        raw_rules = rules_res.get("results") or rules_res.get("memories") or []
        rules_list: list[ContrastiveRule] = []
        for r in raw_rules:
            r_meta = r.get("metadata") or {}
            c_info = r_meta.get("contrastive") or {}
            s_info = r_meta.get("scope") or {}
            rules_list.append(
                ContrastiveRule(
                    rule_id=str(r.get("id") or r_meta.get("rule_id") or "rule"),
                    do=str(c_info.get("do") or r.get("text") or ""),
                    dont=str(c_info.get("dont") or ""),
                    context=str(c_info.get("context") or ""),
                    scope=RuleScope.from_dict(s_info),
                    raw_text=str(r.get("text") or ""),
                )
            )

        facts_res = self.query(
            user_turn,
            top_k=top_k,
            user_id=user_id,
            record_tier="fact",
        )
        raw_facts = facts_res.get("results") or facts_res.get("memories") or []
        facts_list = [str(f.get("text") or f.get("memory") or "") for f in raw_facts if f]

        return format_cache_aligned_prompt(
            rules=rules_list,
            facts=facts_list,
            user_prompt=user_turn,
            active_context=active_context,
            enable_cache_breakpoint=enable_cache_breakpoint,
        )

    def forget(
        self,
        document_ids: list[str] | str | None = None,
        *,
        memory_id: str | None = None,
        user_id: str | None = None,
        namespace: str | None = None,
    ) -> dict[str, Any]:
        """Delete documents from memory via `DELETE /v1/memory/forget`."""
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

    def intervene(
        self,
        text: str | dict[str, Any] = "",
        *,
        hook_event_name: str = "UserPromptSubmit",
        prompt: str | None = None,
        last_assistant_message: str | None = None,
        stop_hook_active: bool = False,
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
        res = self._request("POST", "/v1/memory/intervene", payload)
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
        meta = dict(metadata or {})
        effective_tier = kwargs.pop("record_tier", None) or meta.get("record_tier") or meta.get("tier")
        if effective_tier:
            meta["record_tier"] = str(effective_tier)
            payload["record_tier"] = str(effective_tier)
        effective_slot = kwargs.pop("slot_key", None) or meta.get("slot_key")
        if not effective_slot and isinstance(messages, str):
            effective_slot = extract_canonical_slot_key(messages, meta)
        if effective_slot:
            meta["slot_key"] = str(effective_slot)
            payload["slot_key"] = str(effective_slot)
        scope = kwargs.pop("scope", None)
        if scope is not None:
            meta["scope"] = scope.to_dict() if isinstance(scope, RuleScope) else dict(scope)
        contrastive = kwargs.pop("contrastive", None)
        if contrastive is not None:
            meta["contrastive"] = contrastive.to_dict() if isinstance(contrastive, ContrastiveRule) else dict(contrastive)
        if meta:
            payload["metadata"] = meta
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

    async def intervene(self, text: Any = "", **kwargs: Any) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.intervene, text, **kwargs)

    async def status(self, **kwargs: Any) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.status, **kwargs)

    async def add_rule(self, text: str, **kwargs: Any) -> dict[str, Any]:
        return await asyncio.to_thread(self._sync.add_rule, text, **kwargs)

    async def get_cache_aligned_prompt(self, user_turn: str, **kwargs: Any) -> CacheAlignedPrompt:
        return await asyncio.to_thread(self._sync.get_cache_aligned_prompt, user_turn, **kwargs)

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
