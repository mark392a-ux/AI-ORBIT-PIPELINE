"""
Retry-with-backoff decorator used by every extractor's HTTP calls.

Implements the "Resilience" and "Error Handling" requirements from the
spec: transient network/API failures should be retried with exponential
backoff + jitter rather than crashing the whole pipeline run, but
persistent failures should be logged and surfaced (not swallowed silently).
"""

from __future__ import annotations

import functools
import random
import time
from typing import Callable, TypeVar

from src.utils.logging_config import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


def retry_with_backoff(
    max_attempts: int = 4,
    base_delay: float = 1.0,
    max_delay: float = 20.0,
    retry_exceptions: tuple = (Exception,),
):
    """
    Decorator: retries the wrapped function on failure with exponential
    backoff and jitter. Raises the final exception if all attempts fail so
    the caller can decide how to degrade gracefully (skip record, use
    cached data, etc.) rather than the retry layer hiding the failure.
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            attempt = 0
            while True:
                attempt += 1
                try:
                    return func(*args, **kwargs)
                except retry_exceptions as exc:
                    if attempt >= max_attempts:
                        logger.error(
                            "%s failed after %d attempts: %s",
                            func.__qualname__,
                            attempt,
                            exc,
                        )
                        raise
                    delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
                    delay += random.uniform(0, delay * 0.25)
                    logger.warning(
                        "%s attempt %d/%d failed (%s); retrying in %.1fs",
                        func.__qualname__,
                        attempt,
                        max_attempts,
                        exc,
                        delay,
                    )
                    time.sleep(delay)

        return wrapper

    return decorator
