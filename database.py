import os
from motor.motor_asyncio import AsyncIOMotorClient

client = None
db = None

def get_db():
    global client, db
    if client is None:
        mongo_uri = os.getenv("MONGODB_URI")
        if not mongo_uri:
            print("Warning: MONGODB_URI not found. Using local fallback.")
            mongo_uri = "mongodb://localhost:27017/weave_automation"
        client = AsyncIOMotorClient(mongo_uri)
        # Parse DB name from URI or default to weave_automation
        db_name = mongo_uri.split("/")[-1].split("?")[0] if "/" in mongo_uri.replace("mongodb://", "").replace("mongodb+srv://", "") else "weave_automation"
        if not db_name:
            db_name = "weave_automation"
        db = client[db_name]
    return db

def is_db_connected():
    return client is not None
