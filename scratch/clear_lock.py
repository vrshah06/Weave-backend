from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()
uri = os.getenv("MONGODB_URI")
client = MongoClient(uri)
db = client.get_default_database()
result = db.worker_locks.delete_many({})
print(f"Deleted {result.deleted_count} stale locks!")
client.close()
