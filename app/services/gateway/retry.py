import time
import logging
from typing import Callable, TypeVar, Any
from app.services.gateway.errors import (
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    GatewayError
)

logger = logging.getLogger(__name__)

T = TypeVar("T")

class BoundedRetryHandler:
    """
    Implements bounded retries with exponential backoff on retryable exceptions.
    Allows injecting custom sleep functions to accelerate unit testing.
    """
    def __init__(
        self,
        max_retries: int = 3,
        initial_delay_sec: float = 0.5,
        backoff_factor: float = 2.0,
        sleep_fn: Callable[[float], None] = time.sleep
    ):
        self.max_retries = max_retries
        self.initial_delay_sec = initial_delay_sec
        self.backoff_factor = backoff_factor
        self.sleep_fn = sleep_fn

    def is_retryable(self, exception: Exception) -> bool:
        """
        Determines if the exception belongs to a retryable category.
        """
        return isinstance(exception, (
            ProviderRateLimitError,
            ProviderTimeoutError,
            ProviderUnavailableError
        ))

    def execute(self, operation: Callable[[], T]) -> tuple[T, int]:
        """
        Executes the operation with retries.
        Returns a tuple of (result, retry_count).
        """
        attempts = 0
        delay = self.initial_delay_sec

        while True:
            try:
                result = operation()
                return result, attempts
            except Exception as e:
                if not self.is_retryable(e):
                    # Do not retry non-retryable errors
                    logger.info(f"Non-retryable error encountered: {type(e).__name__}. Propagation immediately.")
                    raise e
                
                attempts += 1
                if attempts > self.max_retries:
                    logger.warning(f"Exceeded max retry attempts ({self.max_retries}). Failing with original error: {str(e)}")
                    raise e

                logger.warning(
                    f"Retryable error encountered: {type(e).__name__} ({str(e)}). "
                    f"Attempt {attempts}/{self.max_retries}. Backoff sleep for {delay}s."
                )
                self.sleep_fn(delay)
                delay *= self.backoff_factor
