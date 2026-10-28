"""LangChain Integration for `/ ml` (`https://api.slashml.ai`)."""

from __future__ import annotations

from typing import Any

from slashml.client import MemoryClient


class SlashMLChatMessageHistory:
    """LangChain-compatible ChatMessageHistory backed by `/ ml` Cloud."""

    def __init__(
        self,
        session_id: str,
        *,
        client: MemoryClient | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.session_id = session_id
        self.client = client or MemoryClient(api_key=api_key, base_url=base_url)

    def add_user_message(self, message: str) -> dict[str, Any]:
        return self.client.add(
            [{"role": "user", "content": message}],
            user_id=self.session_id,
            metadata={"role": "user"},
        )

    def add_ai_message(self, message: str) -> dict[str, Any]:
        return self.client.add(
            [{"role": "assistant", "content": message}],
            user_id=self.session_id,
            metadata={"role": "assistant"},
        )

    @property
    def messages(self) -> list[dict[str, Any]]:
        return list(self.client.get_all(user_id=self.session_id).get("results") or [])

    def clear(self) -> dict[str, Any]:
        return self.client.delete_all(user_id=self.session_id)


class SlashMLLangChainRetriever:
    """LangChain-compatible Retriever backed by `/ ml` Cloud."""

    def __init__(
        self,
        *,
        client: MemoryClient | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        user_id: str = "default",
        top_k: int = 5,
    ) -> None:
        self.client = client or MemoryClient(api_key=api_key, base_url=base_url)
        self.user_id = user_id
        self.top_k = top_k

    def invoke(self, query: str) -> list[dict[str, Any]]:
        res = self.client.search(query, user_id=self.user_id, limit=self.top_k)
        return list(res.get("results") or [])

    def get_relevant_documents(self, query: str) -> list[dict[str, Any]]:
        return self.invoke(query)


class SlashMLLangChainVectorStore:
    """LangChain-compatible VectorStore adapter backed by `/ ml` Cloud."""

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

    def add_texts(
        self,
        texts: list[str],
        metadatas: list[dict[str, Any]] | None = None,
        ids: list[str] | None = None,
    ) -> list[str]:
        docs: list[dict[str, Any]] = []
        for idx, text in enumerate(texts):
            doc: dict[str, Any] = {"text": text, "user_id": self.user_id}
            if metadatas and idx < len(metadatas):
                doc["metadata"] = metadatas[idx]
            if ids and idx < len(ids):
                doc["id"] = ids[idx]
            docs.append(doc)
        self.client.ingest(documents=docs, user_id=self.user_id)
        return [str(d.get("id", f"doc_{i}")) for i, d in enumerate(docs)]

    def similarity_search(self, query: str, k: int = 5) -> list[dict[str, Any]]:
        res = self.client.search(query, user_id=self.user_id, limit=k)
        return list(res.get("results") or [])

    def delete(self, ids: list[str] | str) -> bool:
        self.client.forget(ids, user_id=self.user_id)
        return True
