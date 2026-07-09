import logging
import time
from abc import ABC, abstractmethod
from typing import Type
from pydantic import BaseModel

logger = logging.getLogger("opsgraph.tools")

class BaseTool(ABC):
    """
    Abstract base class for all OpsGraph diagnostic tools.
    Encapsulates input models, structured logging, and latency measurements.
    """
    name: str
    description: str
    args_model: Type[BaseModel]

    @abstractmethod
    def run(self, **kwargs) -> BaseModel:
        """
        Subclass implementation of the tool's core logic.
        """
        pass

    def execute(self, input_data: BaseModel) -> BaseModel:
        """
        Execution wrapper that registers log outputs, durations, and outcomes.
        """
        start_time = time.perf_counter()
        logger.info(f"Tool '{self.name}' invoked with arguments: {input_data.model_dump()}")
        try:
            result = self.run(**input_data.model_dump())
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info(f"Tool '{self.name}' executed successfully in {duration_ms:.2f}ms")
            return result
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(f"Tool '{self.name}' failed in {duration_ms:.2f}ms with error: {e}")
            raise e
