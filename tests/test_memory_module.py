"""
tests/test_memory_module.py
Automated tests for A1 persistent memory module.
Run: pytest tests/test_memory_module.py -v
"""

import chromadb
import pytest

from agent.core.memory.memory_manager import MemoryManager
from agent.core.memory.memory_search import ChromaMemorySearch
from agent.core.memory.memory_store import MemoryStore


class EphemeralChromaMemorySearch:
    """Ephemeral ChromaDB search class for testing, matching interface of ChromaMemorySearch."""

    def __init__(self):
        self.client = chromadb.EphemeralClient()
        self.collection = self.client.get_or_create_collection(name="roamin_memory")
        self._doc_counter = 0

    def index_data(self, texts: list[str], metadatas: list[dict] | None = None):
        if metadatas is None:
            metadatas = [{"index": i} for i in range(len(texts))]
        ids = [f"doc_{self._doc_counter + i}" for i in range(len(texts))]
        self._doc_counter += len(texts)
        self.collection.add(documents=texts, metadatas=metadatas, ids=ids)

    def search(self, query_text: str, n_results: int = 3) -> dict:
        results = self.collection.query(query_texts=[query_text], n_results=n_results)
        return {
            "documents": results["documents"][0] if results["documents"] else [],
            "metadatas": results["metadatas"][0] if results["metadatas"] else [],
        }


@pytest.fixture
def tmp_store(tmp_path):
    return MemoryStore(db_path=str(tmp_path / "test.db"))


@pytest.fixture
def tmp_manager(tmp_path):
    store = MemoryStore(db_path=str(tmp_path / "test.db"))
    search = EphemeralChromaMemorySearch()
    mgr = MemoryManager.__new__(MemoryManager)
    mgr.store = store
    mgr.search = search
    return mgr


class TestMemoryStore:
    def test_add_and_get_conversation(self, tmp_store):
        row_id = tmp_store.add_conversation_history("sess1", "qwen3", "hello")
        assert row_id == 1
        rows = tmp_store.get_conversation_history()
        assert len(rows) == 1
        assert rows[0]["session_id"] == "sess1"

    def test_filter_by_session(self, tmp_store):
        tmp_store.add_conversation_history("sess1", "qwen3", "msg1")
        tmp_store.add_conversation_history("sess2", "qwen3", "msg2")
        tmp_store.add_conversation_history("sess1", "qwen3", "msg3")
        rows = tmp_store.get_conversation_history(session_id="sess1")
        assert len(rows) == 2

    def test_add_and_recall_named_fact(self, tmp_store):
        tmp_store.add_named_fact("email", "user@example.com")
        result = tmp_store.get_named_fact("email")
        assert result is not None
        assert result["value"] == "user@example.com"

    def test_missing_fact_returns_none(self, tmp_store):
        assert tmp_store.get_named_fact("nonexistent") is None

    def test_add_observation(self, tmp_store):
        row_id = tmp_store.add_observation("User opened VS Code")
        assert row_id == 1
        rows = tmp_store.get_observations()
        assert rows[0]["description"] == "User opened VS Code"

    def test_add_action_taken(self, tmp_store):
        row_id = tmp_store.add_action_taken("Ran git status", "success", "auto")
        assert row_id == 1
        rows = tmp_store.get_actions_taken()
        assert rows[0]["outcome"] == "success"

    def test_add_user_pattern(self, tmp_store):
        row_id = tmp_store.add_user_pattern("morning_routine", "Opens email first")
        assert row_id == 1
        rows = tmp_store.get_user_patterns()
        assert rows[0]["pattern_name"] == "morning_routine"

    def test_update_named_fact(self, tmp_store):
        tmp_store.add_named_fact("city", "Houston")
        fact = tmp_store.get_named_fact("city")
        updated = tmp_store.update_named_fact(fact["id"], "Dallas")
        assert updated is True
        assert tmp_store.get_named_fact("city")["value"] == "Dallas"

    def test_delete_named_fact(self, tmp_store):
        tmp_store.add_named_fact("temp", "delete_me")
        fact = tmp_store.get_named_fact("temp")
        deleted = tmp_store.delete_named_fact(fact["id"])
        assert deleted is True
        assert tmp_store.get_named_fact("temp") is None

    def test_multiple_conversations_ordering(self, tmp_store):
        for i in range(5):
            tmp_store.add_conversation_history("sess1", "qwen3", f"message {i}")
        rows = tmp_store.get_conversation_history()
        assert len(rows) == 5


class TestMemoryManager:
    def test_write_and_recall_fact(self, tmp_manager):
        tmp_manager.write_to_memory("named_fact", {"fact_name": "name", "value": "Asherre"})
        result = tmp_manager.recall_fact("name")
        assert result["value"] == "Asherre"

    def test_write_conversation(self, tmp_manager):
        tmp_manager.write_to_memory("conversation", {"session_id": "s1", "model_used": "qwen3", "content": "test"})
        rows = tmp_manager.get_recent_conversations(limit=5)
        assert len(rows) >= 1

    def test_write_observation(self, tmp_manager):
        tmp_manager.write_to_memory("observation", {"description": "Screen shows Gmail"})
        rows = tmp_manager.store.get_observations()
        assert rows[0]["description"] == "Screen shows Gmail"

    def test_write_action(self, tmp_manager):
        tmp_manager.write_to_memory(
            "action", {"action_description": "Clicked send", "outcome": "sent", "approval_status": "auto"}
        )
        rows = tmp_manager.store.get_actions_taken()
        assert rows[0]["approval_status"] == "auto"

    def test_invalid_type_raises(self, tmp_manager):
        with pytest.raises(ValueError):
            tmp_manager.write_to_memory("invalid_type", {})

    def test_get_recent_conversations_limit(self, tmp_manager):
        for i in range(15):
            tmp_manager.write_to_memory(
                "conversation", {"session_id": "s1", "model_used": "qwen3", "content": f"msg {i}"}
            )
        rows = tmp_manager.get_recent_conversations(limit=5)
        assert len(rows) == 5


@pytest.fixture
def chroma_search(tmp_path):
    return ChromaMemorySearch(db_path=str(tmp_path / "chroma_test"))


class TestChromaSearch:
    def test_index_and_search(self, chroma_search):
        chroma_search.index_data(
            ["Roamin is an AI agent", "The user works on os_agent daily"], [{"source": "test"}, {"source": "test"}]
        )
        results = chroma_search.search("AI agent")
        assert len(results["documents"]) > 0

    def test_empty_search_returns_structure(self, chroma_search):
        results = chroma_search.search("anything")
        assert "documents" in results
        assert "metadatas" in results

    def test_doc_counter_no_collision_on_second_index(self, chroma_search):
        """index_data() called twice on same instance must not raise IDAlreadyExistsError (#104)."""
        chroma_search.index_data(["first batch"], [{"source": "test"}])
        # Second call reuses the same instance — _doc_counter must continue from collection.count()
        chroma_search.index_data(["second batch"], [{"source": "test"}])
        results = chroma_search.search("batch")
        assert len(results["documents"]) > 0
