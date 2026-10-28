# `/ ml` (`slashml-memory`) Python SDK

Official thin HTTP Python SDK for **`/ ml` (`https://api.slashml.ai`)** — sub-millisecond stateful agent & code memory. Zero native binary or local model dependencies (`urllib.request` standard library).

## Installation

```bash
pip install slashml-memory
export SLASHML_API_KEY="sml_live_..."
```

## Quickstart

### 1. Native `/ ml` Memory Client (`SlashMLMemory` / `MemoryClient`)

```python
from slashml import SlashMLMemory

client = SlashMLMemory(api_key="sml_live_...")

# Ingest raw text or source code in a single pass ($0 LLM extraction cost)
client.ingest(
    documents=[
        {"id": "doc_1", "text": "Production PostgreSQL runs on port 5432 with pgBouncer on 6432."}
    ],
    user_id="alice",
)

# Sub-millisecond semantic & code query
hits = client.query("Which port does pgBouncer listen on?", user_id="alice", top_k=3)
print(hits["results"][0])

# Physical O(1) GDPR unlearning
client.forget(["doc_1"], user_id="alice")
```

### 2. 1-Line `Mem0` Drop-In Replacement (`Memory` & `MemoryClient`)

Replace `from mem0 import MemoryClient` or `from mem0 import Memory` with `from slashml import MemoryClient, Memory`:

```python
# Before: from mem0 import MemoryClient
from slashml import MemoryClient

client = MemoryClient(api_key="sml_live_...")

client.add(
    [{"role": "user", "content": "Always use uv and pytest -q for Python checks."}],
    user_id="developer_1",
)

results = client.search("How should I run Python tests?", user_id="developer_1")
```
