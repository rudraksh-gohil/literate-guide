from urllib.parse import quote_plus
import certifi
from pymongo import MongoClient

username = "rudu"
password = "sample@12"

encoded_username = quote_plus(username)
encoded_password = quote_plus(password)


uri = f"mongodb+srv://{encoded_username}:{encoded_password}@cluster0.rsk4r.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
client = MongoClient(uri, tlsCAFile=certifi.where())


db = client["Sy_userstories_db"]
collection = db["stories"]


domain_counts = collection.aggregate([
    {"$group": {"_id": "$domain", "story_count": {"$sum": 1}}},
    {"$sort": {"story_count": -1}},
    {"$limit": 10}
])

quality_counts = collection.aggregate([
    {"$group": {"_id": "$quality", "count": {"$sum": 1}}},
    {"$sort": {"count": -1}}
])

model_counts = collection.aggregate([
    {"$group": {"_id": "$model", "story_count": {"$sum": 1}}},
    {"$sort": {"story_count": -1}}
])

print("Stories per Domain:")
for doc in domain_counts:
    print(f"- Domain: {doc['_id']}, Count: {doc['story_count']}")

print("\nQuality Distribution:")
for doc in quality_counts:
    print(f"- Quality: {doc['_id']}, Count: {doc['count']}")

print("\nStories per Model:")
for doc in model_counts:
    print(f"- Model: {doc['_id']}, Count: {doc['story_count']}")
