"""
Example usage of the Laravel-like async task scheduler.

Run from the project root:

    python -m src.schedule.example_usage
"""

import asyncio
import contextlib
import random

from src.schedule.async_scheduler import scheduler


# 1. Using decorators (recommended)
@scheduler.schedule("*/2 * * * *", name="data_sync")
async def sync_data() -> None:
    """Sync data every 2 minutes"""
    print("Syncing data...")
    await asyncio.sleep(1)
    print("Data sync complete!")


@scheduler.schedule("0 9 * * 1-5", name="weekday_report")
def generate_weekday_report() -> None:
    """Generate report every weekday at 9 AM (sync function, runs in an executor)"""
    print("Generating weekday report...")


# 2. Using convenience methods (Laravel-style)
async def check_queue() -> None:
    print("Checking queue...")
    await asyncio.sleep(0.5)
    print("Queue checked!")


async def process_emails() -> None:
    print("Processing emails...")
    await asyncio.sleep(1)
    print("Emails processed!")


def backup_database() -> None:
    print("Backing up database...")


def weekly_cleanup() -> None:
    print("Running weekly cleanup...")


def monthly_report() -> None:
    print("Generating monthly report...")


def setup_tasks() -> None:
    """Setup tasks using Laravel-like methods"""
    scheduler.everyMinute(check_queue, name="queue_check")
    scheduler.everyFiveMinutes(process_emails, name="email_processor")
    scheduler.hourlyAt(30, lambda: print("Half-hour mark!"), name="half_hour_notification")
    scheduler.dailyAt("02:30", backup_database, name="db_backup")
    scheduler.weeklyOn(1, "08:00", weekly_cleanup, name="weekly_cleanup")
    scheduler.monthly(monthly_report, name="monthly_report")


# 3. Adding tasks with custom parameters
async def send_notification(user_id: int, message: str) -> None:
    print(f"Sending '{message}' to user {user_id}")
    await asyncio.sleep(0.5)
    print(f"Notification sent to user {user_id}")


async def potentially_failing_task() -> None:
    """Task that might fail"""
    if random.random() < 0.3:  # noqa: S311 - demo only
        msg = "Random failure occurred!"
        raise RuntimeError(msg)
    print("Task executed successfully!")


def setup_custom_tasks() -> None:
    """Setup tasks with custom parameters"""
    scheduler.add_task(
        send_notification,
        "0 10 * * *",  # Daily at 10 AM
        name="daily_reminder",
        args=(123,),  # user_id
        kwargs={"message": "Don't forget to check your tasks!"},
    )

    scheduler.add_task(
        potentially_failing_task,
        "*/10 * * * *",  # Every 10 minutes
        name="retry_example",
        max_retries=5,
        retry_delay=120,  # 2 minutes
    )


# 4. Running the scheduler
async def main() -> None:
    print("Setting up scheduled tasks...")
    setup_tasks()
    setup_custom_tasks()

    print("\nScheduled tasks:")
    for task in scheduler.list_tasks():
        print(f"  - {task['name']}: {task['cron']} (Next run: {task['next_run']})")

    print("\nStarting scheduler... (Press Ctrl+C to stop)")
    try:
        await scheduler.start()
    except asyncio.CancelledError:
        await scheduler.stop()


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())
