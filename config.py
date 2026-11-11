import os

API_ID = int(os.getenv("API_ID", "123456"))
API_HASH = os.getenv("API_HASH", "your_api_hash")
BOT_TOKEN = os.getenv("BOT_TOKEN", "your_bot_token")
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")

# Primary Owner ID
OWNER_ID = int(os.getenv("OWNER_ID", "123456789"))

# AI API Config (Default Gemini ya koi bhi open free endpoint)
CHATBOT_API_KEY = os.getenv("CHATBOT_API_KEY", "")
