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

async def ask_gemini(prompt: str) -> str:
    if not CHATBOT_API_KEY:
        raise Exception("API_KEY_EXHAUSTED")
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={CHATBOT_API_KEY}"
    payload = {
        "contents": [{
            "parts": [{"text": f"You are a friendly, witty Telegram chat buddy. Reply shortly in natural Hinglish or English without long essays. User said: {prompt}"}]
        }]
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 429:
                raise Exception("API_KEY_EXHAUSTED")
            if resp.status != 200:
                return "Abhi network busy hai bhai, thodi der me reply karta hu!"
            data = await resp.json()
            try:
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()
            except (KeyError, IndexError):
                return "Samajh nahi aaya bhai!"

@Client.on_message(filters.text & filters.group, group=10)
async def handle_ai_mentions(client: Client, message: Message):
    from main import clients
    chat_settings = await get_chat_settings(message.chat.id)
    if not chat_settings.get("chatbot", False):
        return

    bot_names = ["bot", "shinobi", "assistant", "bhai"]
    is_mentioned = any(name in message.text.lower().split() for name in bot_names)
    is_reply_to_me = bool(message.reply_to_message and message.reply_to_message.from_user and message.reply_to_message.from_user.is_self)

    if is_mentioned or is_reply_to_me:
        try:
            response = await ask_gemini(message.text)
            responder = random.choice(clients) if clients else client
            user_tag = f"[{message.from_user.first_name}](tg://user?id={message.from_user.id})"
            
            await responder.send_message(
                message.chat.id,
                f"{user_tag} {response}",
                reply_to_message_id=message.id
            )
        except Exception as e:
            if "API_KEY_EXHAUSTED" in str(e):
                await client.send_message(
                    OWNER_ID,
                    "⚠️ **Alert:** Chatbot Gemini API quota limit touch ho gaya hai! Kripya new key update karein."
                )
