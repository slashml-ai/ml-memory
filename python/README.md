# `/ ml` (`slashml-memory`) Python SDK

Official HTTP Python SDK for **`/ ml` (`https://api.slashml.ai`)**.

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

# Ingest text or source code
client.ingest(
    documents=[
        {"id": "doc_1", "text": "Production PostgreSQL runs on port 5432 with pgBouncer on 6432."}
    ],
    user_id="alice",
)

# Query stored memories
hits = client.query("Which port does pgBouncer listen on?", user_id="alice", top_k=3)
print(hits["results"][0])

# Delete documents by ID
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

# 3. Evaluate an agent turn or tool action
decision = client.intervene(
    "pip install pytest",
    hook_event_name="PreToolUse",
    tool_name="Bash",
    user_id="developer_1",
)
```

### 3. Inline Redaction & Per-Agent Read/Write Access Control

```python
from slashml import Memory

admin = Memory(api_key="sml_live_...")

# Configure workspace defaults & bind a read-only, GDPR-masked support agent
admin.set_redaction_policy(
    redact_policy="tier1_secrets",
    redact_scope="recall_only",
    access_mode="read_write",
)
admin.configure_agent(
    agent_id="support_triage_bot",
    access_mode="read_only",
    redact_policy="gdpr",
    redact_scope="recall_only",
)

# Scoped agent client automatically attaches X-SlashML-Agent-Id
triage = Memory(api_key="sml_live_...", agent_id="support_triage_bot")
masked = triage.redact(text="Billing contact is alice@acme.io")
recalled = triage.search("Who is the billing contact?", user_id="developer_1")
```

### 4. CLI & Ambient Hook Installation

```bash
python -m slashml.mcp_server --install-hooks --api-key "$SLASHML_API_KEY" --agent-id "coding_agent" --redact-policy "soc2_coding"
```

## License

Apache-2.0

<!-- mcp-name: io.github.slashml-ai/ml-memory -->


