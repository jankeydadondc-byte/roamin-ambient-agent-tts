import logging
from pathlib import Path

import chromadb

logger = logging.getLogger(__name__)

_DEFAULT_CHROMA = str(Path(__file__).parent / "chroma_db")


class ChromaMemorySearch:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or _DEFAULT_CHROMA
        # Ensure directory exists before initializing PersistentClient
        Path(self.db_path).mkdir(parents=True, exist_ok=True)
        try:
            # Production path: allow_reset=False prevents accidental client.reset() (#76)
            self.client = chromadb.PersistentClient(
                path=self.db_path,
                settings=chromadb.Settings(allow_reset=False),
            )
        except Exception:
            # Fallback: older chromadb — try settings kwarg first, then bare (#68)
            try:
                self.client = chromadb.PersistentClient(
                    path=self.db_path,
                    settings=chromadb.Settings(allow_reset=False),
                )
            except TypeError:
                # Very old chromadb: no settings kwarg — reset protection unavailable
                logger.warning(
                    "chromadb version does not support allow_reset=False — " "reset protection unavailable (#68)"
                )
                self.client = chromadb.PersistentClient(path=self.db_path)
        self.collection = self.client.get_or_create_collection(name="roamin_memory")
        # Seed counter from existing collection size so IDs never collide on
        # re-instantiation after the first session (#74)
        self._doc_counter = self.collection.count()

    def index_data(self, texts: list[str], metadatas: list[dict] | None = None):
        if metadatas is None:
            # Ensure each text has at least one metadata entry
            metadatas = [{"index": i} for i in range(len(texts))]

        # Generate unique IDs for each document
        ids = [f"doc_{self._doc_counter + i}" for i in range(len(texts))]
        self._doc_counter += len(texts)

        self.collection.add(documents=texts, metadatas=metadatas, ids=ids)

    def search(self, query_text: str, n_results: int = 3) -> dict:
        # Guard against empty collection — ChromaDB raises InvalidArgumentError
        # when n_results > collection.count() (#75)
        count = self.collection.count()
        if count == 0:
            return {"documents": [], "metadatas": [], "distances": []}
        n = min(n_results, count)
        results = self.collection.query(query_texts=[query_text], n_results=n)
        return {
            "documents": results["documents"][0] if results["documents"] else [],
            "metadatas": results["metadatas"][0] if results["metadatas"] else [],
        }
