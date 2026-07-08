from pathlib import Path
import json
from app.schemas.incident import IncidentRecord
from app.schemas.evidence import Evidence
from app.schemas.rca import GoldenCase
from app.schemas.telemetry import LogRecord, MetricPoint, TraceSpan, DeploymentEvent, ServiceTopology
from app.services.evidence.validator import validate_incident_record, validate_evidence_list
from app.common.exceptions import IncidentNotFoundError

class ScenarioRepository:
    """
    Service repository for loading deterministically generated incident scenario files.
    """
    def __init__(self, scenario_dir: Path):
        self.base = Path(scenario_dir)
        if not self.base.exists():
            raise FileNotFoundError(f"Scenario directory does not exist: {scenario_dir}")

    def load_incident(self) -> IncidentRecord:
        p = self.base / "incident.json"
        if not p.exists():
            raise IncidentNotFoundError(f"incident.json missing from scenario: {self.base}")
        record = IncidentRecord.model_validate_json(p.read_text(encoding="utf-8"))
        validate_incident_record(record)
        return record

    def load_evidence(self) -> list[Evidence]:
        p = self.base / "evidence.json"
        if not p.exists():
            return []
        items = json.loads(p.read_text(encoding="utf-8"))
        evidence_list = [Evidence.model_validate(x) for x in items]
        incident = self.load_incident()
        validate_evidence_list(evidence_list, incident.incident_id, incident.scenario_id)
        return evidence_list

    def load_golden_case(self) -> GoldenCase:
        # Note: golden case is for evaluations only and should not be accessed by runtime nodes
        p = self.base / "golden.json"
        if not p.exists():
            raise FileNotFoundError(f"golden.json missing from scenario: {self.base}")
        return GoldenCase.model_validate_json(p.read_text(encoding="utf-8"))

    def load_logs(self) -> list[LogRecord]:
        p = self.base / "logs.jsonl"
        if not p.exists():
            return []
        records = []
        with p.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    records.append(LogRecord.model_validate_json(line))
        return records

    def load_metrics(self) -> list[MetricPoint]:
        p = self.base / "metrics.jsonl"
        if not p.exists():
            return []
        records = []
        with p.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    records.append(MetricPoint.model_validate_json(line))
        return records

    def load_traces(self) -> list[TraceSpan]:
        p = self.base / "traces.jsonl"
        if not p.exists():
            return []
        records = []
        with p.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    records.append(TraceSpan.model_validate_json(line))
        return records

    def load_deployments(self) -> list[DeploymentEvent]:
        p = self.base / "deployments.json"
        if not p.exists():
            return []
        items = json.loads(p.read_text(encoding="utf-8"))
        return [DeploymentEvent.model_validate(x) for x in items]

    def load_topology(self) -> ServiceTopology:
        p = self.base.parent / "topology.json"
        if not p.exists():
            from app.config import settings
            p = settings.GENERATED_DATA_DIR / "topology.json"
        if not p.exists():
            raise FileNotFoundError(f"topology.json missing: {p}")
        return ServiceTopology.model_validate_json(p.read_text(encoding="utf-8"))

