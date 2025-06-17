import logging
from pymongo import MongoClient
from typing import Any, Optional
from src.config import Config

logger = logging.getLogger(__name__)

class Mongo:
    def __init__(self, mongo_uri: Optional[str] = None, database_name: Optional[str] = None):
        self.mongo_uri = mongo_uri or Config.MONGO_URI
        self.database_name = database_name or Config.MONGO_DB_NAME
        
        # Initialize MongoDB connection
        self.connect()
        
    def connect(self):
        """Connect to MongoDB if not already connected"""
        try:
            self.client: MongoClient[Any] = MongoClient(self.mongo_uri)
            self.db = self.client[self.database_name]
            
            # Test connection
            self.client.admin.command('ping')
            logger.info("Connected to MongoDB")
            
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise
        
    def ensure_connected(self):
        """Ensure connection is alive, reconnect if needed"""
        try:
            if not self.client:
                self.connect()
                return
                
            # Ping to check if connection is alive
            self.client.admin.command('ping')
        except Exception as e:
            logger.warning(f"Connection check failed, {str(e)}")
            self.close_connection()
            
            
    def close_connection(self):
        """Close MongoDB connection"""
        if hasattr(self, 'client'):
            self.client.close()
            logger.info("MongoDB connection closed")