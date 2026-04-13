"""Stub implementation of chromadb for tests.

Provides the subset of the chromadb API used by production code so tests can
run without the real chromadb package being importable first.
"""

from typing import Any, Dict, List


class Settings:
    """Stub Settings — accepts and ignores all kwargs."""

    def __init__(self, **kwargs):
        pass


class Collection:
    def __init__(self):
        self.documents: List[str] = []
        self.metadatas: List[Dict[str, Any]] = []
        self.ids: List[str] = []

    def count(self) -> int:
        return len(self.ids)

    def add(self, documents: List[str], metadatas: List[Dict[str, Any]], ids: List[str]):
        self.documents.extend(documents)
        self.metadatas.extend(metadatas)
        self.ids.extend(ids)

    def query(self, query_texts: List[str], n_results: int = 3):
        n = min(n_results, len(self.documents))
        return {
            "documents": [self.documents[:n]],
            "metadatas": [self.metadatas[:n]],
            "distances": [[0.0] * n],
        }


class Client:
    def __init__(self, path: str | None = None, settings: Settings | None = None, **kwargs):
        self._collections: Dict[str, Collection] = {}

    def get_or_create_collection(self, name: str) -> Collection:
        if name not in self._collections:
            self._collections[name] = Collection()
        return self._collections[name]


# Aliases matching the real chromadb API surface used by production code
EphemeralClient = Client
PersistentClient = Client
