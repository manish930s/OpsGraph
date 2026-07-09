import hashlib

def generate_deterministic_id(scenario_id: str, incident_id: str, source_kind: str, source_id: str) -> str:
    """
    Generates a stable, reproducible context item ID.
    """
    raw_key = f"{scenario_id}:{incident_id}:{source_kind}:{source_id}"
    hasher = hashlib.sha256(raw_key.encode("utf-8"))
    return f"CTX-{hasher.hexdigest()[:16]}"
