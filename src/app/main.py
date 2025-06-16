import logging
from ..config import Config
from ..report.notify import async_report, NotificationType
from datetime import timedelta
from ..cache.redis import RedisCache
from ..db.store import MongoDBClient

# Configure logging
logger = logging.getLogger(__name__) # __name__ or could be fastapi etc. as configured in Config.LOGGING
            
class App:
    def __init__(self, org_id, db_client=None, cache_client=None):
        self.org_id = org_id
        
        # Use provided clients or create new ones
        self.db: MongoDBClient = db_client or MongoDBClient()
        self.cache = cache_client or RedisCache(
            host=Config.REDIS_HOST,
            port=Config.REDIS_PORT,
            db=0
        )
        
    async def initialize(self):
        """ Connect to databases if not already connected """
        if not self.db.client:
            await self.db.connect()
        if not self.cache.client:
            await self.cache.connect()

    async def run(self):
        attempt_key = f"org:{self.org_id}:<some_unique_identifier>:attempts"
        try:
            await self.initialize()
            
            # check if failed attempt counter is 3, if 3 or more then store as failed with score 0 to permanent skip further processing
            attempt_count = await self.cache.get_counter(attempt_key)
            if( attempt_count is not None and attempt_count >= 3):
                # await async_report(f"SKIPPING: processing already attempted 3 times, answer - {self.answer_id}", NotificationType.WARNING)
                result = {"score": 0}
                # await self.db.save_assessment_evaluation(org_id = self.org_id, answer_id = self.answer_id, ai_result = result)
                return result
            
            """ Perform the main logic of the application here ---------------- """
            result = {
                "score": 100,  # Example score, replace with actual logic
                "message": "Processing completed successfully"
            }
            # await self.db.save_assessment_evaluation(org_id = self.org_id, answer_id = self.answer_id, ai_result = result)
            return result

        except Exception as e:
            await self.cache.increment(attempt_key, ttl=timedelta(hours=1))  # Cache failed attempt for 1 hr
            # await async_report(f"STUCK: Error processing, answer - {self.answer_id}, Message - {str(e)}", NotificationType.EMERGENCY)
            raise
        finally:
            # Cleanup any resources if needed e.g. thread pool, connections, etc.
            pass