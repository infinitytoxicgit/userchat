import random
import aiohttp
from pyrogram import Client, filters
from pyrogram.types import Message
from database import is_auth, get_chat_settings, update_chat_settings
from config import CHATBOT_API_KEY, OWNER_ID

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
GUARD_MODEL = "meta-llama/llama-prompt-guard-2-86m"
CHAT_MODEL = "allam-2-7b"

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
        return await message.reply(
            f"💬 **AI Girl Chatbot Controller**\n"
            f"• **Current Status:** {status_str}\n\n"
            f"**Commands:**\n"
            f"• `/chatbot 1` — Enable only ID #1\n"
            f"• `/chatbot 1 2` — Enable ID #1 & #2\n"
            f"• `/chatbot all` — Enable all active IDs\n"
            f"• `/chatbot disable` — Turn OFF chatbot in this group"
        )

    if args[0].lower() in ["off", "disable", "stop"]:
        await update_chat_settings(chat_id, "chatbot", False)
        await update_chat_settings(chat_id, "chatbot_sessions", [])
        return await message.reply("🔴 **AI Girl Chatbot disabled** for this group.")

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
        f"• **Features:** Auto-Reply + Random Tag + New Member Tag Welcome ✨"
    )

async def check_prompt_guard(session: aiohttp.ClientSession, headers: dict, text: str) -> bool:
    payload = {
        "model": GUARD_MODEL,
        "messages": [{"role": "user", "content": text[:500]}],
        "max_tokens": 10,
        "temperature": 0.0
    }
    try:
        async with session.post(GROQ_CHAT_URL, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=6)) as resp:
            if resp.status == 200:
                data = await resp.json()
                verdict = data["choices"][0]["message"]["content"].strip().lower()
                if "jailbreak" in verdict or "injection" in verdict or "unsafe" in verdict:
                    return False
    except Exception:
        pass
    return True

async def ask_girl_ai(prompt: str, bot_name: str, is_welcome: bool = False) -> str:
    if not CHATBOT_API_KEY:
        raise Exception("API_KEY_EXHAUSTED")

    headers = {
        "Authorization": f"Bearer {CHATBOT_API_KEY}",
        "Content-Type": "application/json"
    }

    async with aiohttp.ClientSession() as session:
        is_safe = await check_prompt_guard(session, headers, prompt)
        if not is_safe:
            return "Hehe nice try, par main itni bhi bholi nahi hu 😜✨"

        if is_welcome:
            sys_prompt = (
                f"You are {bot_name}, a sweet, playful, friendly Indian girl chatting in a Telegram group. "
                "Welcome the new member warmly in 1 short sentence (max 15 words) using natural Hinglish and cute emojis (✨💖😊🌸). "
                "Never break character or say you are an AI."
            )
        else:
            sys_prompt = (
                f"You are {bot_name}, a cute, witty, friendly Indian girl chatting in a Telegram group. "
                "Always stay in character as a real girl named " + bot_name + ". "
                "Reply in 1 to 2 short, natural Hinglish/English sentences with expressive emojis (😊✨💖🙈😂). "
                "Never write long paragraphs and never mention being an AI or bot."
            )

        payload = {
            "model": CHAT_MODEL,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.85,
            "max_tokens": 80
        }

        async with session.post(GROQ_CHAT_URL, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=12)) as resp:
            if resp.status in (401, 429):
                raise Exception("API_KEY_EXHAUSTED")
            if resp.status != 200:
                return f"Abhi thoda network slow hai jaan, ek min baad baat karte hain 🙈✨"
            data = await resp.json()
            try:
                return data["choices"][0]["message"]["content"].strip()
            except (KeyError, IndexError):
                return "Hehe kya bola? Samajh nahi aaya 🙈💖"

def get_enabled_responders(clients, chat_settings):
    if not chat_settings.get("chatbot", False) or not clients:
        return []
    saved_indices = chat_settings.get("chatbot_sessions", [])
    if not saved_indices:
        return list(enumerate(clients))
    return [(idx, clients[idx]) for idx in saved_indices if 0 <= idx < len(clients)]

