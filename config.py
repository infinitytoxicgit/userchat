import os
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")

# Primary Owner ID
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

# AI API Config (Gemini / Groq)
CHATBOT_API_KEY = os.getenv("CHATBOT_API_KEY", "")

# Git Update Config
UPSTREAM_REPO = os.getenv("UPSTREAM_REPO", "https://github.com/infinitytoxicgit/userchat")
UPSTREAM_BRANCH = os.getenv("UPSTREAM_BRANCH", "main")
