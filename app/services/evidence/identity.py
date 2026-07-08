import hashlib
from app.common.enums import SourceType

def generate_evidence_id(source_type: SourceType, scenario_id: str, seq_num: int) -> str:
    """
    Generate a deterministic evidence ID matching the schema validation format:
    <SOURCE_TYPE_UPPER>-EV-<SCENARIO_ID>-<SEQ_NUM>
    """
    prefix = source_type.value.upper()
    if prefix == "HISTORICAL_INCIDENT":
        prefix = "INCIDENT"
    return f"{prefix}-EV-{scenario_id}-{seq_num:04d}"

def compute_evidence_hash(observation: str, service: str, timestamp_str: str | None) -> str:
    """
    Computes MD5 hash of evidence content for duplicate detection.
    """
    hasher = hashlib.md5()
    t_str = timestamp_str if timestamp_str else "no-timestamp"
    payload = f"{observation}|{service}|{t_str}"
    hasher.update(payload.encode("utf-8"))
    return hasher.hexdigest()
