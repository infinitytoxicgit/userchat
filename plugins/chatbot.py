import re
import time
import random
import aiohttp
from collections import defaultdict, deque
from pyrogram import Client, filters, raw
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
_welcomed_users = {}
_casual_msg_counter = defaultdict(int)
_last_casual_reply = defaultdict(float)
_last_active_girl = {}  # {chat_id: (bot_idx, timestamp)} - bina tag follow-up pakadne ke liye
_chat_memory = defaultdict(lambda: deque(maxlen=10))
_vc_raw_hooked = set()

def extract_name_tokens(full_name: str) -> list[str]:
    # "Jaanvi 🌻" -> ["jaanvi"]
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", full_name.lower()).strip()
    tokens = [t for t in cleaned.split() if len(t) >= 3]
    return tokens

def match_name_in_text(text: str, full_name: str, username: str = None) -> bool:
    text_l = text.lower()
    if username and f"@{username.lower()}" in text_l:
        return True
    clean_text = re.sub(r"[^a-zA-Z0-9\s]", " ", text_l)
    text_words = clean_text.split()
    tokens = extract_name_tokens(full_name)
    for tok in tokens:
        if tok in text_words or any(w.startswith(tok) or tok.startswith(w) for w in text_words if len(w) >= 4):
            return True
    return False

@Client.on_message(filters.command("chatbot") & filters.group)
async def toggle_chatbot(client: Client, message: Message):
    if message.sender_chat and message.sender_chat.id == message.chat.id:
        pass
    elif not message.from_user or not await is_auth(message.from_user.id):
        return

    from main import clients
    ensure_vc_chat_hooks(clients)

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
        return await message.reply("🔴 **AI Girl Chatbot disabled** for this group & Voice Chat.")

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
        f"• **Active In:** Group Chat + Voice Chat Live Messages 🎙️\n"
        f"• **Features:** Name Call + Follow-up Context + Memory + Request Welcome ✨"
    )

