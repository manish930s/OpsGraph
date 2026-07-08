import logging
from app.schemas.evidence import Evidence
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
            # Use source records or cryptographic hash of message/service/timestamp
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
                # Merge duplicate info into match_ev
                logger.info(f"Merging duplicate evidence item: {ev.evidence_id} into {match_ev.evidence_id}")
                
                # Merge source record IDs
                for r_id in ev.source_record_ids:
                    if r_id not in match_ev.source_record_ids:
                        match_ev.source_record_ids.append(r_id)

                # Merge provenance references
                if ev.provenance.record_reference:
                    refs = match_ev.provenance.record_reference.split(",")
                    if ev.provenance.record_reference not in refs:
                        match_ev.provenance.record_reference += f",{ev.provenance.record_reference}"

                if ev.provenance.query_reference:
                    queries = match_ev.provenance.query_reference.split(" | ")
                    if ev.provenance.query_reference not in queries:
                        match_ev.provenance.query_reference += f" | {ev.provenance.query_reference}"

            else:
                # Store new evidence
                seen_records[record_keys[0]] = ev
                unique_evidences.append(ev)
                for key in record_keys:
                    seen_records[key] = ev

        logger.info(f"Deduplication completed. Original count: {len(evidences)}, unique count: {len(unique_evidences)}")
        return unique_evidences
