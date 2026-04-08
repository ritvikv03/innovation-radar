"""
core/utils.py — Shared Utilities
=================================
Small helpers used across the core package.

retry_with_backoff  — exponential backoff with jitter for any callable.
                      Retries only on transient errors (network, quota).
                      Raises immediately on validation errors.
"""

from __future__ import annotations

import time
from typing import Callable, Tuple, Type

from core.logger import get_logger

log = get_logger(__name__)

# Errors that should NOT be retried — they indicate a logic / validation failure
_NON_RETRYABLE = (ValueError, TypeError, AttributeError)


def retry_with_backoff(
    fn: Callable,
    max_attempts: int = 3,
    base_delay: float = 2.0,
    non_retryable: Tuple[Type[Exception], ...] = _NON_RETRYABLE,
):
    """
    Call ``fn()`` up to ``max_attempts`` times with exponential backoff + jitter.

    Parameters
    ----------
    fn            : zero-argument callable to execute
    max_attempts  : total attempts before re-raising
    base_delay    : initial wait in seconds (doubles each attempt)
    non_retryable : exception types that abort immediately (no retry)

    Returns
    -------
    The return value of ``fn()`` on first success.

    Raises
    ------
    The last exception on final failure.
    Non-retryable exceptions are re-raised immediately on first occurrence.
    """
    last_exc: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except non_retryable as exc:
            # Validation / logic errors — retrying won't help
            raise
        except Exception as exc:
            last_exc = exc
            if attempt == max_attempts:
                break
            delay = base_delay * (2 ** (attempt - 1)) + (time.time() % 1)   # jitter
            log.warning(
                "Attempt %d/%d failed (%s: %s). Retrying in %.1fs…",
                attempt, max_attempts, type(exc).__name__, exc, delay,
            )
            time.sleep(delay)

    raise last_exc  # type: ignore[misc]
