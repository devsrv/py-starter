import schedule
import time
import logging
from datetime import datetime

SCHEDULAR_LOG_FILE = '/home/sourav/apps/py-starter/scheduler.log' #TODO: get from env

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(SCHEDULAR_LOG_FILE),
        logging.StreamHandler()
    ]
)

def job():
    logging.info("Job executed successfully!")
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
logging.info("Scheduler started")

while True:
    schedule.run_pending()
    time.sleep(1)