def build_girl_system_prompt(bot_full_name: str, is_welcome: bool = False, is_vc: bool = False) -> str:
    if is_welcome:
        return (
            f"You are {bot_full_name}, a sweet, playful Indian girl chatting in a Telegram group. "
            f"Your exact name is {bot_full_name}. "
            "Welcome the new member warmly in 1 short sentence (max 14 words) in natural Hinglish with 1 or 2 cute emojis (like 🌸, 😊, ✨, 💕). "
            "Never mention being an AI or bot."
        )
    if is_vc:
        return (
            f"You are {bot_full_name}, a real Indian girl currently sitting inside a Telegram Voice Chat. "
            f"Your exact display name is {bot_full_name}. "
            "Reply very briefly (max 8-12 words) in natural casual Hinglish with 1 or 2 expressive emojis (like 😂, 👀, 🥺, 🔥, ❤️, 🙈). "
            "Sound like a real girl texting in VC chat. Never say you are an AI."
        )
    return (
        f"You are {bot_full_name}, a cute, witty, real Indian girl chatting in a Telegram group. "
        f"Your exact display name is '{bot_full_name}'. Stay completely in character as {bot_full_name}. "
        "Remember the conversation history and reply in 1 short natural Hinglish/English sentence (max 15 words) with 1 or 2 varied emojis (😂, 👀, 🥺, 🙈, 💕, ✨, 😅). "
        "Do NOT repeat the same emojis every time, do NOT repeat user's text, and never say you are an AI or bot."
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
                    return "Hehe nice try, par main itni bhi bholi nahi hu 😜"
    except Exception:
        pass

    last_err = "UNKNOWN"
    for model_name in GROQ_FREE_MODELS:
        payload = {
            "model": model_name,
            "messages": messages_list,
            "temperature": 0.9,
            "max_tokens": 180
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

async def ask_girl_ai(prompt: str, bot_full_name: str, history: list = None, is_welcome: bool = False, is_vc: bool = False) -> str:
    key = str(CHATBOT_API_KEY or "").strip()
    if not key:
        raise Exception("NO_API_KEY_SET")

    sys_prompt = build_girl_system_prompt(bot_full_name, is_welcome=is_welcome, is_vc=is_vc)
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

# =====================================================================
# VOICE CHAT LIVE IN-CALL MESSAGES HANDLER (UpdateGroupCallMessage)
# =====================================================================
def ensure_vc_chat_hooks(clients):
    for idx, ubot in enumerate(clients):
        if id(ubot) in _vc_raw_hooked:
            continue
        _vc_raw_hooked.add(id(ubot))

        @ubot.on_raw_update()
        async def _on_vc_raw_update(cli, update, users, chats, _idx=idx):
            # Sirf VC ke andar bheje gaye live chat messages pakdo
            if not isinstance(update, raw.types.UpdateGroupCallMessage):
                return

            from main import clients as all_clients
            # Apni hi userbot IDs ke VC messages ignore karo
            my_ids = set()
            for c in all_clients:
                try:
                    m = await c.get_me()
                    my_ids.add(m.id)
                except Exception:
                    pass

            from_id = getattr(update.message, "from_id", None)
            sender_id = getattr(from_id, "user_id", None) if from_id else None
            if not sender_id or sender_id in my_ids:
                return

            msg_obj = getattr(update.message, "message", None)
            msg_text = getattr(msg_obj, "message", "") if msg_obj else ""
            if not msg_text.strip():
                return

            # Group chat_id resolve karo
            chat_id = None
            for cid in chats:
                chat_id = int(f"-100{cid}") if cid > 0 else cid
                break
            if not chat_id:
                return

            chat_settings = await get_chat_settings(chat_id)
            responders = get_enabled_responders(all_clients, chat_settings)
            if not responders:
                return

            # Sirf pehla enabled responder hi VC message handle kare taaki duplicate reply na ho
            if responders[0][0] != _idx:
                return

            # Check karo kya kisi enabled girl ka naam liya gaya hai
            chosen_ubot = None
            for r_idx, r_cli in responders:
                try:
                    r_me = await r_cli.get_me()
                    r_name = f"{r_me.first_name or ''} {r_me.last_name or ''}".strip()
                    if match_name_in_text(msg_text, r_name, r_me.username):
                        chosen_ubot = r_cli
                        break
                except Exception:
                    pass

            if not chosen_ubot:
                _, chosen_ubot = random.choice(responders)

            try:
                me = await chosen_ubot.get_me()
                bot_full_name = f"{me.first_name or ''} {me.last_name or ''}".strip() or "Cutie"
                sender_user = users.get(sender_id)
                sender_name = getattr(sender_user, "first_name", "Friend") if sender_user else "Friend"

                # Agar sirf emoji bheja hai toh cute emoji/short reply bhejo
                if len(msg_text.strip()) <= 3 and not any(c.isalnum() for c in msg_text):
                    reply_text = random.choice(["🙈✨", "😂🔥", "❤️👀", "🥺💕", "Hii 👀✨"])
                else:
                    reply_text = await ask_girl_ai(
                        f"{sender_name} in Voice Chat: {msg_text}",
                        bot_full_name=bot_full_name,
                        is_vc=True
                    )

                # VC ke andar live message bhejo
                await chosen_ubot.invoke(
                    raw.functions.phone.SendGroupCallMessage(
                        call=update.call,
                        random_id=random.randint(10000, 999999999),
                        message=raw.types.TextWithEntities(text=reply_text, entities=[])
                    )
                )
            except Exception:
                pass

# =====================================================================
# WELCOME HANDLER (Direct Join + Join Request Approve)
# =====================================================================
async def send_welcome_tag(client: Client, chat_id: int, chat_title: str, user, reply_to_id: int = None):
    if not user or user.is_bot:
        return

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
            f"{user_tag} {welcome_reply}",
            reply_to_message_id=reply_to_id
        )
    except Exception as e:
        await notify_owner_once(client, str(e))

@Client.on_message(filters.new_chat_members & filters.group, group=9)
async def welcome_on_service_join(client: Client, message: Message):
    for member in message.new_chat_members:
        await send_welcome_tag(client, message.chat.id, message.chat.title, member, reply_to_id=message.id)

@Client.on_chat_member_updated(filters.group, group=9)
async def welcome_on_request_approved(client: Client, event: ChatMemberUpdated):
    old_status = event.old_chat_member.status if event.old_chat_member else None
    new_status = event.new_chat_member.status if event.new_chat_member else None
    if old_status in (None, ChatMemberStatus.LEFT, ChatMemberStatus.BANNED) and new_status == ChatMemberStatus.MEMBER:
        user = event.new_chat_member.user
        await send_welcome_tag(client, event.chat.id, event.chat.title, user, reply_to_id=None)

# =====================================================================
# GROUP TEXT HANDLER (Name Call + Follow-up Context + Occasional Tag)
# =====================================================================
@Client.on_message(filters.text & filters.group & ~filters.command(["chatbot", "joinvc", "leavevc", "update", "panel", "addallsessions", "vcstatus"]), group=10)
async def handle_ai_mentions(client: Client, message: Message):
    if not message.from_user or message.from_user.is_bot:
        return

    from main import clients
    if not clients:
        return

    ensure_vc_chat_hooks(clients)

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

    replied_user_id = (
        message.reply_to_message.from_user.id
        if message.reply_to_message and message.reply_to_message.from_user
        else None
    )

    chosen_entry = None
    is_direct_call = False

    # 1. Check direct reply or name call (tag ke saath ya bina tag ke)
    for idx, ubot in responders:
        if idx not in ubot_profiles:
            continue
        _, me, full_n = ubot_profiles[idx]

        if replied_user_id == me.id:
            chosen_entry = (idx, ubot, me, full_n)
            is_direct_call = True
            break

        if match_name_in_text(message.text, full_n, me.username):
            chosen_entry = (idx, ubot, me, full_n)
            is_direct_call = True
            break

    # 2. Check Active Conversation Follow-up (agar pichhle 75 sec me kisi girl ne baat ki hai aur user bina tag follow-up bhej raha hai)
    now = time.time()
    if not is_direct_call and replied_user_id is None and chat_id in _last_active_girl:
        last_idx, last_ts = _last_active_girl[chat_id]
        if (now - last_ts) <= 75 and last_idx in ubot_profiles and any(r_idx == last_idx for r_idx, _ in responders):
            # Agar message kisi aur member ko nahi bulaya gaya toh active girl reply karegi
            _, ubot, me, full_n = ubot_profiles[last_idx]
            chosen_entry = (last_idx, ubot, me, full_n)
            is_direct_call = True

    # 3. Casual beech-beech me bolna (har 10 messages me 1 baar, kam se kam 2 min gap ke baad)
    if not is_direct_call:
        _casual_msg_counter[chat_id] += 1
        if _casual_msg_counter[chat_id] < 10 or (now - _last_casual_reply[chat_id]) < 120:
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

    chosen_idx, chosen_ubot, chosen_me, bot_full_name = chosen_entry
    _last_active_girl[chat_id] = (chosen_idx, now)

    try:
        mem_key = (chat_id, chosen_me.id, message.from_user.id)
        history = list(_chat_memory[mem_key])

        user_prompt = f"{message.from_user.first_name}: {message.text}"
        response = await ask_girl_ai(
            user_prompt,
            bot_full_name=bot_full_name,
            history=history,
            is_welcome=False,
            is_vc=False
        )

        _chat_memory[mem_key].append({"role": "user", "content": user_prompt})
        _chat_memory[mem_key].append({"role": "assistant", "content": response})

        # Kabhi-kabhi (25% chance) hi name tag karegi, har reply me tag spam nahi karegi
        if random.random() < 0.25:
            sender_tag = f"[{message.from_user.first_name}](tg://user?id={message.from_user.id}) "
        else:
            sender_tag = ""

        # Casual drop-in ke waqt kabhi-kabhi group ke kisi random member ko bhi tag kar sakti hai
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
            f"{sender_tag}{response}{extra_tag}",
            reply_to_message_id=message.id
        )
    except Exception as e:
        await notify_owner_once(client, str(e))
