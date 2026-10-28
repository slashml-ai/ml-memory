"""1-line drop-in replacement for `from mem0 import Memory, AsyncMemory` (`from slashml import Memory, AsyncMemory`).

Thin HTTP wrapper delegating all storage, indexing, and retrieval operations
to the `/ ml` Cloud API (`https://api.slashml.ai`).
"""

from __future__ import annotations

from typing import Any, Generator

from slashml.client import AsyncMemoryClient, MemoryClient, TransportCallable


def _extract_config_kwargs(
    config: dict[str, Any] | None,
    *,
    api_key: str | None = None,
    host: str | None = None,
    base_url: str | None = None,
    org_id: str | None = None,
    project_id: str | None = None,
    model: str = "slashml-nano",
    timeout_s: float = 30.0,
    transport: TransportCallable | None = None,
) -> dict[str, Any]:
    cfg = dict(config or {})
    if isinstance(cfg, dict):
        if api_key is None:
            api_key = cfg.get("api_key") or cfg.get("apiKey")
        if base_url is None and host is None:
            base_url = cfg.get("base_url") or cfg.get("host") or cfg.get("baseUrl")
        if org_id is None:
            org_id = cfg.get("org_id") or cfg.get("orgId")
        if project_id is None:
            project_id = cfg.get("project_id") or cfg.get("projectId")
        if cfg.get("model"):
            model = str(cfg["model"])
        if transport is None:
            transport = cfg.get("transport")
    return {
        "api_key": api_key,
        "host": host,
        "base_url": base_url,
        "org_id": org_id,
        "project_id": project_id,
        "model": model,
        "timeout_s": timeout_s,
        "transport": transport,
    }


class Memory(MemoryClient):
    """1-line drop-in replacement for `mem0.Memory` backed by `https://api.slashml.ai`."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        api_key: str | None = None,
        host: str | None = None,
        base_url: str | None = None,
        org_id: str | None = None,
        project_id: str | None = None,
        model: str = "slashml-nano",
        timeout_s: float = 30.0,
        transport: TransportCallable | None = None,
    ) -> None:
        self.config = dict(config or {})
        kwargs = _extract_config_kwargs(
            self.config,
            api_key=api_key,
            host=host,
            base_url=base_url,
            org_id=org_id,
            project_id=project_id,
            model=model,
            timeout_s=timeout_s,
            transport=transport,
        )
        super().__init__(**kwargs)

    @classmethod
    def from_config(cls, config_dict: dict[str, Any]) -> "Memory":
        return cls(config=config_dict)


class AsyncMemory(AsyncMemoryClient):
    """1-line drop-in replacement for `mem0.AsyncMemory` backed by `https://api.slashml.ai`.

    Supports both synchronous (`mem = AsyncMemory.from_config(cfg)`) and
    asynchronous (`mem = await AsyncMemory.from_config(cfg)`) instantiation patterns.
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        api_key: str | None = None,
        host: str | None = None,
        base_url: str | None = None,
        org_id: str | None = None,
        project_id: str | None = None,
        model: str = "slashml-nano",
        timeout_s: float = 30.0,
        transport: TransportCallable | None = None,
    ) -> None:
        self.config = dict(config or {})
        kwargs = _extract_config_kwargs(
            self.config,
            api_key=api_key,
            host=host,
            base_url=base_url,
            org_id=org_id,
            project_id=project_id,
            model=model,
            timeout_s=timeout_s,
            transport=transport,
        )
        super().__init__(**kwargs)

    def __await__(self) -> Generator[Any, None, "AsyncMemory"]:
        async def _coro() -> "AsyncMemory":
            return self

        return _coro().__await__()

    @classmethod
    def from_config(cls, config_dict: dict[str, Any]) -> "AsyncMemory":
        return cls(config=config_dict)
