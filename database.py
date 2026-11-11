from motor.motor_asyncio import AsyncIOMotorClient
from config import MONGO_URL, OWNER_ID

client = AsyncIOMotorClient(MONGO_URL)
db = client["multi_assistant_bot"]

sessions_col = db["sessions"]
auth_col = db["auth_users"]
chats_col = db["chats_settings"]
api_keys_col = db["api_keys"]

# Auth system
async def is_auth(user_id: int) -> bool:
    if user_id == OWNER_ID:
        return True
    user = await auth_col.find_one({"user_id": user_id})
    return bool(user)

async def add_auth(user_id: int):
    await auth_col.update_one({"user_id": user_id}, {"$set": {"user_id": user_id}}, upsert=True)

async def remove_auth(user_id: int):
    await auth_col.delete_one({"user_id": user_id})

async def get_all_auth():
    return [doc["user_id"] async for doc in auth_col.find()]

# Sessions
async def save_session(session_string: str, phone: str = ""):
    await sessions_col.update_one(
        {"session_string": session_string},
        {"$set": {"session_string": session_string, "phone": phone}},
        upsert=True
    )

async def get_all_sessions():
    return [doc["session_string"] async for doc in sessions_col.find()]

async def delete_session(session_string: str):
    await sessions_col.delete_one({"session_string": session_string})

# Settings per Chat
async def get_chat_settings(chat_id: int):
    chat = await chats_col.find_one({"chat_id": chat_id})
    if not chat:
        return {"chatbot": False, "welcome": False, "welcome_msg": "Welcome {mention}!", "welcome_buttons": []}
    return chat

async def update_chat_settings(chat_id: int, key: str, value):
    await chats_col.update_one({"chat_id": chat_id}, {"$set": {key: value}}, upsert=True)
