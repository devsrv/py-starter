import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.config import Config
from src.schedule.async_scheduler import AsyncScheduler, ScheduledTask, TaskStatus, scheduler

UTC = ZoneInfo("UTC")


@pytest.fixture
def sched():
    return AsyncScheduler(tz=UTC, poll_interval=0.01)


def due(task: ScheduledTask) -> None:
    task.next_run = task.now() - timedelta(seconds=1)


class TestScheduledTask:
    def test_next_run_is_computed_in_tz(self):
        task = ScheduledTask("t", lambda: None, "0 9 * * *", tz=UTC)
        assert task.next_run is not None
        assert task.next_run.tzinfo is not None
        assert task.next_run.hour == 9
        assert task.next_run > task.now()

    def test_invalid_cron_rejected(self):
        with pytest.raises(ValueError, match="Invalid cron"):
            ScheduledTask("t", lambda: None, "not a cron", tz=UTC)

    def test_detects_async(self):
        async def a():
            pass

        assert ScheduledTask("a", a, "* * * * *", tz=UTC).is_async is True
        assert ScheduledTask("s", lambda: None, "* * * * *", tz=UTC).is_async is False

    def test_should_run(self):
        task = ScheduledTask("t", lambda: None, "* * * * *", tz=UTC)
        assert task.should_run() is False
        due(task)
        assert task.should_run() is True
        task.next_run = None
        assert task.should_run() is False

    def test_update_next_run_uses_last_run(self):
        task = ScheduledTask("t", lambda: None, "*/15 * * * *", tz=UTC)
        task.last_run = datetime(2025, 1, 1, 10, 3, tzinfo=UTC)
        task.update_next_run()
        assert task.next_run == datetime(2025, 1, 1, 10, 15, tzinfo=UTC)


class TestRegistration:
    def test_defaults_to_app_timezone(self):
        assert AsyncScheduler().tz == Config.TZ
        assert scheduler.tz == Config.TZ

    def test_decorator_registers_and_returns_function(self, sched):
        @sched.schedule("* * * * *", name="named")
        async def job():
            return 1

        @sched.schedule("0 * * * *")
        def other():
            pass

        assert set(sched.tasks) == {"named", "other"}
        assert sched.tasks["named"].func is job
        assert asyncio.iscoroutinefunction(job)

    def test_add_task_with_args_and_retry_settings(self, sched):
        def job(a, b=None):
            pass

        task = sched.add_task(
            job, "* * * * *", "j", args=(1,), kwargs={"b": 2}, max_retries=5, retry_delay=7
        )
        assert task.args == (1,)
        assert task.kwargs == {"b": 2}
        assert task.max_retries == 5
        assert task.retry_delay == 7
        assert task.tz == UTC

    def test_duplicate_name_replaces(self, sched, caplog):
        sched.add_task(lambda: 1, "* * * * *", "dup")
        sched.add_task(lambda: 2, "0 0 * * *", "dup")
        assert len(sched.tasks) == 1
        assert sched.tasks["dup"].cron_expression == "0 0 * * *"

    def test_remove_task(self, sched):
        sched.add_task(lambda: 1, "* * * * *", "x")
        assert sched.remove_task("x") is True
        assert sched.remove_task("x") is False

    def test_list_tasks(self, sched):
        sched.add_task(lambda: 1, "* * * * *", "x")
        [info] = sched.list_tasks()
        assert info["name"] == "x"
        assert info["cron"] == "* * * * *"
        assert info["status"] == "pending"
        assert info["last_run"] is None
        assert info["next_run"] is not None
        assert info["error_count"] == 0

    @pytest.mark.parametrize(
        "method,args,cron",
        [
            ("everyMinute", (), "* * * * *"),
            ("everyFiveMinutes", (), "*/5 * * * *"),
            ("everyTenMinutes", (), "*/10 * * * *"),
            ("everyThirtyMinutes", (), "*/30 * * * *"),
            ("hourly", (), "0 * * * *"),
            ("hourlyAt", (45,), "45 * * * *"),
            ("daily", (), "0 0 * * *"),
            ("dailyAt", ("02:30",), "30 2 * * *"),
            ("weekly", (), "0 0 * * 0"),
            ("weeklyOn", (1, "08:15"), "15 8 * * 1"),
            ("monthly", (), "0 0 1 * *"),
            ("monthlyOn", (15, "23:59"), "59 23 15 * *"),
        ],
    )
    def test_convenience_methods(self, sched, method, args, cron):
        task = getattr(sched, method)(*args, lambda: None, name="conv")
        assert task.cron_expression == cron

    @pytest.mark.parametrize("bad", ["9", "25:00", "10:60", "ab:cd", "1:2:3"])
    def test_bad_times_rejected(self, sched, bad):
        with pytest.raises(ValueError):
            sched.dailyAt(bad, lambda: None)


