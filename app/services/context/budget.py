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
    and redistributing unused budget segments from evidence to knowledge support.
    """
    def __init__(self, policy: ContextBudgetPolicy | None = None, estimator: BaseBudgetEstimator | None = None):
        self.policy = policy or ContextBudgetPolicy()
        self.estimator = estimator or WordCountBudgetEstimator()

    def allocate_and_select(
        self,
        prioritized_items: list[ContextItem]
    ) -> tuple[list[ContextItem], list[ContextItem], dict]:
        """
        Executes budget limits, redistributes unused evidence allocation, and selects items.
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

        # 1. Process Evidence Items
        evidence_spent = 0
        for item in evidence_candidates:
            cost = self.estimator.estimate_cost(item.content)
            # Update the estimated cost on the context item
            item_with_cost = item.model_copy(update={"estimated_budget_cost": cost})
            
            if evidence_spent + cost <= evidence_limit:
                evidence_spent += cost
                selected.append(item_with_cost)
            else:
                dropped.append(item_with_cost)

        # 2. Redistribute Unused Evidence Budget to Knowledge
        unused_evidence = evidence_limit - evidence_spent
        active_knowledge_limit = knowledge_limit + max(unused_evidence, 0)

        # 3. Process Knowledge Chunks
        knowledge_spent = 0
        for item in knowledge_candidates:
            cost = self.estimator.estimate_cost(item.content)
            item_with_cost = item.model_copy(update={"estimated_budget_cost": cost})

            if knowledge_spent + cost <= active_knowledge_limit:
                knowledge_spent += cost
                selected.append(item_with_cost)
            else:
                dropped.append(item_with_cost)

        remaining_budget = total - (evidence_spent + knowledge_spent + reserved_limit)

        summary = {
            "total_budget": total,
            "evidence_budget": evidence_limit,
            "knowledge_budget": active_knowledge_limit,
            "evidence_cost": evidence_spent,
            "knowledge_cost": knowledge_spent,
            "remaining_budget": max(remaining_budget, 0),
            "dropped_by_budget_count": len(dropped)
        }

        return selected, dropped, summary
