import pytest

from src.utils.performance import PerformanceTracker, performance_tracker


class Result:
    def __init__(self):
        self.performance_metrics = None


def test_boot_timing():
    tracker = PerformanceTracker()
    assert tracker.get_boot_time() is None
    tracker.start_boot()
    tracker.end_boot()
    assert tracker.get_boot_time() is not None
    assert tracker.get_boot_time() >= 0


def test_end_boot_without_start_is_noop():
    tracker = PerformanceTracker()
    tracker.end_boot()
    assert tracker.get_boot_time() is None


def test_start_boot_resets_previous_duration():
    tracker = PerformanceTracker()
    tracker.start_boot()
    tracker.end_boot()
    tracker.start_boot()
    assert tracker.get_boot_time() is None


def test_global_instance_exists():
    assert isinstance(performance_tracker, PerformanceTracker)


def test_time_operation_sync_records_metrics():
    @PerformanceTracker.time_operation("load")
    def load():
        return Result()

    res = load()
    assert "load_duration_seconds" in res.performance_metrics
    assert load.__name__ == "load"


async def test_time_operation_async_records_metrics():
    @PerformanceTracker.time_operation("fetch")
    async def fetch():
        return Result()

    res = await fetch()
    assert "fetch_duration_seconds" in res.performance_metrics
    assert isinstance(res.performance_metrics["fetch_duration_seconds"], float)


def test_time_operation_leaves_plain_results_alone():
    @PerformanceTracker.time_operation()
    def compute():
        return 42

    assert compute() == 42


def test_time_operation_reraises_sync():
    @PerformanceTracker.time_operation("boom")
    def boom():
        raise RuntimeError("x")

    with pytest.raises(RuntimeError):
        boom()


async def test_time_operation_reraises_async():
    @PerformanceTracker.time_operation("boom")
    async def boom():
        raise RuntimeError("x")

    with pytest.raises(RuntimeError):
        await boom()
