import time
import random
import aiohttp
from pyrogram import Client, filters
from pyrogram.types import Message
from database import is_auth, get_chat_settings, update_chat_settings
from config import CHATBOT_API_KEY, OWNER_ID

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
GUARD_MODEL = "meta-llama/llama-prompt-guard-2-86m"

# Saare Free Groq Models (Priority order me fallback)
GROQ_FREE_MODELS = [
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-120b",
    "llama-3.1-8b-instant",
    "allam-2-7b",
    "gemma2-9b-it"
]

# Saare Free Gemini Models (Agar CHATBOT_API_KEY Google/Gemini ki ho)
GEMINI_FREE_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash"
]

_last_alert_time = 0

@Client.on_message(filters.command("chatbot") & filters.group)
async def toggle_chatbot(client: Client, message: Message):
    if message.sender_chat and message.sender_chat.id == message.chat.id:
        pass
    elif not message.from_user or not await is_auth(message.from_user.id):
        return

    from main import clients
    chat_id = message.chat.id
    args = message.command[1:]

    if not args:
        settings = await get_chat_settings(chat_id)
        active_ids = settings.get("chatbot_sessions", [])
        status_str = f"🟢 ON for IDs: `{[i + 1 for i in active_ids]}`" if active_ids else "🔴 OFF"
        provider = "Groq Free Pool" if str(CHATBOT_API_KEY).startswith("gsk_") else "Gemini Free Pool"
        return await message.reply(
            f"💬 **AI Girl Chatbot Controller**\n"
            f"• **Current Status:** {status_str}\n"
            f"• **Engine:** `{provider}` (Auto-Fallback)\n\n"
            f"**Commands:**\n"
            f"• `/chatbot 1` — Enable only ID #1\n"
            f"• `/chatbot 1 2` — Enable ID #1 & #2\n"
            f"• `/chatbot all` — Enable all active IDs\n"
            f"• `/chatbot disable` — Turn OFF chatbot"
        )

    if args[0].lower() in ["off", "disable", "stop"]:
        await update_chat_settings(chat_id, "chatbot", False)
        await update_chat_settings(chat_id, "chatbot_sessions", [])
        return await message.reply("🔴 **AI Girl Chatbot disabled** for this group & VC chat.")

    if not clients:
        return await message.reply("⚠️ **No active userbot sessions found.** Add a session first.")

    target_indices = []
    if args[0].lower() in ["all", "on", "enable"]:
        target_indices = list(range(len(clients)))
    else:
        for item in args:
            for num in item.replace(",", " ").split():
                if num.isdigit():
                    idx = int(num) - 1
                    if 0 <= idx < len(clients) and idx not in target_indices:
                        target_indices.append(idx)

    if not target_indices:
        return await message.reply(f"❌ **Invalid Session ID.** Available IDs: `1` to `{len(clients)}`.")

    await update_chat_settings(chat_id, "chatbot", True)
    await update_chat_settings(chat_id, "chatbot_sessions", target_indices)

    names_preview = []
    for idx in target_indices:
        try:
            me = await clients[idx].get_me()
            names_preview.append(f"`#{idx + 1}` (**{me.first_name}**)")
        except Exception:
            names_preview.append(f"`#{idx + 1}`")

    await message.reply(
        f"💖 **AI Girl Chatbot Enabled!**\n"
        f"• **Active Personas:** {', '.join(names_preview)}\n"
        f"• **Active In:** Group Chat + Voice Chat Messages 🎙️\n"
        f"• **Features:** Girl Persona + Emojis + Random Tag + Welcome ✨"
    )

def build_girl_system_prompt(bot_name: str, is_welcome: bool = False) -> str:
    if is_welcome:
        return (
            f"You are {bot_name}, a sweet, playful, friendly Indian girl chatting in a Telegram group. "
            "Welcome the new member warmly in 1 short sentence (max 15 words) using natural Hinglish and cute emojis (✨💖😊🌸). "
            "Never break character or say you are an AI."
        )
    return (
        f"You are {bot_name}, a cute, witty, friendly Indian girl chatting in a Telegram group & voice chat. "
        f"Always stay in character as a real girl named {bot_name}. "
        "Reply in 1 to 2 short, natural Hinglish/English sentences with expressive emojis (😊✨💖🙈😂). "
        "Never write long paragraphs and never mention being an AI or bot."
    )

