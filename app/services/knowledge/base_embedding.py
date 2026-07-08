from abc import ABC, abstractmethod
import hashlib
import numpy as np

class BaseEmbeddingProvider(ABC):
    """
    Interface for interchangeable embedding models.
    """
    @abstractmethod
    def get_embedding(self, text: str) -> list[float]:
        pass

    @abstractmethod
    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        pass

class MockEmbeddingProvider(BaseEmbeddingProvider):
    """
    Local offline embedding generator that hashes content to yield
    deterministic, normalized mock vectors.
    """
    def __init__(self, dimension: int = 3072):
        self.dimension = dimension

    def get_embedding(self, text: str) -> list[float]:
        hasher = hashlib.sha256()
        hasher.update(text.encode("utf-8"))
        seed = int(hasher.hexdigest(), 16) % (2**32)
        
        state = np.random.RandomState(seed)
        vec = state.normal(0.0, 1.0, self.dimension)
        
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()

    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        return [self.get_embedding(t) for t in texts]

class SentenceTransformerEmbeddingProvider(BaseEmbeddingProvider):
    """
    Real local embedding provider using the sentence-transformers library.
    Generates normalized L2 unit vectors.
    """
    def __init__(self, model_name: str = "all-MiniLM-L6-v2", device: str = "cpu"):
        self.model_name = model_name
        self.device = device
        self._model = None
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(model_name, device=device)
        except Exception as e:
            raise RuntimeError(
                f"Failed to initialize SentenceTransformer model '{model_name}' on device '{device}': {e}"
            ) from e

    def get_embedding(self, text: str) -> list[float]:
        if not self._model:
            raise RuntimeError("SentenceTransformer model is not initialized.")
        vector = self._model.encode(text, convert_to_numpy=True)
        
        # Deterministic L2 Normalization
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm
        return vector.tolist()

    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        if not self._model:
            raise RuntimeError("SentenceTransformer model is not initialized.")
        vectors = self._model.encode(texts, convert_to_numpy=True)
        results = []
        for vec in vectors:
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            results.append(vec.tolist())
        return results
