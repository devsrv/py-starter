"""
Example usage of the Laravel-like async task scheduler
"""
import asyncio
from .async_scheduler import scheduler


# 1. Using decorators (recommended)
@scheduler.schedule("*/2 * * * *", name="data_sync")
async def sync_data():
    """Sync data every 2 minutes"""
    print("Syncing data...")
    await asyncio.sleep(1)
    print("Data sync complete!")


@scheduler.schedule("0 9 * * 1-5", name="weekday_report")
def generate_weekday_report():
    """Generate report every weekday at 9 AM"""
    print("Generating weekday report...")
    # This is a sync function - it will run in an executor


# 2. Using convenience methods (Laravel-style)
async def check_queue():
    """Check message queue"""
    print("Checking queue...")
    await asyncio.sleep(0.5)
    print("Queue checked!")


async def process_emails():
    """Process email queue"""
    print("Processing emails...")
    await asyncio.sleep(1)
    print("Emails processed!")


def setup_tasks():
    """Setup tasks using Laravel-like methods"""
    
    # Every minute
    scheduler.everyMinute(check_queue, name="queue_check")
    
    # Every 5 minutes
    scheduler.everyFiveMinutes(process_emails, name="email_processor")
    
    # Every hour at :30
    scheduler.hourlyAt(30, lambda: print("Half-hour mark!"), name="half_hour_notification")
    
    # Daily at 2:30 AM
    scheduler.dailyAt("02:30", backup_database, name="db_backup")
    
    # Weekly on Monday at 8:00 AM
    scheduler.weeklyOn(1, "08:00", weekly_cleanup, name="weekly_cleanup")
    
    # Monthly on the 1st at midnight
    scheduler.monthly(monthly_report, name="monthly_report")


def backup_database():
    """Backup database"""
    print("Backing up database...")


def weekly_cleanup():
    """Weekly cleanup task"""
    print("Running weekly cleanup...")


def monthly_report():
    """Generate monthly report"""
    print("Generating monthly report...")


# 3. Adding tasks with custom parameters
async def send_notification(user_id: int, message: str):
    """Send notification to user"""
    print(f"Sending '{message}' to user {user_id}")
    await asyncio.sleep(0.5)
    print(f"Notification sent to user {user_id}")


def setup_custom_tasks():
    """Setup tasks with custom parameters"""
    
    # Add task with arguments
    scheduler.add_task(
        send_notification,
        "0 10 * * *",  # Daily at 10 AM
        name="daily_reminder",
        # Arguments for the function
        123,  # user_id
        message="Don't forget to check your tasks!"
    )
    
    # Add task with retry configuration
    task = scheduler.add_task(
        potentially_failing_task,
        "*/10 * * * *",  # Every 10 minutes
        name="retry_example"
    )
    task.max_retries = 5
    task.retry_delay = 120  # 2 minutes


async def potentially_failing_task():
    """Task that might fail"""
    import random
    if random.random() < 0.3:  # 30% chance of failure
        raise Exception("Random failure occurred!")
    print("Task executed successfully!")


# 4. Running the scheduler
async def main():
    """Main entry point"""
    print("Setting up scheduled tasks...")
    
    # Setup all tasks
    setup_tasks()
    setup_custom_tasks()
    
    # List all scheduled tasks
    print("\nScheduled tasks:")
    for task in scheduler.list_tasks():
        print(f"  - {task['name']}: {task['cron']} (Next run: {task['next_run']})")
    
    print("\nStarting scheduler... (Press Ctrl+C to stop)")
    
    try:
        await scheduler.start()
    except KeyboardInterrupt:
        print("\nStopping scheduler...")
        await scheduler.stop()


if __name__ == "__main__":
    asyncio.run(main())
