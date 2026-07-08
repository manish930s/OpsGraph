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
        
        # Generate pseudorandom floats from seed
        state = np.random.RandomState(seed)
        vec = state.normal(0.0, 1.0, self.dimension)
        
        # L2 Normalize
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()

    def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        return [self.get_embedding(t) for t in texts]
