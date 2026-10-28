"""LlamaIndex Retriever & VectorStore Integration for `/ ml` (`https://api.slashml.ai`)."""

from __future__ import annotations

from typing import Any

from slashml.client import MemoryClient


class SlashMLLlamaIndexRetriever:
    """LlamaIndex-compatible Retriever backed by `/ ml` Cloud."""

    def __init__(
        self,
        *,
        client: MemoryClient | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        user_id: str = "default",
        similarity_top_k: int = 5,
    ) -> None:
        self.client = client or MemoryClient(api_key=api_key, base_url=base_url)
        self.user_id = user_id
        self.similarity_top_k = similarity_top_k

    def retrieve(self, query: str) -> list[dict[str, Any]]:
        res = self.client.search(query, user_id=self.user_id, limit=self.similarity_top_k)
        return list(res.get("results") or [])


class SlashMLLlamaIndexVectorStore:
    """LlamaIndex-compatible VectorStore backed by `/ ml` Cloud."""

    def __init__(
        self,
        *,
        client: MemoryClient | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        user_id: str = "default",
    ) -> None:
        self.client = client or MemoryClient(api_key=api_key, base_url=base_url)
        self.user_id = user_id

    def add(self, nodes: list[dict[str, Any]]) -> dict[str, Any]:
        return self.client.ingest(documents=nodes, user_id=self.user_id)

    def query(self, query_str: str, similarity_top_k: int = 5) -> list[dict[str, Any]]:
        res = self.client.query(query_str, user_id=self.user_id, top_k=similarity_top_k)
        return list(res.get("results") or [])

    def delete(self, ref_doc_id: str) -> dict[str, Any]:
        return self.client.forget(ref_doc_id, user_id=self.user_id)
