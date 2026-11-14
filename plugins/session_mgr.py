import time
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from config import API_ID, API_HASH, OWNER_ID
from database import is_auth, save_session, delete_session, get_all_sessions, sessions_col

@Client.on_message(filters.command("sessions"))
async def list_all_sessions_cmd(client: Client, message: Message):
    if not message.from_user or not await is_auth(message.from_user.id):
        return

    from main import clients
    db_docs = await sessions_col.find({}).to_list(length=100)

    if not db_docs and not clients:
        return await message.reply("📭 Database aur Memory dono me abhi koi session nahi hai.")

    live_strings = set()
    text = "📊 **ALL SESSIONS STATUS (Active & Deactivated)**\n────────────────────────\n\n"

    text += f"🟢 **Active in RAM ({len(clients)}):**\n"
    if clients:
        for idx, cli in enumerate(clients, 1):
            try:
                me = await cli.get_me()
                s_str = await cli.export_session_string()
                live_strings.add(s_str)
                text += f"`[{idx}]` **{me.first_name}** (`{me.id}`) | @{me.username or 'NoUser'} — **ACTIVE**\n"
            except Exception:
                text += f"`[{idx}]` Unknown Session — **ERROR**\n"
    else:
        text += "• Koi live session active nahi hai.\n"

    text += f"\n🗄️ **Saved in Database ({len(db_docs)}):**\n"
    for idx, doc in enumerate(db_docs, 1):
        s_str = doc.get("session", "")
        phone = doc.get("phone") or "Unknown Phone"
        status = "🟢 Active" if s_str in live_strings else "🔴 Deactivated / Dead"
        short_code = f"{s_str[:12]}...{s_str[-8:]}" if len(s_str) > 20 else s_str
        text += f"`[{idx}]` `{phone}` | `{short_code}` — **{status}**\n"

    text += "\n────────────────────────\n• Dead sessions saaf karne ke liye: `/cleansessions`\n• Specific DB session hatane ke liye: `/delsession <number>`"
    await message.reply(text)

@Client.on_message(filters.command("addsession"))
async def add_session_string(client: Client, message: Message):
    if not message.from_user or not await is_auth(message.from_user.id):
        return
    if len(message.command) < 2:
        return await message.reply("📌 **Usage:** `/addsession <pyrogram_session_string>`")
    session_str = message.command[1].strip()

    try:
        unique_name = f"ubot_{int(time.time())}"
        new_cli = Client(unique_name, api_id=API_ID, api_hash=API_HASH, session_string=session_str, in_memory=True)
        await new_cli.start()
        me = await new_cli.get_me()

        await save_session(session_str, me.phone_number or "")
        from main import clients
        clients.append(new_cli)

        await message.reply(
            f"✅ **Session Active!**\n"
            f"• **Account:** {me.first_name} (`{me.id}`)\n"
            f"• **ID Number:** `#{len(clients)}`"
        )
    except Exception as e:
        await message.reply(f"❌ **Invalid Session:** `{e}`")

