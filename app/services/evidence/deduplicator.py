import logging
from app.schemas.evidence import Evidence, EvidenceProvenance
from app.services.evidence.identity import compute_evidence_hash

logger = logging.getLogger("opsgraph.evidence.deduplicator")

class EvidenceDeduplicator:
    """
    De-duplicates compiled evidence items based on source record IDs,
    hashing observation content, and merging query parameters.
    """
    def deduplicate(self, evidences: list[Evidence]) -> list[Evidence]:
        """
        Groups and merges matching evidence records, combining metadata and sources.
        """
        seen_records: dict[str, Evidence] = {}
        unique_evidences: list[Evidence] = []

        for ev in evidences:
            # Generate identifier key for identical data
            record_keys = []
            for r_id in ev.source_record_ids:
                record_keys.append(f"{ev.source_type.value}|{r_id}")

            # Fallback to content hashing if record references are empty
            if not record_keys:
                t_val = ev.time_window.start if ev.time_window else None
                h = compute_evidence_hash(ev.observation, ev.service, t_val)
                record_keys = [f"hash|{h}"]

            # Check if any key has been registered
            duplicate_found = False
            match_ev = None
            for key in record_keys:
                if key in seen_records:
                    duplicate_found = True
                    match_ev = seen_records[key]
                    break

            if duplicate_found and match_ev:
                logger.info(f"Merging duplicate evidence item: {ev.evidence_id} into {match_ev.evidence_id}")
                
                # Merge source record IDs
                new_source_ids = list(match_ev.source_record_ids)
                for r_id in ev.source_record_ids:
                    if r_id not in new_source_ids:
                        new_source_ids.append(r_id)

                # Merge provenance references
                new_rec_ref = match_ev.provenance.record_reference
                if ev.provenance.record_reference:
                    if not new_rec_ref:
                        new_rec_ref = ev.provenance.record_reference
                    else:
                        refs = new_rec_ref.split(",")
                        if ev.provenance.record_reference not in refs:
                            new_rec_ref += f",{ev.provenance.record_reference}"

                new_query_ref = match_ev.provenance.query_reference
                if ev.provenance.query_reference:
                    if not new_query_ref:
                        new_query_ref = ev.provenance.query_reference
                    else:
                        queries = new_query_ref.split(" | ")
                        if ev.provenance.query_reference not in queries:
                            new_query_ref += f" | {ev.provenance.query_reference}"

                # Recreate frozen sub-models and parent models
                new_prov = EvidenceProvenance(
                    dataset=match_ev.provenance.dataset,
                    generator_version=match_ev.provenance.generator_version,
                    record_reference=new_rec_ref,
                    query_reference=new_query_ref
                )

                merged_ev = match_ev.model_copy(update={
                    "source_record_ids": new_source_ids,
                    "provenance": new_prov
                })

                # Update collections with the new merged_ev
                # Replace in unique_evidences list
                for idx, item in enumerate(unique_evidences):
                    if item.evidence_id == match_ev.evidence_id:
                        unique_evidences[idx] = merged_ev
                        break
                
                # Update seen records lookup map
                for key in record_keys:
                    seen_records[key] = merged_ev
                seen_records[f"{match_ev.source_type.value}|{match_ev.source_record_ids[0]}"] = merged_ev

            else:
                # Store new evidence
                seen_records[record_keys[0]] = ev
                unique_evidences.append(ev)
                for key in record_keys:
                    seen_records[key] = ev

        logger.info(f"Deduplication completed. Original count: {len(evidences)}, unique count: {len(unique_evidences)}")
        return unique_evidences
