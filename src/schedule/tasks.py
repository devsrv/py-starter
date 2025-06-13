import schedule
import time
import logging
import logging.config
from ..config import Config

# Configure logging
logging.config.dictConfig(Config.LOGGING)
logger = logging.getLogger(__name__)

def job():
    logger.info("Job executed successfully!")
    print("Running scheduled job...")

def daily_backup():
    print("Running daily backup...")

def weekly_report():
    print("Generating weekly report...")

# Schedule jobs with Laravel-like syntax
schedule.every().minute.do(job)
# schedule.every(3).minutes.do(job)
schedule.every().hour.do(job)
schedule.every().day.at("10:30").do(daily_backup)
schedule.every().monday.do(weekly_report)
schedule.every().wednesday.at("13:15").do(weekly_report)

# Keep the script running
logger.info("Scheduler started")

while True:
    schedule.run_pending()
    time.sleep(1)