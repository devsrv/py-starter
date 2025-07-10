import asyncio
import functools
import inspect
import logging
from datetime import datetime, timedelta
from typing import Callable, Any, Optional, Union, Dict, List
from croniter import croniter
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ScheduledTask:
    name: str
    func: Callable
    cron_expression: str
    is_async: bool = False
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)
    retries: int = 0
    max_retries: int = 3
    retry_delay: int = 60  # seconds
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    status: TaskStatus = TaskStatus.PENDING
    error_count: int = 0
    
    def __post_init__(self):
        self.is_async = inspect.iscoroutinefunction(self.func)
        self.update_next_run()
    
    def update_next_run(self):
        """Calculate the next run time based on cron expression"""
        base_time = self.last_run or datetime.now()
        cron = croniter(self.cron_expression, base_time)
        self.next_run = cron.get_next(datetime)
    
    def should_run(self) -> bool:
        """Check if the task should run now"""
        if self.next_run is None:
            return False
        return datetime.now() >= self.next_run


class AsyncScheduler:
    """Laravel-like async task scheduler for Python"""
    
    def __init__(self):
        self.tasks: Dict[str, ScheduledTask] = {}
        self.running = False
        self._task_lock = asyncio.Lock()
        self._shutdown_event = asyncio.Event()
    
    def schedule(self, cron: str, name: Optional[str]=None) -> Callable:
        """Decorator to schedule tasks with cron expressions
        
        Examples:
            @scheduler.schedule("* * * * *", name="sync_data")
            async def sync_data():
                pass
                
            @scheduler.schedule("0 2 * * *")  # Daily at 2 AM
            def backup_database():
                pass
        """

        def decorator(func: Callable) -> Callable:
            task_name = name or func.__name__
            
            task = ScheduledTask(
                name=task_name,
                func=func,
                cron_expression=cron
            )
            
            self.tasks[task_name] = task
            logger.info(f"Scheduled task '{task_name}' with cron: {cron}")
            
            return func
        
        return decorator
    
    def add_task(self, func: Callable, cron: str, name: Optional[str]=None,
                 *args, **kwargs) -> ScheduledTask:
        """Add a task programmatically"""
        task_name = name or func.__name__
        
        task = ScheduledTask(
            name=task_name,
            func=func,
            cron_expression=cron,
            args=args,
            kwargs=kwargs
        )
        
        self.tasks[task_name] = task
        logger.info(f"Added task '{task_name}' with cron: {cron}")
        
        return task
    
    async def run_task(self, task: ScheduledTask) -> bool:
        """Execute a single task with error handling and retries"""
        async with self._task_lock:
            task.status = TaskStatus.RUNNING
            
        try:
            logger.info(f"Running task: {task.name}")
            
            if task.is_async:
                result = await task.func(*task.args, **task.kwargs)
            else:
                # Run sync functions in executor to avoid blocking
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    functools.partial(task.func, *task.args, **task.kwargs)
                )
            
            task.status = TaskStatus.COMPLETED
            task.last_run = datetime.now()
            task.error_count = 0
            task.retries = 0
            task.update_next_run()
            
            logger.info(f"Task '{task.name}' completed successfully")
            return True
            
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error_count += 1
            
            logger.error(f"Task '{task.name}' failed: {str(e)}", exc_info=True)
            
            # Handle retries
            if task.retries < task.max_retries:
                task.retries += 1
                retry_time = datetime.now() + timedelta(seconds=task.retry_delay)
                task.next_run = retry_time
                logger.info(f"Retrying task '{task.name}' in {task.retry_delay} seconds (attempt {task.retries}/{task.max_retries})")
            else:
                task.retries = 0
                task.update_next_run()
                logger.error(f"Task '{task.name}' failed after {task.max_retries} retries")
            
            return False
    
    async def process_tasks(self):
        """Main loop to process scheduled tasks"""
        while not self._shutdown_event.is_set():
            try:
                # Check all tasks
                tasks_to_run = []
                
                async with self._task_lock:
                    for task in self.tasks.values():
                        if task.should_run() and task.status != TaskStatus.RUNNING:
                            tasks_to_run.append(task)
                
                # Run tasks concurrently
                if tasks_to_run:
                    await asyncio.gather(
                        *[self.run_task(task) for task in tasks_to_run],
                        return_exceptions=True
                    )
                
                # Sleep for a short time before checking again
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Error in scheduler loop: {str(e)}", exc_info=True)
                await asyncio.sleep(5)  # Wait longer on error
    
    async def start(self):
        """Start the scheduler"""
        if self.running:
            logger.warning("Scheduler is already running")
            return
        
        self.running = True
        self._shutdown_event.clear()
        
        logger.info(f"Starting scheduler with {len(self.tasks)} tasks")
        
        try:
            await self.process_tasks()
        finally:
            self.running = False
    
    async def stop(self):
        """Stop the scheduler gracefully"""
        logger.info("Stopping scheduler...")
        self._shutdown_event.set()
    
    def list_tasks(self) -> List[Dict[str, Any]]:
        """Get information about all scheduled tasks"""
        return [
            {
                "name": task.name,
                "cron": task.cron_expression,
                "status": task.status.value,
                "last_run": task.last_run.isoformat() if task.last_run else None,
                "next_run": task.next_run.isoformat() if task.next_run else None,
                "error_count": task.error_count,
                "retries": task.retries
            }
            for task in self.tasks.values()
        ]
    
    # Laravel-like convenience methods
    def everyMinute(self, func: Callable, name: Optional[str]=None):
        """Schedule task to run every minute"""
        return self.add_task(func, "* * * * *", name)
    
    def everyFiveMinutes(self, func: Callable, name: Optional[str]=None):
        """Schedule task to run every 5 minutes"""
        return self.add_task(func, "*/5 * * * *", name)
    
    def everyTenMinutes(self, func: Callable, name: Optional[str]=None):
        """Schedule task to run every 10 minutes"""
        return self.add_task(func, "*/10 * * * *", name)
    
    def everyThirtyMinutes(self, func: Callable, name: Optional[str]=None):
        """Schedule task to run every 30 minutes"""
        return self.add_task(func, "*/30 * * * *", name)
    
    def hourly(self, func: Callable, name: Optional[str]=None):
        """Schedule task to run every hour"""
        return self.add_task(func, "0 * * * *", name)
    
    def hourlyAt(self, minute: int, func: Callable, name: Optional[str]=None):
        """Schedule task to run every hour at specific minute"""
        return self.add_task(func, f"{minute} * * * *", name)
    
    def daily(self, func: Callable, name: Optional[str]=None):
        """Schedule task to run daily at midnight"""
        return self.add_task(func, "0 0 * * *", name)
    
    def dailyAt(self, time: str, func: Callable, name: Optional[str]=None):
        """Schedule task to run daily at specific time (HH:MM)"""
        hour, minute = time.split(":")
        return self.add_task(func, f"{minute} {hour} * * *", name)
    
    def weekly(self, func: Callable, name: Optional[str]=None):
        """Schedule task to run weekly on Sunday at midnight"""
        return self.add_task(func, "0 0 * * 0", name)
    
    def weeklyOn(self, day: int, time: str, func: Callable, name: Optional[str]=None):
        """Schedule task to run weekly on specific day and time"""
        hour, minute = time.split(":")
        return self.add_task(func, f"{minute} {hour} * * {day}", name)
    
    def monthly(self, func: Callable, name: Optional[str]=None):
        """Schedule task to run monthly on the 1st at midnight"""
        return self.add_task(func, "0 0 1 * *", name)
    
    def monthlyOn(self, day: int, time: str, func: Callable, name: Optional[str]=None):
        """Schedule task to run monthly on specific day and time"""
        hour, minute = time.split(":")
        return self.add_task(func, f"{minute} {hour} {day} * *", name)


# Global scheduler instance
scheduler = AsyncScheduler()
