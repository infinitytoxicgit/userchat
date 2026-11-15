import re
import time
import random
import aiohttp
from collections import defaultdict, deque
from pyrogram import Client, filters
from pyrogram.types import Message, ChatMemberUpdated
from pyrogram.enums import ChatMemberStatus
from database import is_auth, get_chat_settings, update_chat_settings
from config import CHATBOT_API_KEY, OWNER_ID

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
GUARD_MODEL = "meta-llama/llama-prompt-guard-2-86m"

GROQ_FREE_MODELS = [
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-120b",
    "llama-3.1-8b-instant",
    "allam-2-7b",
    "gemma2-9b-it"
]

GEMINI_FREE_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash"
]

_last_alert_time = 0
_welcomed_users = {}                # {(chat_id, user_id): timestamp} duplicate welcome rokne ke liye
_casual_msg_counter = defaultdict(int)
_last_casual_reply = defaultdict(float)
_chat_memory = defaultdict(lambda: deque(maxlen=10))  # {(chat_id, bot_id, user_id): deque}

def clean_trigger_words(full_name: str) -> list[str]:
    # "Jaanvi 🌻" -> ["jaanvi 🌻", "jaanvi"] (emojis hata kar bhi clean first name match kare)
    words = []
    fn_lower = full_name.strip().lower()
    if fn_lower:
        words.append(fn_lower)
    alpha_only = re.sub(r"[^a-zA-Z0-9\s]", "", fn_lower).strip()
    if alpha_only and alpha_only not in words:
        words.append(alpha_only)
    first_word = alpha_only.split()[0] if alpha_only.split() else ""
    if len(first_word) >= 3 and first_word not in words:
        words.append(first_word)
    return words

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
            f"• `/chatbot disable` — Turn OFF chatbot"
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
            full_n = f"{me.first_name or ''} {me.last_name or ''}".strip()
            names_preview.append(f"`#{idx + 1}` (**{full_n}**)")
        except Exception:
            names_preview.append(f"`#{idx + 1}`")

    await message.reply(
        f"💖 **AI Girl Chatbot Enabled!**\n"
        f"• **Active Girls:** {', '.join(names_preview)}\n"
        f"• **Mode:** Smart Name/Tag Reply + Memory + Request/Join Welcome ✨"
    )

def build_girl_system_prompt(bot_full_name: str, is_welcome: bool = False) -> str:
    if is_welcome:
        return (
            f"You are {bot_full_name}, a sweet, playful, friendly Indian girl chatting in a Telegram group. "
            f"Your full display name is {bot_full_name}. "
            "Welcome the new member warmly in 1 short sentence (max 15 words) using natural Hinglish and cute emojis (✨💖😊🌸). "
            "Never break character or say you are an AI or bot."
        )
    return (
        f"You are {bot_full_name}, a cute, witty, real Indian girl chatting in a Telegram group. "
        f"Your exact display name is '{bot_full_name}'. Stay completely in character as {bot_full_name}. "
        "Remember the previous conversation history with this user and reply naturally in 1 to 2 short Hinglish/English sentences with cute emojis (😊✨💖🙈😂). "
        "Never write long paragraphs, never repeat the user's exact words, and never say you are an AI or bot."
    )

