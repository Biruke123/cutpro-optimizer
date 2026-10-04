"""
MongoDB connection module for CutPro
Loads MONGO_URI from .env and provides collections
"""
import os
from dotenv import load_dotenv
from pymongo import MongoClient, ASCENDING, DESCENDING
import certifi

# Load .env from the same folder as this file
from pathlib import Path
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)
print(f"📄 Loading .env from: {env_path}")
print(f"📄 File exists: {env_path.exists()}")

MONGO_URI = os.getenv('MONGO_URI')
if not MONGO_URI:
    raise RuntimeError("❌ MONGO_URI not found in .env — did you create the file?")

print(f"🔌 Connecting to MongoDB...")

# Connect with proper TLS (required for Atlas)
client = MongoClient(MONGO_URI, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=10000)

# Test connection
try:
    client.admin.command('ping')
    print("✅ MongoDB connected")
except Exception as e:
    print(f"❌ MongoDB connection failed: {e}")
    raise

# Database + collections
db = client['cutpro']
users_col = db['users']
history_col = db['history']
skp_col = db['sketchup_parts']

# Indexes (safe to call repeatedly — Mongo ignores existing)
users_col.create_index([('username', ASCENDING)], unique=True)
history_col.create_index([('username', ASCENDING), ('timestamp', DESCENDING)])

print(f"✅ Collections ready: users, history, sketchup_parts")