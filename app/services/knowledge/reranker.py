import logging
import re
from app.schemas.knowledge import KnowledgeChunk

logger = logging.getLogger("opsgraph.knowledge.reranker")

class FlashRankReranker:
    """
    Reranks candidate chunks using FlashRank cross-encoder models.
    Provides a deterministic term-overlap fallback for offline tests and container environments.
    """
    def __init__(self):
        self.has_flashrank = False
        self._ranker = None
        try:
            # Check if flashrank package is imported
            import flashrank
            self.has_flashrank = True
        except ImportError:
            logger.info("FlashRank library not imported. Local word-overlap matching will be used.")

    def rerank(self, query: str, chunks: list[dict], limit: int = 5) -> list[tuple[float, dict]]:
        """
        Reranks a list of candidate chunk payloads.
        Each candidate is a dict containing {"id": str, "payload": dict, "score": float}
        Returns list of (rerank_score, candidate_dict) sorted descending.
        """
        if not chunks:
            return []

        # If flashrank library is present, attempt RAG cross-encoder rerank
        if self.has_flashrank:
            try:
                # Lazy load ranker model to prevent initialization blocking
                if self._ranker is None:
                    from flashrank import Ranker
                    # Use standard small model config
                    self._ranker = Ranker()

                passages = []
                for c in chunks:
                    passages.append({
                        "id": c["id"],
                        "text": c["payload"]["content"] if "payload" in c else c.get("content", ""),
                        "meta": c
                    })

                from flashrank import RerankRequest
                req = RerankRequest(query=query, passages=passages)
                results = self._ranker.rerank(req)

                reranked = []
                for r in results[:limit]:
                    reranked.append((float(r["score"]), r["meta"]))
                return reranked

            except Exception as e:
                logger.warning(f"FlashRank execution failed: {e}. Falling back to overlap reranking.")

        # Fallback: Deterministic word Jaccard overlap similarity
        query_words = set(re.findall(r"\w+", query.lower()))
        if not query_words:
            return [(0.0, c) for c in chunks[:limit]]

        scored = []
        for c in chunks:
            payload = c.get("payload", {})
            content = payload.get("content", "")
            heading = payload.get("heading", "")

            content_words = set(re.findall(r"\w+", content.lower()))
            intersection = query_words.intersection(content_words)
            union = query_words.union(content_words)
            
            jaccard = len(intersection) / len(union) if union else 0.0
            
            # Boost score if heading contains query terms
            heading_words = set(re.findall(r"\w+", heading.lower()))
            if query_words.intersection(heading_words):
                jaccard += 0.2

            scored.append((round(jaccard, 4), c))

        # Sort descending by score
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:limit]
