from abc import ABC, abstractmethod

class BaseVectorStore(ABC):
    """
    Abstract interface for interchangeable vector database adapters.
    """
    @abstractmethod
    def create_collection(self, collection_name: str, vector_size: int) -> None:
        pass

    @abstractmethod
    def delete_collection(self, collection_name: str) -> None:
        pass

    @abstractmethod
    def upsert(self, collection_name: str, points: list[dict]) -> None:
        """
        Upserts multiple document chunk points.
        Each point dict contains:
        - "id": str (chunk_id)
        - "vector": list[float]
        - "payload": dict (chunk metadata and content)
        """
        pass

    @abstractmethod
    def search(
        self,
        collection_name: str,
        vector: list[float],
        limit: int,
        filter_metadata: dict | None = None
    ) -> list[dict]:
        """
        Searches similarity vectors, applying metadata filters.
        Returns a list of point dictionaries with "id", "score", and "payload".
        """
        pass

    @abstractmethod
    def health_check(self) -> bool:
        pass
