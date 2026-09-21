"""
Laravel-like async task scheduler.

    from src.schedule.async_scheduler import scheduler

    @scheduler.schedule("*/5 * * * *", name="sync_data")
    async def sync_data(): ...

    scheduler.dailyAt("02:30", backup_database)
    await scheduler.start()

Cron expressions are evaluated in the application timezone (Config.TZ).
"""

import asyncio
import functools
import inspect
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, tzinfo
from enum import Enum
from typing import Any

from croniter import croniter

from src.config import Config

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ScheduledTask:
    name: str
    func: Callable[..., Any]
    cron_expression: str
    tz: tzinfo | None = None
    is_async: bool = False
    args: tuple[Any, ...] = field(default_factory=tuple)
    kwargs: dict[str, Any] = field(default_factory=dict)
    retries: int = 0
    max_retries: int = 3
    retry_delay: int = 60  # seconds
    last_run: datetime | None = None
    next_run: datetime | None = None
    status: TaskStatus = TaskStatus.PENDING
    error_count: int = 0

    def __post_init__(self) -> None:
        if not croniter.is_valid(self.cron_expression):
            msg = f"Invalid cron expression for task '{self.name}': {self.cron_expression!r}"
            raise ValueError(msg)
        self.is_async = inspect.iscoroutinefunction(self.func)
        self.update_next_run()

    def now(self) -> datetime:
        return datetime.now(self.tz)

    def update_next_run(self) -> None:
        """Calculate the next run time based on cron expression"""
        base_time = self.last_run or self.now()
        self.next_run = croniter(self.cron_expression, base_time).get_next(datetime)

    def should_run(self) -> bool:
        """Check if the task should run now"""
        if self.next_run is None:
            return False
        return self.now() >= self.next_run


