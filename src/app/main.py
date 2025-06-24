import logging
from boot import app_boot
import asyncio
from src.db.async_mysql import MySQLClient
from src.config import Config
from src.report.notify import async_report, NotificationType
from src.utils import now
from datetime import timedelta
from src.cache.redis import RedisCache
from src.db.async_mongo import MongoDBClient

# Configure logging
logger = logging.getLogger(__name__) # __name__ or could be fastapi etc. as configured in Config.LOGGING
            
async def main():
    await app_boot()
    
    mongo = MongoDBClient()
    mysql = MySQLClient()
    
    try:
        await mongo.connect()
        await mysql.create_pool()
        
        """For Reference"""
        # db = MongoBatchManager(store=mongo, collection_name="ai_batches")
        # await process_orgs_concurrently(allowed_orgs, db)
        
    except Exception as e:
        logger.error(f"Critical error in main execution: {str(e)}")
        await async_report(f"Critical error in main execution: {str(e)}", NotificationType.ERROR)
        raise
    finally:
        await mongo.close()
        await mysql.close_pool()

if __name__ == "__main__":
    asyncio.run(main())