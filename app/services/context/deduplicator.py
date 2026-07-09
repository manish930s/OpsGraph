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

            # Check if this content hash has been seen on different source keys
            if content_hash in seen_contents:
                # Content-equivalent, different provenance (Tier 3)
                # Keep it as a separate item, but add metadata group tracking
                indices = seen_contents[content_hash]
                
                # Enrich new item metadata
                new_metadata = dict(item.metadata)
                new_metadata["content_equivalence_group"] = content_hash
                new_metadata["content_equivalent_to"] = [unique_items[i].source_id for i in indices]
                
                # Update metadata of all previously seen items in this group
                for idx in indices:
                    prev_item = unique_items[idx]
                    prev_metadata = dict(prev_item.metadata)
                    prev_equiv = prev_metadata.get("content_equivalent_to", [])
                    if item.source_id not in prev_equiv:
                        prev_equiv = list(prev_equiv) + [item.source_id]
                    prev_metadata["content_equivalent_to"] = prev_equiv
                    prev_metadata["content_equivalence_group"] = content_hash
                    unique_items[idx] = prev_item.model_copy(update={"metadata": prev_metadata})
                
                # Add this index to seen_contents list
                indices.append(len(unique_items))
                
                # Append item to unique_items
                unique_items.append(item.model_copy(update={"metadata": new_metadata}))
                seen_keys.add(dedup_key)
                continue
                
            seen_keys.add(dedup_key)
            seen_contents[content_hash] = [len(unique_items)]
            unique_items.append(item)
            
        return unique_items, duplicates_removed
