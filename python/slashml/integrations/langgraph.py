"""LangGraph Store & Checkpointer Integration for `/ ml` (`https://api.slashml.ai`)."""

from __future__ import annotations

import json
from typing import Any

from slashml.client import MemoryClient


class SlashMLLangGraphStore:
    """LangGraph-compatible cross-thread BaseStore backed by `/ ml` Cloud."""

    def __init__(
        self,
        *,
        client: MemoryClient | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.client = client or MemoryClient(api_key=api_key, base_url=base_url)

    def put(self, namespace: tuple[str, ...], key: str, value: dict[str, Any]) -> dict[str, Any]:
        ns_str = "/".join(namespace)
        doc_id = f"{ns_str}::{key}"
        text = value.get("text") or json.dumps(value, sort_keys=True)
        return self.client.add(
            str(text),
            user_id=ns_str,
            memory_id=doc_id,
            metadata={"namespace": ns_str, "key": key, "value": value},
        )

    def get(self, namespace: tuple[str, ...], key: str) -> dict[str, Any] | None:
        ns_str = "/".join(namespace)
        doc_id = f"{ns_str}::{key}"
        return self.client.get(doc_id)

    def delete(self, namespace: tuple[str, ...], key: str) -> dict[str, Any]:
        ns_str = "/".join(namespace)
        doc_id = f"{ns_str}::{key}"
        return self.client.delete(doc_id)

    def search(
        self,
        namespace_prefix: tuple[str, ...],
        *,
        query: str = "",
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        ns_str = "/".join(namespace_prefix)
        if query:
            res = self.client.search(query, user_id=ns_str, limit=limit)
        else:
            res = self.client.get_all(user_id=ns_str, limit=limit)
        return list(res.get("results") or [])


class SlashMLLangGraphCheckpointer:
    """LangGraph-compatible state checkpointer backed by `/ ml` Cloud."""

    def __init__(
        self,
        *,
        client: MemoryClient | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.client = client or MemoryClient(api_key=api_key, base_url=base_url)

    def put(self, thread_id: str, checkpoint_id: str, state: dict[str, Any]) -> dict[str, Any]:
        doc_id = f"ckpt::{thread_id}::{checkpoint_id}"
        return self.client.add(
            json.dumps(state, sort_keys=True),
            user_id=f"thread::{thread_id}",
            memory_id=doc_id,
            metadata={"thread_id": thread_id, "checkpoint_id": checkpoint_id},
        )

    def get(self, thread_id: str, checkpoint_id: str) -> dict[str, Any] | None:
        doc_id = f"ckpt::{thread_id}::{checkpoint_id}"
        return self.client.get(doc_id)
