import math
import re
from abc import ABC, abstractmethod
from app.schemas.knowledge import KnowledgeChunk

class BaseLexicalRetriever(ABC):
    """
    Interface for lexical search channels.
    """
    @abstractmethod
    def index_chunks(self, chunks: list[KnowledgeChunk]) -> None:
        pass

    @abstractmethod
    def search(self, query: str, limit: int, filter_metadata: dict | None = None) -> list[dict]:
        """
        Searches chunks using lexical similarity.
        Returns a list of dicts: {"id": chunk_id, "score": float, "payload": dict}
        """
        pass

class BM25LexicalRetriever(BaseLexicalRetriever):
    """
    Local, deterministic BM25 lexical scorer.
    """
    def __init__(self, k1: float = 1.2, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.chunks: list[KnowledgeChunk] = []
        self.doc_count = 0
        self.df: dict[str, int] = {}
        self.doc_tfs: list[dict[str, int]] = []
        self.doc_lengths: list[int] = []
        self.avg_doc_len = 0.0

    def index_chunks(self, chunks: list[KnowledgeChunk]) -> None:
        self.chunks = list(chunks)
        self.doc_count = len(chunks)
        self.df = {}
        self.doc_tfs = []
        self.doc_lengths = []
        
        total_len = 0
        for chunk in chunks:
            # Combine content and heading for text indexing
            text = f"{chunk.heading} {chunk.content}".lower()
            words = re.findall(r"\w+", text)
            length = len(words)
            total_len += length
            self.doc_lengths.append(length)
            
            tf = {}
            for w in words:
                tf[w] = tf.get(w, 0) + 1
            self.doc_tfs.append(tf)
            
            # Record document frequency for terms
            for w in set(words):
                self.df[w] = self.df.get(w, 0) + 1
                
        self.avg_doc_len = total_len / self.doc_count if self.doc_count > 0 else 0.0

    def search(self, query: str, limit: int, filter_metadata: dict | None = None) -> list[dict]:
        query_words = re.findall(r"\w+", query.lower())
        if not query_words or not self.chunks:
            return []

        # Filter indices based on metadata
        valid_indices = []
        for idx, chunk in enumerate(self.chunks):
            if filter_metadata:
                match = True
                for k, v in filter_metadata.items():
                    chunk_val = chunk.metadata.get(k)
                    if isinstance(v, list):
                        if isinstance(chunk_val, list):
                            if not set(v).intersection(set(chunk_val)):
                                match = False
                        else:
                            if chunk_val not in v:
                                match = False
                    else:
                        if isinstance(chunk_val, list):
                            if v not in chunk_val:
                                match = False
                        else:
                            if chunk_val != v:
                                match = False
                if not match:
                    continue
            valid_indices.append(idx)

        # Score matching documents using BM25
        scored = []
        for idx in valid_indices:
            chunk = self.chunks[idx]
            tf = self.doc_tfs[idx]
            doc_len = self.doc_lengths[idx]
            
            score = 0.0
            for w in query_words:
                if w not in self.df:
                    continue
                # Classic BM25 IDF
                idf = math.log((self.doc_count - self.df[w] + 0.5) / (self.df[w] + 0.5) + 1.0)
                
                # Term Frequency component
                tf_val = tf.get(w, 0)
                denom = tf_val + self.k1 * (1.0 - self.b + self.b * (doc_len / self.avg_doc_len if self.avg_doc_len > 0 else 1.0))
                bm25_tf = (tf_val * (self.k1 + 1.0)) / denom if denom > 0 else 0.0
                score += idf * bm25_tf

            if score > 0.0:
                # Add payload details compatible with Qdrant adapter schemas
                payload = dict(chunk.metadata)
                payload["content"] = chunk.content
                payload["heading"] = chunk.heading
                payload["document_id"] = chunk.document_id
                
                scored.append({
                    "id": chunk.chunk_id,
                    "score": round(score, 4),
                    "payload": payload
                })

        # Sort descending by score
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:limit]
