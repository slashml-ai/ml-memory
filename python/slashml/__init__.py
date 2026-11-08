"""Official HTTP Python SDK for / ml (`https://api.slashml.ai`).

Provides 100% Mem0-compatible `Memory` and `MemoryClient` alongside `SlashMLMemory` and `SlashMLClient`.
"""

from slashml.client import (
    DEFAULT_BASE_URL,
    AsyncMemoryClient,
    AsyncSlashMLClient,
    AsyncSlashMLMemory,
    CacheAlignedPrompt,
    ContrastiveRule,
    MemoryClient,
    RuleScope,
    SlashMLAPIError,
    SlashMLClient,
    SlashMLMemory,
    compile_contrastive_rule,
    extract_canonical_slot_key,
    format_cache_aligned_prompt,
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
from slashml.mcp_server import (
    SlashMLMCPServer,
    install_ambient_hooks,
    run_ambient_hook_mode,
)
from slashml.repo_indexer import (
    RepositoryIndexer,
    find_bug_candidates,
    remap_memory_file_references,
    search_code_by_behavior,
)

__version__ = "1.0.10"
__all__ = [
    "AsyncMemory",
    "AsyncMemoryClient",
    "AsyncSlashMLClient",
    "AsyncSlashMLMemory",
    "CacheAlignedPrompt",
    "ContrastiveRule",
    "DEFAULT_BASE_URL",
    "Memory",
    "MemoryClient",
    "RepositoryIndexer",
    "RuleScope",
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
    "compile_contrastive_rule",
    "extract_canonical_slot_key",
    "find_bug_candidates",
    "format_cache_aligned_prompt",
    "install_ambient_hooks",
    "remap_memory_file_references",
    "run_ambient_hook_mode",
    "search_code_by_behavior",
]
