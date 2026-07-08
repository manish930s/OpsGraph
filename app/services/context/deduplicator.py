import hashlib
from app.schemas.context import ContextItem

class ContextDeduplicator:
    """
    Deduplicates candidate ContextItems based on stable identities
    and content hashes, merging scores and references.
    """
    @staticmethod
    def deduplicate(items: list[ContextItem]) -> tuple[list[ContextItem], int]:
        unique_items = []
        seen_keys = set()
        seen_contents = {}  # maps content_hash -> index in unique_items
        
        duplicates_removed = 0
        
        for item in items:
            # Normalize content for near-identical string deduplication
            clean_content = "".join(item.content.split()).lower()
            content_hash = hashlib.sha256(clean_content.encode("utf-8")).hexdigest()
            
            dedup_key = (item.source_kind, item.source_id)
            
            if dedup_key in seen_keys:
                duplicates_removed += 1
                # Find the existing index
                idx = next(
                    i for i, x in enumerate(unique_items)
                    if (x.source_kind == item.source_kind and x.source_id == item.source_id)
                )
                existing = unique_items[idx]
                
                # Merge scores and metadata
                new_priority = max(existing.priority_score, item.priority_score)
                new_metadata = dict(existing.metadata)
                for k in ["dense_score", "lexical_score", "fusion_score", "rerank_score"]:
                    if k in item.metadata:
                        new_metadata[k] = max(existing.metadata.get(k, 0.0), item.metadata[k])
                
                unique_items[idx] = existing.model_copy(update={
                    "priority_score": new_priority,
                    "metadata": new_metadata
                })
                continue

            if content_hash in seen_contents:
                duplicates_removed += 1
                idx = seen_contents[content_hash]
                existing = unique_items[idx]
                
                new_priority = max(existing.priority_score, item.priority_score)
                unique_items[idx] = existing.model_copy(update={
                    "priority_score": new_priority
                })
                continue
                
            seen_keys.add(dedup_key)
            seen_contents[content_hash] = len(unique_items)
            unique_items.append(item)
            
        return unique_items, duplicates_removed
