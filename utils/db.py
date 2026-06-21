import os
import logging
from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger("database_manager")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DATABASE_NAME = os.getenv("DATABASE_NAME", "archgen_db")

class DatabaseManager:
    client: AsyncIOMotorClient = None
    db = None

    async def connect_to_database(self):
        """
        Creates an asynchronous connection to MongoDB database.
        """
        logger.info(f"Connecting to MongoDB at: {MONGO_URI}")
        try:
            self.client = AsyncIOMotorClient(
                MONGO_URI,
                maxPoolSize=50,
                minPoolSize=10,
                serverSelectionTimeoutMS=5000,
                socketTimeoutMS=30000
            )
            self.db = self.client[DATABASE_NAME]
            # Simple ping to verify connection
            await self.client.admin.command('ping')
            logger.info("Successfully established connection with MongoDB.")
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}. Project persistence disabled.")
            self.client = None
            self.db = None

    async def close_database_connection(self):
        """
        Closes connection to MongoDB.
        """
        if self.client:
            self.client.close()
            logger.info("MongoDB client connection closed.")

db_manager = DatabaseManager()

def get_database():
    """
    Dependency resolver returning the database context.
    """
    return db_manager.db
