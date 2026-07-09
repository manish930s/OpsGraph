import logging
from app.schemas.evidence import Evidence, EvidenceProvenance, EvidenceRetrievalMetadata
from app.schemas.common import TimeWindow
from app.common.enums import SourceType
from app.services.evidence.identity import generate_evidence_id

logger = logging.getLogger("opsgraph.evidence.normalizer")

class EvidenceNormalizer:
    """
    Normalizes diverse tool outputs into canonical validated Evidence objects.
    """
    def __init__(self, incident_id: str, scenario_id: str):
        self.incident_id = incident_id
        self.scenario_id = scenario_id
        self._seq = 1

    def _next_id(self, source_type: SourceType) -> str:
        eid = generate_evidence_id(source_type, self.scenario_id, self._seq)
        self._seq += 1
        return eid

    def normalize_incident(self, incident_id: str, title: str, description: str, reported_services: list[str], reported_symptoms: list[str], reported_at: str, investigation_window: dict) -> Evidence:
        """
        Converts the active incident metadata context into a base Evidence object.
        """
        eid = self._next_id(SourceType.HISTORICAL_INCIDENT)
        logger.info(f"Normalizing incident context into evidence: {eid}")
        
        # Primary service selection
        service = reported_services[0] if reported_services else "system"
        observation = f"Reported incident: '{title}'. Description: '{description}'. Symptoms: {reported_symptoms}"
        
        return Evidence(
            schema_version="1.0",
            evidence_id=eid,
            incident_id=self.incident_id,
            scenario_id=self.scenario_id,
            source_type=SourceType.HISTORICAL_INCIDENT,
            source_name="incident_summary_lookup",
            service=service,
            time_window=TimeWindow(
                start=investigation_window.get("start", reported_at),
                end=investigation_window.get("end", reported_at)
            ),
            observation=observation,
            source_record_ids=[incident_id],
            provenance=EvidenceProvenance(
                dataset="incident",
                record_reference=incident_id,
                query_reference=f"incident_id={incident_id}"
            ),
            retrieval=EvidenceRetrievalMetadata(
                tool_name="incident_summary_lookup",
                relevance_score=1.0
            )
        )

    def normalize_logs(self, log_records: list) -> list[Evidence]:
        """
        Converts a list of LogRecord schemas into normalized Evidence list.
        """
        evidences = []
        for r in log_records:
            eid = self._next_id(SourceType.LOG)
            logger.info(f"Normalizing log record into evidence: {eid}")
            
            # Setup TimeWindow for single timestamp point
            tw = TimeWindow(start=r.timestamp, end=r.timestamp)
            
            ev = Evidence(
                schema_version="1.0",
                evidence_id=eid,
                incident_id=self.incident_id,
                scenario_id=self.scenario_id,
                source_type=SourceType.LOG,
                source_name="log_pattern_search",
                service=r.service,
                time_window=tw,
                observation=r.message,
                source_record_ids=[r.log_id],
                provenance=EvidenceProvenance(
                    dataset="logs",
                    record_reference=r.log_id,
                    query_reference=f"log_id={r.log_id}"
                ),
                retrieval=EvidenceRetrievalMetadata(
                    tool_name="log_pattern_search",
                    relevance_score=1.0
                )
            )
            evidences.append(ev)
        return evidences

    def normalize_metrics(self, metric_points: list, metric_name: str) -> list[Evidence]:
        """
        Converts a list of MetricPoint schemas into normalized Evidence list.
        """
        evidences = []
        for p in metric_points:
            eid = self._next_id(SourceType.METRIC)
            logger.info(f"Normalizing metric point into evidence: {eid}")
            
            tw = TimeWindow(start=p.timestamp, end=p.timestamp)
            obs = f"Metric '{metric_name}' value: {p.value} {p.unit}"
            
            ev = Evidence(
                schema_version="1.0",
                evidence_id=eid,
                incident_id=self.incident_id,
                scenario_id=self.scenario_id,
                source_type=SourceType.METRIC,
                source_name="metric_window_analysis",
                service=p.service,
                time_window=tw,
                observation=obs,
                source_record_ids=[p.metric_id],
                provenance=EvidenceProvenance(
                    dataset="metrics",
                    record_reference=p.metric_id,
                    query_reference=f"metric_id={p.metric_id}"
                ),
                retrieval=EvidenceRetrievalMetadata(
                    tool_name="metric_window_analysis",
                    relevance_score=1.0
                )
            )
            evidences.append(ev)
        return evidences

    def normalize_traces(self, spans: list, trace_id: str) -> list[Evidence]:
        """
        Converts TraceSpans into Trace Evidence.
        """
        evidences = []
        for s in spans:
            eid = self._next_id(SourceType.TRACE)
            logger.info(f"Normalizing trace span into evidence: {eid}")
            
            tw = TimeWindow(start=s.timestamp, end=s.timestamp)
            obs = f"Span {s.span_id} ({s.operation}) duration: {s.duration_ms}ms, status: {s.status}"
            
            ev = Evidence(
                schema_version="1.0",
                evidence_id=eid,
                incident_id=self.incident_id,
                scenario_id=self.scenario_id,
                source_type=SourceType.TRACE,
                source_name="trace_dependency_analysis",
                service=s.service,
                time_window=tw,
                observation=obs,
                source_record_ids=[s.span_id],
                provenance=EvidenceProvenance(
                    dataset="traces",
                    record_reference=s.span_id,
                    query_reference=f"span_id={s.span_id}&trace_id={trace_id}"
                ),
                retrieval=EvidenceRetrievalMetadata(
                    tool_name="trace_dependency_analysis",
                    relevance_score=1.0
                )
            )
            evidences.append(ev)
        return evidences

    def normalize_deployments(self, deployment_events: list) -> list[Evidence]:
        """
        Converts DeploymentEvents into Deployment Evidence.
        """
        evidences = []
        for d in deployment_events:
            eid = self._next_id(SourceType.DEPLOYMENT)
            logger.info(f"Normalizing deployment event into evidence: {eid}")
            
            tw = TimeWindow(start=d.timestamp, end=d.timestamp)
            obs = f"Deployment of service '{d.service}' to version {d.version_to}: {d.change_summary}"
            
            ev = Evidence(
                schema_version="1.0",
                evidence_id=eid,
                incident_id=self.incident_id,
                scenario_id=self.scenario_id,
                source_type=SourceType.DEPLOYMENT,
                source_name="deployment_event_search",
                service=d.service,
                time_window=tw,
                observation=obs,
                source_record_ids=[d.event_id],
                provenance=EvidenceProvenance(
                    dataset="deployments",
                    record_reference=d.event_id,
                    query_reference=f"event_id={d.event_id}"
                ),
                retrieval=EvidenceRetrievalMetadata(
                    tool_name="deployment_event_search",
                    relevance_score=1.0
                )
            )
            evidences.append(ev)
        return evidences

    def normalize_topology(self, service_id: str, direction: str, connected_services: list[str]) -> Evidence:
        """
        Converts service dependency relationships into Topology Evidence.
        """
        eid = self._next_id(SourceType.TOPOLOGY)
        logger.info(f"Normalizing service topology relationship into evidence: {eid}")
        
        obs = f"Topology mapping for '{service_id}' ({direction}) connected to services: {connected_services}"
        
        return Evidence(
            schema_version="1.0",
            evidence_id=eid,
            incident_id=self.incident_id,
            scenario_id=self.scenario_id,
            source_type=SourceType.TOPOLOGY,
            source_name="service_topology_lookup",
            service=service_id,
            time_window=None,
            observation=obs,
            source_record_ids=[service_id],
            provenance=EvidenceProvenance(
                dataset="topology",
                record_reference=service_id,
                query_reference=f"service_id={service_id}&direction={direction}"
            ),
            retrieval=EvidenceRetrievalMetadata(
                tool_name="service_topology_lookup",
                relevance_score=1.0
            )
        )