class TestExecution:
    async def test_runs_async_task_and_reschedules(self, sched):
        ran = []

        async def job(x, y=0):
            ran.append(x + y)

        task = sched.add_task(job, "* * * * *", "j", args=(1,), kwargs={"y": 2})
        due(task)
        assert await sched.run_pending() == 1
        assert ran == [3]
        assert task.status == TaskStatus.COMPLETED
        assert task.last_run is not None
        assert task.next_run > task.now()
        assert await sched.run_pending() == 0

    async def test_runs_sync_task_in_executor(self, sched):
        import threading

        seen = {}

        def job():
            seen["thread"] = threading.current_thread().name

        task = sched.add_task(job, "* * * * *", "sync")
        due(task)
        assert await sched.run_task(task) is True
        assert seen["thread"] != threading.main_thread().name

    async def test_failure_schedules_retry_then_gives_up(self, sched):
        async def job():
            raise RuntimeError("nope")

        task = sched.add_task(job, "0 0 * * *", "fail", max_retries=2, retry_delay=100)

        assert await sched.run_task(task) is False
        assert task.status == TaskStatus.FAILED
        assert task.retries == 1
        assert task.error_count == 1
        delta = task.next_run - task.now()
        assert timedelta(seconds=95) < delta <= timedelta(seconds=100)

        assert await sched.run_task(task) is False
        assert task.retries == 2

        assert await sched.run_task(task) is False  # exhausted
        assert task.retries == 0
        assert task.error_count == 3
        assert task.next_run.hour == 0  # back on the cron schedule
        assert task.next_run - task.now() > timedelta(seconds=100)

    async def test_success_resets_error_counters(self, sched):
        state = {"fail": True}

        async def job():
            if state["fail"]:
                raise RuntimeError("x")

        task = sched.add_task(job, "* * * * *", "flaky")
        await sched.run_task(task)
        assert task.retries == 1
        state["fail"] = False
        await sched.run_task(task)
        assert task.retries == 0
        assert task.error_count == 0
        assert task.status == TaskStatus.COMPLETED

    async def test_running_task_is_not_started_twice(self, sched):
        started = asyncio.Event()
        release = asyncio.Event()
        count = 0

        async def slow():
            nonlocal count
            count += 1
            started.set()
            await release.wait()

        task = sched.add_task(slow, "* * * * *", "slow")
        due(task)
        first = asyncio.create_task(sched.run_pending())
        await started.wait()
        assert task.status == TaskStatus.RUNNING
        assert await sched.run_pending() == 0
        release.set()
        await first
        assert count == 1

    async def test_start_and_stop_loop(self, sched):
        ran = asyncio.Event()

        async def job():
            ran.set()

        task = sched.add_task(job, "* * * * *", "loop")
        due(task)

        runner = asyncio.create_task(sched.start())
        await asyncio.wait_for(ran.wait(), timeout=2)
        assert sched.running is True
        await sched.stop()
        await asyncio.wait_for(runner, timeout=2)
        assert sched.running is False

    async def test_start_twice_warns(self, sched, caplog):
        runner = asyncio.create_task(sched.start())
        await asyncio.sleep(0.02)
        await sched.start()  # returns immediately
        assert "already running" in caplog.text
        await sched.stop()
        await runner
