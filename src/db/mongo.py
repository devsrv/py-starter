import logging
from typing import TYPE_CHECKING, Any

from pymongo import MongoClient
from pymongo.collection import Collection

if TYPE_CHECKING:
    from pymongo.database import Database

from src.config import Config

logger = logging.getLogger(__name__)


def mongo_client_kwargs() -> dict[str, Any]:
    """TLS kwargs shared by the sync and async clients.

    When MONGO_TLS is unset we pass nothing and let the URI decide
    (`mongodb+srv://` enables TLS on its own). When it is set we force it.
    """
    if Config.MONGO_TLS is None:
        return {}
    return {"tls": Config.MONGO_TLS}


class Mongo:
    """Small synchronous MongoDB wrapper. Prefer `src.db.async_mongo` inside async code."""

    def __init__(self, mongo_uri: str | None = None, database_name: str | None = None):
        self.mongo_uri = mongo_uri or Config.MONGO_URI
        self.database_name = database_name or Config.MONGO_DB_NAME
        self.client: MongoClient[Any] | None = None
        self.db: Database[Any] | None = None

        self.connect()

    def connect(self) -> None:
        """Open a connection and verify it with a ping."""
        try:
            self.client = MongoClient(self.mongo_uri, **mongo_client_kwargs())
            self.db = self.client[self.database_name]
            self.client.admin.command("ping")
            logger.info("Connected to MongoDB")
        except Exception as e:
            logger.error("Failed to connect to MongoDB: %s", e)
            self.close_connection()
            raise

    def ensure_connected(self) -> None:
        """Ensure the connection is alive, reconnect if needed."""
        if self.client is None:
            self.connect()
            return
        try:
            self.client.admin.command("ping")
        except Exception as e:
            logger.warning("Connection check failed, reconnecting: %s", e)
            self.close_connection()
            self.connect()

    def get_collection(self, name: str) -> Collection[Any]:
        if self.db is None:
            msg = "MongoDB is not connected"
            raise RuntimeError(msg)
        return self.db[name]

    def close_connection(self) -> None:
        """Close MongoDB connection"""
        if self.client is not None:
            self.client.close()
            self.client = None
            self.db = None
            logger.info("MongoDB connection closed")
