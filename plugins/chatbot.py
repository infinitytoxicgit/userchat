import random
import aiohttp
from pyrogram import Client, filters
from pyrogram.types import Message
from database import is_auth, get_chat_settings, update_chat_settings
from config import CHATBOT_API_KEY, OWNER_ID

@Client.on_message(filters.command("chatbot"))
async def toggle_chatbot(client: Client, message: Message):
    if not await is_auth(message.from_user.id):
        return
    if len(message.command) < 2:
        return await message.reply("Usage: `/chatbot on` ya `/chatbot disable`")
    
    action = message.command[1].lower()
    chat_id = message.chat.id
    
    if action in ["on", "enable"]:
        await update_chat_settings(chat_id, "chatbot", True)
        await message.reply("AI Chatbot is chat ke liye **ON** ho gaya hai.")
    elif action in ["off", "disable"]:
        await update_chat_settings(chat_id, "chatbot", False)
        await message.reply("AI Chatbot is chat ke liye **OFF** ho gaya hai.")

async def ask_ai_service(prompt: str) -> str:
    # Dummy mock response / Free API endpoint
    # Agar API quota khatam ho jaye:
    if not CHATBOT_API_KEY:
        raise Exception("API_KEY_EXHAUSTED")
    async with aiohttp.ClientSession() as session:
        # Example call
        return f"Hello! Reply for: {prompt}"

@Client.on_message(filters.text & filters.group, group=10)
async def handle_ai_mentions(client: Client, message: Message):
    from main import clients
    chat_settings = await get_chat_settings(message.chat.id)
    if not chat_settings.get("chatbot", False):
        return

    # Check if message mentions client accounts or replies to them
    bot_names = ["bot", "shinobi", "assistant"]
    is_mentioned = any(name in message.text.lower() for name in bot_names)
    
    if is_mentioned or (message.reply_to_message and message.reply_to_message.from_user):
        try:
            response = await ask_ai_service(message.text)
            
            # Select any random connected userbot to answer
            responder = random.choice(clients) if clients else client
            
            reply_tag = f"[{message.from_user.first_name}](tg://user?id={message.from_user.id})"
            await responder.send_message(
                message.chat.id,
                f"{reply_tag} {response}",
                reply_to_message_id=message.id
            )
        except Exception as e:
            if "API_KEY_EXHAUSTED" in str(e):
                # Alert owner in DM
                await client.send_message(
                    OWNER_ID,
                    "⚠️ **Alert:** Chatbot API limits/quota exhaust ho gaya hai! Kripya new API key create karke set karo."
                )