async def call_groq_pool(session: aiohttp.ClientSession, messages_list: list) -> str:
    headers = {
        "Authorization": f"Bearer {CHATBOT_API_KEY}",
        "Content-Type": "application/json"
    }

    last_user_text = messages_list[-1]["content"]
    try:
        guard_payload = {
            "model": GUARD_MODEL,
            "messages": [{"role": "user", "content": last_user_text[:400]}],
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
            "messages": messages_list,
            "temperature": 0.85,
            "max_tokens": 200
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

async def call_gemini_pool(session: aiohttp.ClientSession, messages_list: list) -> str:
    sys_prompt = messages_list[0]["content"]
    convo_lines = []
    for m in messages_list[1:]:
        role_tag = "User" if m["role"] == "user" else "You"
        convo_lines.append(f"{role_tag}: {m['content']}")
    full_prompt = f"{sys_prompt}\n\nConversation:\n" + "\n".join(convo_lines)

    last_err = "UNKNOWN"
    for model_name in GEMINI_FREE_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={CHATBOT_API_KEY}"
        payload = {"contents": [{"parts": [{"text": full_prompt}]}]}
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

async def ask_girl_ai(prompt: str, bot_full_name: str, history: list = None, is_welcome: bool = False) -> str:
    key = str(CHATBOT_API_KEY or "").strip()
    if not key:
        raise Exception("NO_API_KEY_SET")

    sys_prompt = build_girl_system_prompt(bot_full_name, is_welcome=is_welcome)
    messages_list = [{"role": "system", "content": sys_prompt}]
    if history:
        messages_list.extend(history)
    messages_list.append({"role": "user", "content": prompt})

    async with aiohttp.ClientSession() as session:
        if key.startswith("gsk_"):
            return await call_groq_pool(session, messages_list)
        else:
            return await call_gemini_pool(session, messages_list)

async def notify_owner_once(client: Client, reason: str):
    global _last_alert_time
    now = time.time()
    if now - _last_alert_time < 600:
        return
    _last_alert_time = now
    try:
        await client.send_message(OWNER_ID, f"⚠️ **Chatbot API Alert:** `{reason}`")
    except Exception:
        pass

def get_enabled_responders(clients, chat_settings):
    if not chat_settings.get("chatbot", False) or not clients:
        return []
    saved_indices = chat_settings.get("chatbot_sessions", [])
    if not saved_indices:
        return list(enumerate(clients))
    return [(idx, clients[idx]) for idx in saved_indices if 0 <= idx < len(clients)]

async def send_welcome_tag(client: Client, chat_id: int, chat_title: str, user, reply_to_id: int = None):
    if not user or user.is_bot:
        return

    # Duplicate welcome prevent (agar service message aur chat_member_updated dono fire hon)
    now = time.time()
    key = (chat_id, user.id)
    if now - _welcomed_users.get(key, 0) < 30:
        return
    _welcomed_users[key] = now

    from main import clients
    chat_settings = await get_chat_settings(chat_id)
    responders = get_enabled_responders(clients, chat_settings)
    if not responders:
        return

    _, responder = random.choice(responders)
    try:
        me = await responder.get_me()
        bot_full_name = f"{me.first_name or ''} {me.last_name or ''}".strip() or "Cutie"
        user_tag = f"[{user.first_name}](tg://user?id={user.id})"
        welcome_reply = await ask_girl_ai(
            f"New member {user.first_name} just joined {chat_title}. Welcome them!",
            bot_full_name=bot_full_name,
            is_welcome=True
        )
        await responder.send_message(
            chat_id,
            f"✨ {user_tag} {welcome_reply}",
            reply_to_message_id=reply_to_id
        )
    except Exception as e:
        await notify_owner_once(client, str(e))

# 1A. Normal Member Join Service Message Welcome
@Client.on_message(filters.new_chat_members & filters.group, group=9)
async def welcome_on_service_join(client: Client, message: Message):
    for member in message.new_chat_members:
        await send_welcome_tag(client, message.chat.id, message.chat.title, member, reply_to_id=message.id)

# 1B. Join Request Approve Hone Par Bhi Tag Karke Welcome
@Client.on_chat_member_updated(filters.group, group=9)
async def welcome_on_request_approved(client: Client, event: ChatMemberUpdated):
    old_status = event.old_chat_member.status if event.old_chat_member else None
    new_status = event.new_chat_member.status if event.new_chat_member else None
    if old_status in (None, ChatMemberStatus.LEFT, ChatMemberStatus.BANNED) and new_status == ChatMemberStatus.MEMBER:
        user = event.new_chat_member.user
        await send_welcome_tag(client, event.chat.id, event.chat.title, user, reply_to_id=None)

# 2. Smart Group Chat Handler (Zero Self-Loop + Name Trigger + Memory + Casual Drop-in)
@Client.on_message(filters.text & filters.group & ~filters.command(["chatbot", "joinvc", "leavevc", "update", "panel", "addallsessions", "vcstatus"]), group=10)
async def handle_ai_mentions(client: Client, message: Message):
    if not message.from_user or message.from_user.is_bot:
        return

    from main import clients
    if not clients:
        return

    # CRITICAL FIX: Apni hi userbot IDs ke messages par kabhi reply na kare (Khud se baat band!)
    all_ubot_ids = set()
    ubot_profiles = {}
    for idx, ubot in enumerate(clients):
        try:
            me = await ubot.get_me()
            all_ubot_ids.add(me.id)
            full_n = f"{me.first_name or ''} {me.last_name or ''}".strip()
            ubot_profiles[idx] = (ubot, me, full_n)
        except Exception:
            pass

    if message.from_user.id in all_ubot_ids:
        return

    chat_id = message.chat.id
    chat_settings = await get_chat_settings(chat_id)
    responders = get_enabled_responders(clients, chat_settings)
    if not responders:
        return

    msg_lower = message.text.lower()
    replied_user_id = (
        message.reply_to_message.from_user.id
        if message.reply_to_message and message.reply_to_message.from_user
        else None
    )

    # Check karo kya kisi enabled girl session ko reply kiya hai ya uske naam se bulaya hai (tag ya bina tag ke)
    chosen_entry = None
    is_direct_call = False

    for idx, ubot in responders:
        if idx not in ubot_profiles:
            continue
        _, me, full_n = ubot_profiles[idx]

        # Direct reply to that girl ID
        if replied_user_id == me.id:
            chosen_entry = (idx, ubot, me, full_n)
            is_direct_call = True
            break

        # Mentioned by @username or Name (with or without tag)
        if me.username and f"@{me.username.lower()}" in msg_lower:
            chosen_entry = (idx, ubot, me, full_n)
            is_direct_call = True
            break

        name_triggers = clean_trigger_words(full_n)
        if any(re.search(rf"\b{re.escape(w)}\b", msg_lower) for w in name_triggers if w.isascii()):
            chosen_entry = (idx, ubot, me, full_n)
            is_direct_call = True
            break
        elif any(w in msg_lower for w in name_triggers if not w.isascii()):
            chosen_entry = (idx, ubot, me, full_n)
            is_direct_call = True
            break

    # Agar kisi ne naam nahi liya aur reply bhi nahi kiya -> har kisi ke text par reply nahi karegi!
    # Sirf beech-beech me (har 12 messages me 1 baar, kam se kam 2 min gap ke baad) naturally baat karegi
    if not is_direct_call:
        _casual_msg_counter[chat_id] += 1
        now = time.time()
        if _casual_msg_counter[chat_id] < 12 or (now - _last_casual_reply[chat_id]) < 120:
            return
        _casual_msg_counter[chat_id] = 0
        _last_casual_reply[chat_id] = now

        valid_entries = [
            (idx, ubot, *ubot_profiles[idx][1:])
            for idx, ubot in responders
            if idx in ubot_profiles
        ]
        if not valid_entries:
            return
        chosen_entry = random.choice(valid_entries)

    _, chosen_ubot, chosen_me, bot_full_name = chosen_entry

    try:
        mem_key = (chat_id, chosen_me.id, message.from_user.id)
        history = list(_chat_memory[mem_key])

        user_prompt = f"{message.from_user.first_name}: {message.text}"
        response = await ask_girl_ai(
            user_prompt,
            bot_full_name=bot_full_name,
            history=history,
            is_welcome=False
        )

        # Memory me save karo taaki purani baat yaad rahe
        _chat_memory[mem_key].append({"role": "user", "content": user_prompt})
        _chat_memory[mem_key].append({"role": "assistant", "content": response})

        sender_tag = f"[{message.from_user.first_name}](tg://user?id={message.from_user.id})"

        # Beech-beech me casual message karte waqt kabhi-kabhi kisi random member ko bhi tag kar sakti hai
        extra_tag = ""
        if not is_direct_call and random.random() < 0.35:
            try:
                recent_users = []
                async for m in client.get_chat_history(chat_id, limit=20):
                    if (
                        m.from_user
                        and not m.from_user.is_bot
                        and m.from_user.id not in all_ubot_ids
                        and m.from_user.id != message.from_user.id
                    ):
                        recent_users.append(m.from_user)
                if recent_users:
                    rnd_u = random.choice(recent_users)
                    extra_tag = f" kya bolte ho [{rnd_u.first_name}](tg://user?id={rnd_u.id})? 👀"
            except Exception:
                pass

        await chosen_ubot.send_message(
            chat_id,
            f"{sender_tag} {response}{extra_tag}",
            reply_to_message_id=message.id
        )
    except Exception as e:
        await notify_owner_once(client, str(e))
