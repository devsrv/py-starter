"""Performance tracking utilities"""

import asyncio
import functools
import logging
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class PerformanceTracker:
    """Track application performance metrics"""

    def __init__(self) -> None:
        self.boot_start_time: float | None = None
        self.boot_end_time: float | None = None
        self.boot_duration: float | None = None

    def start_boot(self) -> None:
        """Mark the start of boot process"""
        self.boot_start_time = time.perf_counter()
        self.boot_end_time = None
        self.boot_duration = None

    def end_boot(self) -> None:
        """Mark the end of boot process"""
        self.boot_end_time = time.perf_counter()
        if self.boot_start_time is not None:
            self.boot_duration = self.boot_end_time - self.boot_start_time

    def get_boot_time(self) -> float | None:
        """Get boot duration in seconds (None until boot has completed)"""
        return self.boot_duration

    @staticmethod
    def time_operation(operation_name: str = "operation") -> Callable[..., Any]:
        """Decorator to time function execution (sync or async).

        If the return value has a `performance_metrics` dict attribute, the duration is
        stored there under `<operation_name>_duration_seconds`. Durations are always
        logged at DEBUG level, including when the function raises.
        """

        def _record(result: Any, duration: float) -> None:
            logger.debug("%s took %.3fs", operation_name, duration)
            if hasattr(result, "performance_metrics"):
                if result.performance_metrics is None:
                    result.performance_metrics = {}
                result.performance_metrics[f"{operation_name}_duration_seconds"] = round(
                    duration, 3
                )

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            if asyncio.iscoroutinefunction(func):

                @functools.wraps(func)
                async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                    start_time = time.perf_counter()
                    try:
                        result = await func(*args, **kwargs)
                    except Exception:
                        logger.debug(
                            "%s failed after %.3fs",
                            operation_name,
                            time.perf_counter() - start_time,
                        )
                        raise
                    _record(result, time.perf_counter() - start_time)
                    return result

                return async_wrapper

            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                start_time = time.perf_counter()
                try:
                    result = func(*args, **kwargs)
                except Exception:
                    logger.debug(
                        "%s failed after %.3fs",
                        operation_name,
                        time.perf_counter() - start_time,
                    )
                    raise
                _record(result, time.perf_counter() - start_time)
                return result

            return sync_wrapper

        return decorator


# Global performance tracker instance
performance_tracker = PerformanceTracker()
