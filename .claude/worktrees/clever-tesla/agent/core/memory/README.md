# Roamin Memory Module (A1)

Local persistent memory for the Roamin agent. Stores and retrieves data across sessions using SQLite and ChromaDB.

## Architecture

- `memory_store.py` — SQLite CRUD for 5 tables
- `memory_search.py` — ChromaDB semantic search
- `memory_manager.py` — Unified interface
- `__init__.py` — Public exports

## Tables

| Table | Purpose |
|-------|---------|
| conversation_history | Full chat logs per session |
| observations | Screen observations and descriptions |
| actions_taken | Actions Roamin performed + outcomes |
| user_patterns | Learned recurring behaviours |
| named_facts | User-provided facts (email, name, etc.) |

## Usage
```python
from agent.core.memory import MemoryManager

m = MemoryManager()

# Store a fact
m.write_to_memory("named_fact", {"fact_name": "email", "value": "user@example.com"})

# Recall it
m.recall_fact("email")

# Store a conversation
m.write_to_memory("conversation", {
    "session_id": "sess1",
    "model_used": "qwen3:8b",
    "content": "User asked about memory module"
})

# Get recent conversations
m.get_recent_conversations(limit=10)

# Semantic search
m.search_memory("what did we work on yesterday")
```

## Files

- DB: `agent/core/memory/roamin_memory.db`
- ChromaDB: `agent/core/memory/chroma_db/`
- Tests: `tests/test_memory_module.py`

## Running Tests
pytest tests/test_memory_module.py -v

All 18 tests should pass.
