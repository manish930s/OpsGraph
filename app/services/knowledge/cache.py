import logging
import hashlib

logger = logging.getLogger("opsgraph.knowledge.cache")

class KnowledgeCache:
    """
    Lightweight, thread-safe in-memory cache for storing generated embeddings
    and vector search results to minimize token overhead.
    """
    def __init__(self) -> None:
        self._embeddings: dict[str, list[float]] = {}
        self._retrievals: dict[str, list[dict]] = {}

    def _hash_key(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def get_embedding(self, text: str) -> list[float] | None:
        key = self._hash_key(text)
        val = self._embeddings.get(key)
        if val is not None:
            logger.info("Cache HIT: Embedding resolved.")
        else:
            logger.debug("Cache MISS: Embedding not found.")
        return val

    def set_embedding(self, text: str, vector: list[float]) -> None:
        key = self._hash_key(text)
        self._embeddings[key] = vector
        logger.debug("Cache set: Embedding saved.")

    def get_retrieval(self, query_key: str) -> list[dict] | None:
        key = self._hash_key(query_key)
        val = self._retrievals.get(key)
        if val is not None:
            logger.info("Cache HIT: Vector search results resolved.")
        else:
            logger.debug("Cache MISS: Vector search results not found.")
        return val

    def set_retrieval(self, query_key: str, results: list[dict]) -> None:
        key = self._hash_key(query_key)
        self._retrievals[key] = results
        logger.debug("Cache set: Search results saved.")

    def clear(self) -> None:
        self._embeddings.clear()
        self._retrievals.clear()
        logger.info("Knowledge cache cleared.")
