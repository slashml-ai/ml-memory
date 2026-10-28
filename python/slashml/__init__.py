"""/ ml (`slashml`) Python SDK — Sub-Millisecond Stateful Agent & Code Memory.

Provides 100% Mem0-compatible `Memory` and `MemoryClient` alongside `SlashMLMemory` and `SlashMLClient`.
"""

from slashml.client import (
    DEFAULT_BASE_URL,
    AsyncMemoryClient,
    AsyncSlashMLClient,
    AsyncSlashMLMemory,
    MemoryClient,
    SlashMLAPIError,
    SlashMLClient,
    SlashMLMemory,
)
from slashml.compat import AsyncMemory, Memory
from slashml.integrations import (
    SlashMLChatMessageHistory,
    SlashMLCrewAIMemory,
    SlashMLLangChainRetriever,
    SlashMLLangChainVectorStore,
    SlashMLLangGraphCheckpointer,
    SlashMLLangGraphStore,
    SlashMLLlamaIndexRetriever,
    SlashMLLlamaIndexVectorStore,
)
from slashml.mcp_server import SlashMLMCPServer
from slashml.repo_indexer import (
    RepositoryIndexer,
    find_bug_candidates,
    remap_memory_file_references,
    search_code_by_behavior,
)

__version__ = "1.0.0"
__all__ = [
    "AsyncMemory",
    "AsyncMemoryClient",
    "AsyncSlashMLClient",
    "AsyncSlashMLMemory",
    "DEFAULT_BASE_URL",
    "Memory",
    "MemoryClient",
    "RepositoryIndexer",
    "SlashMLAPIError",
    "SlashMLChatMessageHistory",
    "SlashMLClient",
    "SlashMLCrewAIMemory",
    "SlashMLLangChainRetriever",
    "SlashMLLangChainVectorStore",
    "SlashMLLangGraphCheckpointer",
    "SlashMLLangGraphStore",
    "SlashMLLlamaIndexRetriever",
    "SlashMLLlamaIndexVectorStore",
    "SlashMLMCPServer",
    "SlashMLMemory",
    "__version__",
    "find_bug_candidates",
    "remap_memory_file_references",
    "search_code_by_behavior",
]