async def call_groq_pool(session: aiohttp.ClientSession, prompt: str, sys_prompt: str) -> str:
    headers = {
        "Authorization": f"Bearer {CHATBOT_API_KEY}",
        "Content-Type": "application/json"
    }

    # Prompt Guard check
    try:
        guard_payload = {
            "model": GUARD_MODEL,
            "messages": [{"role": "user", "content": prompt[:400]}],
            "max_tokens": 10,
            "temperature": 0.0
        }
        async with session.post(GROQ_CHAT_URL, json=guard_payload, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as gresp:
            if gresp.status == 200:
                gdata = await gresp.json()
                verdict = gdata["choices"][0]["message"]["content"].strip().lower()
                if any(bad in verdict for bad in ("jailbreak", "injection", "unsafe")):
                    return "Hehe nice try, par main itni bhi bholi nahi hu 😜✨"
    except Exception:
        pass

    last_err = "UNKNOWN"
    for model_name in GROQ_FREE_MODELS:
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.85,
            "max_tokens": 220
        }
        try:
            async with session.post(GROQ_CHAT_URL, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=12)) as resp:
                if resp.status == 401:
                    raise Exception("INVALID_KEY_401")
                if resp.status != 200:
                    last_err = f"HTTP_{resp.status}"
                    continue
                data = await resp.json()
                reply_text = data["choices"][0]["message"].get("content", "").strip()
                if reply_text:
                    return reply_text
        except Exception as e:
            if "INVALID_KEY_401" in str(e):
                raise
            last_err = str(e)
            continue

    raise Exception(f"ALL_GROQ_MODELS_BUSY ({last_err})")

async def call_gemini_pool(session: aiohttp.ClientSession, prompt: str, sys_prompt: str) -> str:
    last_err = "UNKNOWN"
    for model_name in GEMINI_FREE_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={CHATBOT_API_KEY}"
        payload = {
            "contents": [{
                "parts": [{"text": f"{sys_prompt}\n\nUser message: {prompt}"}]
            }]
        }
        try:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=12)) as resp:
                if resp.status in (400, 401, 403):
                    err_body = await resp.text()
                    if "API_KEY_INVALID" in err_body or resp.status in (401, 403):
                        raise Exception("INVALID_GEMINI_KEY")
                if resp.status != 200:
                    last_err = f"HTTP_{resp.status}"
                    continue
                data = await resp.json()
                reply_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                if reply_text:
                    return reply_text
        except Exception as e:
            if "INVALID_GEMINI_KEY" in str(e):
                raise
            last_err = str(e)
            continue

    raise Exception(f"ALL_GEMINI_MODELS_BUSY ({last_err})")

async def ask_girl_ai(prompt: str, bot_name: str, is_welcome: bool = False) -> str:
    key = str(CHATBOT_API_KEY or "").strip()
    if not key:
        raise Exception("NO_API_KEY_SET")

    sys_prompt = build_girl_system_prompt(bot_name, is_welcome=is_welcome)

    async with aiohttp.ClientSession() as session:
        # Auto-detect Groq (gsk_...) vs Google Gemini key
        if key.startswith("gsk_"):
            return await call_groq_pool(session, prompt, sys_prompt)
        else:
            return await call_gemini_pool(session, prompt, sys_prompt)

async def notify_owner_once(client: Client, reason: str):
    global _last_alert_time
    now = time.time()
    if now - _last_alert_time < 600:  # 10 minute cooldown taaki spam na ho
        return
    _last_alert_time = now
    try:
        await client.send_message(
            OWNER_ID,
            f"⚠️ **Chatbot API Alert:** `{reason}`\n"
            "• Agar Groq models (`gpt-oss-120b` / `llama-3.3`) chalane hain toh `.env` me `CHATBOT_API_KEY=gsk_...` daalein.\n"
            "• Ya valid Google AI Studio Gemini key (`AIza...`) daalein."
        )
    except Exception:
        pass

def get_enabled_responders(clients, chat_settings):
    if not chat_settings.get("
