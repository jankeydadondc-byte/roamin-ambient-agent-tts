from .memory_search import ChromaMemorySearch
from .memory_store import MemoryStore


class MemoryManager:
    def __init__(self):
        self.store = MemoryStore()
        self.search = ChromaMemorySearch()

    def write_to_memory(self, data_type: str, data: dict) -> int:
        """
        Write data to the appropriate SQLite table based on data type.

        Args:
            data_type: One of 'conversation', 'observation', 'action',
                       'user_pattern', or 'named_fact'
            data: Dictionary containing required fields for the entity

        Returns:
            ID of newly inserted record
        """
        if data_type == "conversation":
            return self.store.add_conversation_history(
                session_id=data["session_id"], model_used=data["model_used"], content=data["content"]
            )
        elif data_type == "observation":
            return self.store.add_observation(
                description=data["description"], screenshot_path=data.get("screenshot_path")
            )
        elif data_type == "action":
            return self.store.add_action_taken(
                action_description=data["action_description"],
                outcome=data["outcome"],
                approval_status=data["approval_status"],
            )
        elif data_type == "user_pattern":
            return self.store.add_user_pattern(pattern_name=data["pattern_name"], description=data["description"])
        elif data_type == "named_fact":
            return self.store.add_named_fact(fact_name=data["fact_name"], value=data["value"])
        else:
            raise ValueError(f"Unknown data type: {data_type}")

    def search_memory(self, query: str) -> dict:
        """
        Search memory using ChromaDB semantic search.

        Args:
            query: Natural language query string

        Returns:
            Dictionary with 'documents' and 'metadatas' lists
        """
        return self.search.search(query)

    def recall_fact(self, fact_name: str):
        """
        Recall a specific named fact from SQLite.

        Args:
            fact_name: Name of the fact to retrieve

        Returns:
            Dictionary with fact record or None if not found
        """
        return self.store.get_named_fact(fact_name)

    def get_recent_conversations(self, session_id: str | None = None, limit: int = 20) -> list:
        """
        Retrieve recent conversation history for context loading.

        Args:
            session_id: Optional filter by session
            limit: Max number of entries to return (most recent first)

        Returns:
            List of conversation dicts sorted newest-first
        """
        rows = self.store.get_conversation_history(session_id=session_id)
        return rows[-limit:][::-1]