class AsyncScheduler:
    """Laravel-like async task scheduler for Python"""

    def __init__(self, tz: tzinfo | None = None, poll_interval: float = 1.0):
        self.tz = tz or Config.TZ
        self.poll_interval = poll_interval
        self.tasks: dict[str, ScheduledTask] = {}
        self.running = False
        self._task_lock = asyncio.Lock()
        self._shutdown_event = asyncio.Event()
        self._inflight: set[asyncio.Task[Any]] = set()

    def schedule(self, cron: str, name: str | None = None) -> Callable[..., Any]:
        """Decorator to schedule tasks with cron expressions

        Examples:
            @scheduler.schedule("* * * * *", name="sync_data")
            async def sync_data():
                pass

            @scheduler.schedule("0 2 * * *")  # Daily at 2 AM
            def backup_database():
                pass
        """

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self.add_task(func, cron, name)
            return func

        return decorator

    def add_task(
        self,
        func: Callable[..., Any],
        cron: str,
        name: str | None = None,
        *,
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
        max_retries: int = 3,
        retry_delay: int = 60,
    ) -> ScheduledTask:
        """Add a task programmatically.

        `args`/`kwargs` are passed to `func` on every run. Registering a task with a
        name that already exists replaces the old one.
        """
        task_name = name or func.__name__

        task = ScheduledTask(
            name=task_name,
            func=func,
            cron_expression=cron,
            tz=self.tz,
            args=tuple(args),
            kwargs=dict(kwargs or {}),
            max_retries=max_retries,
            retry_delay=retry_delay,
        )

        if task_name in self.tasks:
            logger.warning("Replacing already scheduled task '%s'", task_name)
        self.tasks[task_name] = task
        logger.info("Scheduled task '%s' with cron: %s", task_name, cron)

        return task

    def remove_task(self, name: str) -> bool:
        """Unschedule a task by name."""
        return self.tasks.pop(name, None) is not None

    async def run_task(self, task: ScheduledTask) -> bool:
        """Execute a single task with error handling and retries"""
        async with self._task_lock:
            task.status = TaskStatus.RUNNING

        try:
            logger.info("Running task: %s", task.name)

            if task.is_async:
                await task.func(*task.args, **task.kwargs)
            else:
                # Run sync functions in executor to avoid blocking
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(
                    None, functools.partial(task.func, *task.args, **task.kwargs)
                )

            task.status = TaskStatus.COMPLETED
            task.last_run = task.now()
            task.error_count = 0
            task.retries = 0
            task.update_next_run()

            logger.info("Task '%s' completed successfully", task.name)
            return True

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error_count += 1

            logger.error("Task '%s' failed: %s", task.name, e, exc_info=True)

            if task.retries < task.max_retries:
                task.retries += 1
                task.next_run = task.now() + timedelta(seconds=task.retry_delay)
                logger.info(
                    "Retrying task '%s' in %s seconds (attempt %s/%s)",
                    task.name,
                    task.retry_delay,
                    task.retries,
                    task.max_retries,
                )
            else:
                task.retries = 0
                task.last_run = task.now()
                task.update_next_run()
                logger.error("Task '%s' failed after %s retries", task.name, task.max_retries)

            return False

    async def run_pending(self) -> int:
        """Run every task that is due right now. Returns how many were started."""
        async with self._task_lock:
            due = [
                t for t in self.tasks.values() if t.should_run() and t.status != TaskStatus.RUNNING
            ]

        if due:
            await asyncio.gather(*[self.run_task(task) for task in due], return_exceptions=True)
        return len(due)

    async def process_tasks(self) -> None:
        """Main loop to process scheduled tasks"""
        while not self._shutdown_event.is_set():
            try:
                await self.run_pending()
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("Error in scheduler loop: %s", e, exc_info=True)
                await asyncio.sleep(self.poll_interval * 5)  # Wait longer on error

    async def start(self) -> None:
        """Start the scheduler (blocks until stop() is called)"""
        if self.running:
            logger.warning("Scheduler is already running")
            return

        self.running = True
        self._shutdown_event.clear()

        logger.info("Starting scheduler with %s tasks", len(self.tasks))

        try:
            await self.process_tasks()
        finally:
            self.running = False

    async def stop(self) -> None:
        """Stop the scheduler gracefully"""
        logger.info("Stopping scheduler...")
        self._shutdown_event.set()

    def list_tasks(self) -> list[dict[str, Any]]:
        """Get information about all scheduled tasks"""
        return [
            {
                "name": task.name,
                "cron": task.cron_expression,
                "status": task.status.value,
                "last_run": task.last_run.isoformat() if task.last_run else None,
                "next_run": task.next_run.isoformat() if task.next_run else None,
                "error_count": task.error_count,
                "retries": task.retries,
            }
            for task in self.tasks.values()
        ]

    # Laravel-like convenience methods
    def everyMinute(self, func: Callable[..., Any], name: str | None = None) -> ScheduledTask:
        """Schedule task to run every minute"""
        return self.add_task(func, "* * * * *", name)

    def everyFiveMinutes(self, func: Callable[..., Any], name: str | None = None) -> ScheduledTask:
        """Schedule task to run every 5 minutes"""
        return self.add_task(func, "*/5 * * * *", name)

    def everyTenMinutes(self, func: Callable[..., Any], name: str | None = None) -> ScheduledTask:
        """Schedule task to run every 10 minutes"""
        return self.add_task(func, "*/10 * * * *", name)

    def everyThirtyMinutes(
        self, func: Callable[..., Any], name: str | None = None
    ) -> ScheduledTask:
        """Schedule task to run every 30 minutes"""
        return self.add_task(func, "*/30 * * * *", name)

    def hourly(self, func: Callable[..., Any], name: str | None = None) -> ScheduledTask:
        """Schedule task to run every hour"""
        return self.add_task(func, "0 * * * *", name)

    def hourlyAt(
        self, minute: int, func: Callable[..., Any], name: str | None = None
    ) -> ScheduledTask:
        """Schedule task to run every hour at specific minute"""
        return self.add_task(func, f"{minute} * * * *", name)

    def daily(self, func: Callable[..., Any], name: str | None = None) -> ScheduledTask:
        """Schedule task to run daily at midnight"""
        return self.add_task(func, "0 0 * * *", name)

    def dailyAt(
        self, time: str, func: Callable[..., Any], name: str | None = None
    ) -> ScheduledTask:
        """Schedule task to run daily at specific time (HH:MM)"""
        hour, minute = self._parse_time(time)
        return self.add_task(func, f"{minute} {hour} * * *", name)

    def weekly(self, func: Callable[..., Any], name: str | None = None) -> ScheduledTask:
        """Schedule task to run weekly on Sunday at midnight"""
        return self.add_task(func, "0 0 * * 0", name)

    def weeklyOn(
        self, day: int, time: str, func: Callable[..., Any], name: str | None = None
    ) -> ScheduledTask:
        """Schedule task to run weekly on specific day (0=Sunday..6=Saturday) and time"""
        hour, minute = self._parse_time(time)
        return self.add_task(func, f"{minute} {hour} * * {day}", name)

    def monthly(self, func: Callable[..., Any], name: str | None = None) -> ScheduledTask:
        """Schedule task to run monthly on the 1st at midnight"""
        return self.add_task(func, "0 0 1 * *", name)

    def monthlyOn(
        self, day: int, time: str, func: Callable[..., Any], name: str | None = None
    ) -> ScheduledTask:
        """Schedule task to run monthly on specific day and time"""
        hour, minute = self._parse_time(time)
        return self.add_task(func, f"{minute} {hour} {day} * *", name)

    @staticmethod
    def _parse_time(time: str) -> tuple[int, int]:
        try:
            hour_s, minute_s = time.split(":")
            hour, minute = int(hour_s), int(minute_s)
        except ValueError as e:
            msg = f"Time must be in HH:MM format, got {time!r}"
            raise ValueError(msg) from e
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            msg = f"Time out of range: {time!r}"
            raise ValueError(msg)
        return hour, minute


# Global scheduler instance
scheduler = AsyncScheduler()