# 1. New Member Join -> Tag karke Girl Persona me Welcome
@Client.on_message(filters.new_chat_members & filters.group, group=9)
async def welcome_new_member_girl(client: Client, message: Message):
    from main import clients
    chat_settings = await get_chat_settings(message.chat.id)
    responders = get_enabled_responders(clients, chat_settings)
    if not responders:
        return

    for member in message.new_chat_members:
        if member.is_bot:
            continue
        _, responder = random.choice(responders)
        try:
            me = await responder.get_me()
            girl_name = me.first_name or "Cutie"
            user_tag = f"[{member.first_name}](tg://user?id={member.id})"
            welcome_reply = await ask_girl_ai(
                f"New member {member.first_name} just joined the group {message.chat.title}. Welcome them!",
                bot_name=girl_name,
                is_welcome=True
            )
            await responder.send_message(
                message.chat.id,
                f"✨ {user_tag} {welcome_reply}",
                reply_to_message_id=message.id
            )
        except Exception as e:
            if "API_KEY_EXHAUSTED" in str(e):
                try:
                    await client.send_message(OWNER_ID, "⚠️ **Alert:** Groq API Key (`CHATBOT_API_KEY`) limit exhausted or invalid!")
                except Exception:
                    pass

# 2. Mention / Reply / Random Tag Chat Handler
@Client.on_message(filters.text & filters.group & ~filters.command(["chatbot", "joinvc", "leavevc", "update", "panel", "addallsessions"]), group=10)
async def handle_ai_mentions(client: Client, message: Message):
    if not message.from_user or message.from_user.is_bot:
        return

    from main import clients
    chat_settings = await get_chat_settings(message.chat.id)
    responders = get_enabled_responders(clients, chat_settings)
    if not responders:
        return

    # Check karo kya kisi enabled userbot ke naam ya reply par message aaya hai
    chosen_responder = None
    replied_user_id = (
        message.reply_to_message.from_user.id
        if message.reply_to_message and message.reply_to_message.from_user
        else None
    )

    msg_lower = message.text.lower()
    for _, ubot in responders:
        try:
            me = await ubot.get_me()
            if replied_user_id == me.id:
                chosen_responder = ubot
                break
            if me.first_name and me.first_name.lower() in msg_lower:
                chosen_responder = ubot
                break
        except Exception:
            pass

    trigger_words = ["hi", "hello", "hey", "oye", "sun", "jaan", "baby", "cutie", "bot", "kaisi", "kya", "kon"]
    is_triggered = bool(chosen_responder) or any(w in msg_lower.split() for w in trigger_words) or (random.random() < 0.25)

    if not is_triggered:
        return

    if not chosen_responder:
        _, chosen_responder = random.choice(responders)

    try:
        me = await chosen_responder.get_me()
        girl_name = me.first_name or "Cutie"
        response = await ask_girl_ai(message.text, bot_name=girl_name, is_welcome=False)

        # Sender tag + kabhi-kabhi random member tag
        sender_tag = f"[{message.from_user.first_name}](tg://user?id={message.from_user.id})"
        extra_tag = ""
        if random.random() < 0.20:
            try:
                recent_users = []
                async for m in client.get_chat_history(message.chat.id, limit=15):
                    if m.from_user and not m.from_user.is_bot and m.from_user.id not in (message.from_user.id, me.id):
                        recent_users.append(m.from_user)
                if recent_users:
                    rnd_u = random.choice(recent_users)
                    extra_tag = f" (cc: [{rnd_u.first_name}](tg://user?id={rnd_u.id}))"
            except Exception:
                pass

        await chosen_responder.send_message(
            message.chat.id,
            f"{sender_tag} {response}{extra_tag}",
            reply_to_message_id=message.id
        )
    except Exception as e:
        if "API_KEY_EXHAUSTED" in str(e):
            try:
                await client.send_message(
                    OWNER_ID,
                    "⚠️ **Alert:** Groq API (`CHATBOT_API_KEY`) quota limit touch ho gaya hai ya key invalid hai!"
                )
            except Exception:
                pass