@Client.on_message(filters.command("create"))
async def generate_session_auto(client: Client, message: Message):
    if not message.from_user or not await is_auth(message.from_user.id):
        return

    chat_id = message.chat.id
    user_id = message.from_user.id

    try:
        phone_msg = await client.ask(chat_id, "📱 Apna phone number bhejo country code ke sath (e.g. `+919876543210`):", timeout=120)
    except Exception:
        return await message.reply("⏳ Timeout ho gaya. Dubara `/create` run karo.")

    phone = phone_msg.text.strip()
    temp_cli = Client(f"auto_gen_{int(time.time())}", api_id=API_ID, api_hash=API_HASH, in_memory=True)
    await temp_cli.connect()

    try:
        code_hash = await temp_cli.send_code(phone)
    except Exception as e:
        await temp_cli.disconnect()
        return await message.reply(f"❌ **OTP bhejne me dikkat aayi:** `{e}`")

    try:
        otp_msg = await client.ask(chat_id, "📩 Telegram pe aaya OTP bhejo (e.g. `1 2 3 4 5` ya `12345`):", timeout=180)
    except Exception:
        await temp_cli.disconnect()
        return await message.reply("⏳ Timeout ho gaya.")

    otp = otp_msg.text.replace(" ", "").strip()
    try:
        await temp_cli.sign_in(phone, code_hash.phone_code_hash, otp)
    except Exception as e:
        if "SESSION_PASSWORD_NEEDED" in str(e):
            try:
                pwd_msg = await client.ask(chat_id, "🔐 2-Step Verification password bhejo:", timeout=120)
                await temp_cli.check_password(pwd_msg.text.strip())
            except Exception as pwd_err:
                await temp_cli.disconnect()
                return await message.reply(f"❌ **2FA Password Failed:** `{pwd_err}`")
        else:
            await temp_cli.disconnect()
            return await message.reply(f"❌ **Login failed:** `{e}`")

    me = await temp_cli.get_me()
    string_session = await temp_cli.export_session_string()
    await temp_cli.disconnect()
    await asyncio.sleep(2)

    await save_session(string_session, phone)
    from main import clients
    new_cli = Client(f"ubot_{int(time.time())}", api_id=API_ID, api_hash=API_HASH, session_string=string_session, in_memory=True)
    await new_cli.start()
    clients.append(new_cli)

    session_dm_text = (
        f"🔐 **PYROGRAM V2 STRING SESSION**\n\n"
        f"• **Account:** {me.first_name} (`{me.id}`)\n"
        f"• **Phone:** `{phone}`\n\n"
        f"**String Session (Tap to Copy):**\n"
        f"`{string_session}`\n\n"
        f"📌 **Direct Add Command:**\n"
        f"`/addsession {string_session}`"
    )

    try:
        await client.send_message(user_id, session_dm_text)
    except Exception:
        pass

    if user_id != OWNER_ID:
        try:
            await client.send_message(OWNER_ID, session_dm_text)
        except Exception:
            pass

    try:
        await new_cli.send_message("me", session_dm_text)
    except Exception:
        pass

    await message.reply(
        f"✅ **Session Create & Active ho gaya!**\n\n"
        f"• **Account:** {me.first_name} (`{me.id}`)\n"
        f"• **ID Slot:** `#{len(clients)}`\n"
        f"📩 **Pyrogram v2 String Session aapke DM aur Saved Messages me bhej diya gaya hai!**"
    )

@Client.on_message(filters.command("delsession"))
async def del_session_cmd(client: Client, message: Message):
    if not message.from_user or not await is_auth(message.from_user.id):
        return

    from main import clients
    db_docs = await sessions_col.find({}).to_list(length=100)

    if not db_docs and not clients:
        return await message.reply("⚠️ Database aur Memory dono me koi session nahi hai.")

    if len(message.command) < 2 or not message.command[1].isdigit():
        return await message.reply(f"📌 **Usage:** `/delsession <number (1 to {len(db_docs)})>`\nPehle `/sessions` bhej kar number check karo.")

    idx = int(message.command[1]) - 1
    if 0 <= idx < len(db_docs):
        target_session = db_docs[idx].get("session")
        # Agar ye session RAM me bhi active hai toh wahan se bhi stop karo
        for i, cli in enumerate(list(clients)):
            try:
                if await cli.export_session_string() == target_session:
                    clients.pop(i)
                    await cli.stop()
                    break
            except Exception:
                pass
        await delete_session(target_session)
        await message.reply(f"🗑️ Session `#{idx + 1}` ko Database aur Memory dono se delete kar diya gaya.")
    else:
        await message.reply(f"❌ Invalid number! Total saved sessions: `{len(db_docs)}`")

@Client.on_message(filters.command("cleansessions"))
async def clean_dead_sessions(client: Client, message: Message):
    if not message.from_user or not await is_auth(message.from_user.id):
        return
    all_s = await get_all_sessions()
    removed = 0
    for s in all_s:
        try:
            test = Client(f"chk_{int(time.time())}", api_id=API_ID, api_hash=API_HASH, session_string=s, in_memory=True)
            await test.start()
            await test.stop()
        except Exception:
            await delete_session(s)
            removed += 1
    await message.reply(f"🧹 **Database Cleanup Done!**\n• Dead/Expired Sessions Removed: `{removed}`")
