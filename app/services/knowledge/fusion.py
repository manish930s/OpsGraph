import logging

logger = logging.getLogger("opsgraph.knowledge.fusion")

class ReciprocalRankFusion:
    """
    Combines dense and lexical candidates using Reciprocal Rank Fusion (RRF).
    Preserves retrieval channel provenance, scores, and rank placements.
    """
    def __init__(self, k: int = 60):
        self.k = k

    def fuse(self, dense_results: list[dict], lexical_results: list[dict]) -> list[dict]:
        """
        Merges and deduplicates candidate lists using standard RRF score logic.
        """
        # Map item IDs to (1-indexed rank, score, payload)
        dense_map = {
            item["id"]: (idx + 1, item["score"], item["payload"])
            for idx, item in enumerate(dense_results)
        }
        lexical_map = {
            item["id"]: (idx + 1, item["score"], item["payload"])
            for idx, item in enumerate(lexical_results)
        }

        all_ids = set(dense_map.keys()).union(set(lexical_map.keys()))
        fused = []

        for c_id in all_ids:
            rrf_score = 0.0
            channels = []

            dense_rank, dense_score, payload = None, None, None
            if c_id in dense_map:
                dense_rank, dense_score, payload = dense_map[c_id]
                rrf_score += 1.0 / (self.k + dense_rank)
                channels.append("dense")

            lexical_rank, lexical_score, lex_payload = None, None, None
            if c_id in lexical_map:
                lexical_rank, lexical_score, lex_payload = lexical_map[c_id]
                rrf_score += 1.0 / (self.k + lexical_rank)
                channels.append("lexical")
                if payload is None:
                    payload = lex_payload

            # Structure explicit retrieval channel tracing metadata
            provenance = {
                "chunk_id": c_id,
                "dense_rank": dense_rank,
                "dense_score": dense_score,
                "lexical_rank": lexical_rank,
                "lexical_score": lexical_score,
                "fusion_score": round(rrf_score, 6),
                "retrieval_channels": channels
            }

            # Embed provenance inside payload so FlashRank reranking preserves it
            enriched_payload = dict(payload) if payload else {}
            enriched_payload["_provenance"] = provenance

            fused.append({
                "id": c_id,
                "score": round(rrf_score, 6),
                "payload": enriched_payload
            })

        # Sort descending by RRF score
        fused.sort(key=lambda x: x["score"], reverse=True)
        logger.info(f"Fused {len(dense_results)} dense and {len(lexical_results)} lexical candidates into {len(fused)} items.")
        return fused
