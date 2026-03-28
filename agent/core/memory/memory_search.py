from pathlib import Path

import chromadb

_DEFAULT_CHROMA = str(Path(__file__).parent / "chroma_db")


class ChromaMemorySearch:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or _DEFAULT_CHROMA
        # Ensure directory exists before initializing PersistentClient
        Path(self.db_path).mkdir(parents=True, exist_ok=True)
        try:
            self.client = chromadb.PersistentClient(path=self.db_path)
        except Exception:
            self.client = chromadb.PersistentClient(path=self.db_path, settings=chromadb.Settings(allow_reset=True))
        self.collection = self.client.get_or_create_collection(name="roamin_memory")
        self._doc_counter = 0

    def index_data(self, texts: list[str], metadatas: list[dict] | None = None):
        if metadatas is None:
            # Ensure each text has at least one metadata entry
            metadatas = [{"index": i} for i in range(len(texts))]

        # Generate unique IDs for each document
        ids = [f"doc_{self._doc_counter + i}" for i in range(len(texts))]
        self._doc_counter += len(texts)

        self.collection.add(documents=texts, metadatas=metadatas, ids=ids)

    def search(self, query_text: str, n_results: int = 3) -> dict:
        results = self.collection.query(query_texts=[query_text], n_results=n_results)
        return {
            "documents": results["documents"][0] if results["documents"] else [],
            "metadatas": results["metadatas"][0] if results["metadatas"] else [],
        }
