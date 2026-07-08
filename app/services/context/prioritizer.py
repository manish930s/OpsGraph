from pydantic import BaseModel, Field
from app.schemas.context import ContextItem
from app.schemas.evidence import EvidenceBundle

class ContextPriorityPolicy(BaseModel):
    model_config = {"frozen": True}
    evidence_base_weight: float = Field(default=1.0)
    confidence_score_weight: float = Field(default=0.5)
    reliability_weight: float = Field(default=0.3)
    contradiction_penalty_factor: float = Field(default=0.2)
    
    knowledge_base_weight: float = Field(default=0.5)
    rerank_weight: float = Field(default=0.4)
    fusion_weight: float = Field(default=0.3)
    service_match_weight: float = Field(default=0.3)

class ContextPrioritizer:
    """
    Computes deterministic priority scores for each ContextItem
    based on the configured policy and bundle values.
    """
    def __init__(self, policy: ContextPriorityPolicy | None = None):
        self.policy = policy or ContextPriorityPolicy()

    def prioritize_items(self, items: list[ContextItem], evidence_bundle: EvidenceBundle) -> list[ContextItem]:
        prioritized = []
        covered_services = list(evidence_bundle.coverage_summary.keys()) if evidence_bundle else []

        for item in items:
            component_scores = {}
            penalties = {}
            reasons = []

            if item.source_kind == "evidence":
                # Evidence priority scoring
                base_score = self.policy.evidence_base_weight
                component_scores["evidence_base"] = base_score
                
                conf = evidence_bundle.confidence_summary
                conf_score = conf.score * self.policy.confidence_score_weight
                component_scores["confidence_score"] = conf_score
                
                reliability = conf.components.source_reliability * self.policy.reliability_weight
                component_scores["source_reliability"] = reliability
                
                penalty = conf.components.contradictions * self.policy.contradiction_penalty_factor
                penalties["contradictions_penalty"] = penalty

                total = base_score + conf_score + reliability - penalty
                total = round(max(total, 0.0), 4)

                reasons.append("Authoritative evidence observation weight")
                if conf_score > 0:
                    reasons.append(f"Confidence score contribution ({conf_score:.2f})")
                if reliability > 0:
                    reasons.append(f"Source reliability weight ({reliability:.2f})")
                if penalty > 0:
                    reasons.append(f"Contradiction penalty ({penalty:.2f})")

            else:
                # Knowledge priority scoring
                base_score = self.policy.knowledge_base_weight
                component_scores["knowledge_base"] = base_score

                rerank_score = item.metadata.get("rerank_score", 0.0)
                rerank_weighted = rerank_score * self.policy.rerank_weight
                component_scores["rerank_relevance"] = rerank_weighted

                fusion_score = item.metadata.get("fusion_score", 0.0)
                fusion_weighted = fusion_score * self.policy.fusion_weight
                component_scores["fusion_relevance"] = fusion_weighted

                service_match = 0.0
                if item.service and item.service in covered_services:
                    service_match = self.policy.service_match_weight
                    component_scores["service_match"] = service_match

                total = base_score + rerank_weighted + fusion_weighted + service_match
                total = round(max(total, 0.0), 4)

                reasons.append("Supporting operational knowledge base weight")
                if rerank_weighted > 0:
                    reasons.append(f"FlashRank rerank relevance ({rerank_weighted:.2f})")
                if fusion_weighted > 0:
                    reasons.append(f"RRF fusion relevance ({fusion_weighted:.2f})")
                if service_match > 0:
                    reasons.append(f"Affected service alignment ({service_match:.2f})")

            # Update item with priority score and breakdown details
            item_metadata = dict(item.metadata)
            item_metadata["priority_components"] = component_scores
            item_metadata["priority_penalties"] = penalties
            item_metadata["priority_reasons"] = reasons

            updated_item = item.model_copy(update={
                "priority_score": total,
                "metadata": item_metadata
            })
            prioritized.append(updated_item)

        # Stable tie-breaking sort: sort by priority_score descending, then source_id ascending
        prioritized.sort(key=lambda x: (-x.priority_score, x.source_id))
        return prioritized
