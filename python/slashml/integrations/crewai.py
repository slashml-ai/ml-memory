"""CrewAI Memory Storage Integration for `/ ml` (`https://api.slashml.ai`)."""

from __future__ import annotations

from typing import Any

from slashml.client import MemoryClient


class SlashMLCrewAIMemory:
    """CrewAI-compatible Storage backend powered by `/ ml` Cloud."""

    def __init__(
        self,
        *,
        client: MemoryClient | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        crew_id: str = "default_crew",
    ) -> None:
        self.client = client or MemoryClient(api_key=api_key, base_url=base_url)
        self.crew_id = crew_id

    def save(self, value: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.client.add(value, user_id=self.crew_id, metadata=metadata)

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        res = self.client.search(query, user_id=self.crew_id, limit=limit)
        return list(res.get("results") or [])

    def reset(self) -> dict[str, Any]:
        return self.client.delete_all(user_id=self.crew_id)
