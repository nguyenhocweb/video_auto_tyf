import logging
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from src.core.config import settings

logger = logging.getLogger("database_mongo")

class MongoDBManager:
    client: AsyncIOMotorClient | None = None
    db: AsyncIOMotorDatabase | None = None

    @classmethod
    def get_client(cls) -> AsyncIOMotorClient:
        if cls.client is None:
            logger.info(f"Connecting to MongoDB at {settings.DATABASE_URL.split('@')[-1]}...")
            cls.client = AsyncIOMotorClient(
                settings.DATABASE_URL,
                maxPoolSize=50,
                minPoolSize=1,
                maxIdleTimeMS=45000,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=10000,
                socketTimeoutMS=20000,
            )
        return cls.client

    @classmethod
    def get_database(cls) -> AsyncIOMotorDatabase:
        if cls.db is None:
            client = cls.get_client()
            cls.db = client[settings.MONGO_DB_NAME]
        return cls.db

    @classmethod
    def close(cls):
        if cls.client is not None:
            cls.client.close()
            cls.client = None
            cls.db = None
            logger.info("MongoDB connection closed.")

def get_mongo_db() -> AsyncIOMotorDatabase:
    """Dependency injection cho FastAPI endpoints."""
    return MongoDBManager.get_database()
