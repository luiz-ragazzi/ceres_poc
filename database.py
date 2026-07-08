"""
ChromaDB client and database operations.
"""

import chromadb
from chromadb.config import Settings
from typing import List, Dict, Any
from config import CHROMA_PATH, COLLECTION_NAME


class DatabaseManager:
    """Singleton manager for ChromaDB client and collection."""
    
    _instance = None
    _client = None
    _collection = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            print("Connecting to ChromaDB...")
            cls._client = chromadb.PersistentClient(
                path=CHROMA_PATH,
                settings=Settings(anonymized_telemetry=False),
            )
            cls._collection = cls._client.get_or_create_collection(
                name=COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
            print("ChromaDB connected.")
        return cls._instance
    
    def add_documents(
        self,
        ids: List[str],
        embeddings: List[List[float]],
        documents: List[str],
        metadatas: List[Dict[str, Any]],
    ) -> None:
        """Add documents to the collection."""
        self._collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
    
    def query(
        self,
        query_embeddings: List[List[float]],
        n_results: int,
    ) -> Dict[str, Any]:
        """Query the collection with embeddings."""
        return self._collection.query(
            query_embeddings=query_embeddings,
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )
    
    def delete_by_doc_id(self, doc_id: str) -> int:
        """Delete all chunks belonging to a document."""
        results = self._collection.get(where={"doc_id": doc_id}, include=["metadatas"])
        ids_to_delete = results["ids"]
        if ids_to_delete:
            self._collection.delete(ids=ids_to_delete)
        return len(ids_to_delete)
    
    def count(self) -> int:
        """Get total number of chunks in the collection."""
        return self._collection.count()


def get_database() -> DatabaseManager:
    """Get or create the database singleton."""
    return DatabaseManager()
