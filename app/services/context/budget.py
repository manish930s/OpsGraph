from abc import ABC, abstractmethod
from pydantic import BaseModel, Field
from app.schemas.context import ContextItem

class BaseBudgetEstimator(ABC):
    """
    Abstract base class for predicting token/word/character costs of text.
    Allows easy plug-in replacement of tiktoken or custom LLM tokenizers.
    """
    @abstractmethod
    def estimate_cost(self, text: str) -> int:
        pass

class WordCountBudgetEstimator(BaseBudgetEstimator):
    """
    Simple word-count based budget estimator.
    """
    def estimate_cost(self, text: str) -> int:
        if not text:
            return 0
        return len(text.split())

class ContextBudgetPolicy(BaseModel):
    model_config = {"frozen": True}
    total_budget: int = Field(default=2000)      # total units (e.g. words)
    evidence_ratio: float = Field(default=0.5)   # 50% for evidence
    knowledge_ratio: float = Field(default=0.3)  # 30% for knowledge
    reserved_ratio: float = Field(default=0.2)   # 20% reserved overhead

class BudgetManager:
    """
    Deterministic budget manager allocating limits, tracking utilization,
    enforcing oversized exclusions, and performing bidirectional redistribution.
    """
    def __init__(self, policy: ContextBudgetPolicy | None = None, estimator: BaseBudgetEstimator | None = None):
        self.policy = policy or ContextBudgetPolicy()
        self.estimator = estimator or WordCountBudgetEstimator()

    def allocate_and_select(
        self,
        prioritized_items: list[ContextItem]
    ) -> tuple[list[ContextItem], list[ContextItem], dict]:
        """
        Executes budget limits, redistributes unused capacities bidirectionally,
        and excludes oversized items.
        Returns (selected_items, dropped_items, budget_summary_dict).
        """
        total = self.policy.total_budget
        evidence_limit = int(total * self.policy.evidence_ratio)
        knowledge_limit = int(total * self.policy.knowledge_ratio)
        reserved_limit = int(total * self.policy.reserved_ratio)

        evidence_candidates = [item for item in prioritized_items if item.source_kind == "evidence"]
        knowledge_candidates = [item for item in prioritized_items if item.source_kind == "knowledge"]

        selected = []
        dropped = []
        oversized_exclusions = []

        # 1. First Pass: Select items within their respective initial allocations
        evidence_spent = 0
        remaining_evidence = []
        for item in evidence_candidates:
            cost = self.estimator.estimate_cost(item.content)
            item_with_cost = item.model_copy(update={"estimated_budget_cost": cost})
            
            # Oversized Check: cannot fit in the entire category limit
            if cost > evidence_limit:
                oversized_exclusions.append(
                    f"{item.source_kind}:{item.source_id} cost={cost} limit={evidence_limit} - OVERSIZED_ITEM_EXCLUDED"
                )
                dropped.append(item_with_cost)
                continue
                
            if evidence_spent + cost <= evidence_limit:
                evidence_spent += cost
                selected.append(item_with_cost)
            else:
                remaining_evidence.append(item_with_cost)

        knowledge_spent = 0
        remaining_knowledge = []
        for item in knowledge_candidates:
            cost = self.estimator.estimate_cost(item.content)
            item_with_cost = item.model_copy(update={"estimated_budget_cost": cost})
            
            # Oversized Check
            if cost > knowledge_limit:
                oversized_exclusions.append(
                    f"{item.source_kind}:{item.source_id} cost={cost} limit={knowledge_limit} - OVERSIZED_ITEM_EXCLUDED"
                )
                dropped.append(item_with_cost)
                continue
                
            if knowledge_spent + cost <= knowledge_limit:
                knowledge_spent += cost
                selected.append(item_with_cost)
            else:
                remaining_knowledge.append(item_with_cost)

        # 2. Second Pass: Bidirectional Capacity Redistribution
        unused_evidence = evidence_limit - evidence_spent
        unused_knowledge = knowledge_limit - knowledge_spent

        # Offer unused evidence budget to remaining knowledge candidates
        if unused_evidence > 0 and remaining_knowledge:
            for item in remaining_knowledge:
                cost = item.estimated_budget_cost
                if cost > unused_evidence:
                    if cost > (knowledge_limit + unused_evidence):
                        oversized_exclusions.append(
                            f"{item.source_kind}:{item.source_id} cost={cost} limit={knowledge_limit + unused_evidence} - OVERSIZED_ITEM_EXCLUDED"
                        )
                    dropped.append(item)
                elif knowledge_spent + cost <= (knowledge_limit + unused_evidence):
                    knowledge_spent += cost
                    unused_evidence -= cost
                    selected.append(item)
                else:
                    dropped.append(item)
        else:
            dropped.extend(remaining_knowledge)

        # Offer unused knowledge budget to remaining evidence candidates
        if unused_knowledge > 0 and remaining_evidence:
            for item in remaining_evidence:
                cost = item.estimated_budget_cost
                if cost > unused_knowledge:
                    if cost > (evidence_limit + unused_knowledge):
                        oversized_exclusions.append(
                            f"{item.source_kind}:{item.source_id} cost={cost} limit={evidence_limit + unused_knowledge} - OVERSIZED_ITEM_EXCLUDED"
                        )
                    dropped.append(item)
                elif evidence_spent + cost <= (evidence_limit + unused_knowledge):
                    evidence_spent += cost
                    unused_knowledge -= cost
                    selected.append(item)
                else:
                    dropped.append(item)
        else:
            dropped.extend(remaining_evidence)

        remaining_budget = total - (evidence_spent + knowledge_spent + reserved_limit)

        summary = {
            "total_budget": total,
            "evidence_budget": evidence_limit,
            "knowledge_budget": knowledge_limit,
            "evidence_cost": evidence_spent,
            "knowledge_cost": knowledge_spent,
            "remaining_budget": max(remaining_budget, 0),
            "dropped_by_budget_count": len(dropped),
            "excluded_oversized_items": tuple(oversized_exclusions)
        }

        return selected, dropped, summary
