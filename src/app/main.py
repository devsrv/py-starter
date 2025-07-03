from boot import app_boot
import logging
import asyncio
from src.db.async_mongo import mongo_manager, get_collection
from src.db.async_mysql import mysql_manager, fetch_one, execute_query, execute_transaction
from src.config import Config
from src.report.notify import async_report, NotificationType
from src.cache.redis import RedisCache

# Configure logging
logger = logging.getLogger(__name__)  # __name__ or could be fastapi etc. as configured in Config.LOGGING

            
async def main():
    await app_boot()
    
    try:
        await mongo_manager.initialize()
        await mysql_manager.initialize()
        
        """do something"""
        
    except Exception as e:
        logger.error(f"Critical error in main execution: {str(e)}")
        await async_report(f"Critical error in main execution: {str(e)}", NotificationType.ERROR)
        raise
    finally:
        await mongo_manager.close()
        await mysql_manager.close()


if __name__ == "__main__":
    asyncio.run(main())
