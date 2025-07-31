"""Performance tracking utilities"""

import time
from typing import Optional


class PerformanceTracker:
    """Track application performance metrics"""

    def __init__(self):
        self.boot_start_time: Optional[float] = None
        self.boot_end_time: Optional[float] = None
        self.boot_duration: Optional[float] = None

    def start_boot(self):
        """Mark the start of boot process"""
        self.boot_start_time = time.time()

    def end_boot(self):
        """Mark the end of boot process"""
        self.boot_end_time = time.time()
        if self.boot_start_time:
            self.boot_duration = self.boot_end_time - self.boot_start_time

    def get_boot_time(self) -> Optional[float]:
        """Get boot duration in seconds"""
        return self.boot_duration

    @staticmethod
    def time_operation(operation_name: str = "operation"):
        """Decorator to time function execution"""

        def decorator(func):
            async def async_wrapper(*args, **kwargs):
                start_time = time.time()
                try:
                    result = await func(*args, **kwargs)
                    duration = time.time() - start_time

                    # Add timing to result if it has performance_metrics
                    if hasattr(result, "performance_metrics"):
                        if result.performance_metrics is None:
                            result.performance_metrics = {}
                        result.performance_metrics[
                            f"{operation_name}_duration_seconds"
                        ] = round(duration, 3)

                    return result
                except Exception:
                    duration = time.time() - start_time
                    # Log the duration even on error
                    raise

            def sync_wrapper(*args, **kwargs):
                start_time = time.time()
                try:
                    result = func(*args, **kwargs)
                    duration = time.time() - start_time

                    # Add timing to result if it has performance_metrics
                    if hasattr(result, "performance_metrics"):
                        if result.performance_metrics is None:
                            result.performance_metrics = {}
                        result.performance_metrics[
                            f"{operation_name}_duration_seconds"
                        ] = round(duration, 3)

                    return result
                except Exception:
                    duration = time.time() - start_time
                    raise

            # Return appropriate wrapper based on function type
            import asyncio

            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            return sync_wrapper

        return decorator


# Global performance tracker instance
performance_tracker = PerformanceTracker()
