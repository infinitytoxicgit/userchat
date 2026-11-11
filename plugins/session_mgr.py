import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from config import API_ID, API_HASH
from database import is_auth, save_session, delete_session, get_all_sessions

@Client.on_message(filters.command("addsession"))
async def add_session_string(client: Client, message: Message):
    if not await is_auth(message.from_user.id):
        return
    if len(message.command) < 2:
        return await message.reply("Usage: `/addsession <pyrogram_session_string>`")
    session_str = message.command[1]
    
    try:
        test_cli = Client("temp_test", api_id=API_ID, api_hash=API_HASH, session_string=session_str, in_memory=True)
        await test_cli.start()
        me = await test_cli.get_me()
        await test_cli.stop()
        
        await save_session(session_str, me.phone_number or "")
        from main import clients
        new_cli = Client(f"ubot_{len(clients)}", api_id=API_ID, api_hash=API_HASH, session_string=session_str, in_memory=True)
        await new_cli.start()
        clients.append(new_cli)
        
        await message.reply(f"Session successfully active ho gaya!\nAccount: **{me.first_name}** (`{me.id}`)")
    except Exception as e:
        await message.reply(f"Invalid Session: `{e}`")

@Client.on_message(filters.command("create"))
async def generate_session_auto(client: Client, message: Message):
    if not await is_auth(message.from_user.id):
        return
    
    chat_id = message.chat.id
    try:
        phone_msg = await client.ask(chat_id, "Apna phone number bhejo country code ke sath (e.g. `+919876543210`):", timeout=120)
    except:
        return await message.reply("Timeout ho gaya. Dubara `/create` run karo.")
    
    phone = phone_msg.text.strip()
    temp_cli = Client("auto_gen", api_id=API_ID, api_hash=API_HASH, in_memory=True)
    await temp_cli.connect()
    
    try:
        code_hash = await temp_cli.send_code(phone)
    except Exception as e:
        await temp_cli.disconnect()
        return await message.reply(f"OTP bhejne me dikkat aayi: `{e}`")
    
    try:
        otp_msg = await client.ask(chat_id, "Telegram pe aaya OTP bhejo format me: `1 2 3 4 5` ya normal digits:", timeout=180)
    except:
        await temp_cli.disconnect()
        return await message.reply("Timeout ho gaya.")
    
    otp = otp_msg.text.replace(" ", "").strip()
    try:
        await temp_cli.sign_in(phone, code_hash.phone_code_hash, otp)
    except Exception as e:
        # Check if 2FA required
        if "SESSION_PASSWORD_NEEDED" in str(e):
            pwd_msg = await client.ask(chat_id, "2-Step Verification password bhejo:", timeout=120)
            await temp_cli.check_password(pwd_msg.text.strip())
        else:
            await temp_cli.disconnect()
            return await message.reply(f"Login failed: `{e}`")
            
    string_session = await temp_cli.export_session_string()
    await temp_cli.disconnect()
    
    await save_session(string_session, phone)
    from main import clients
    new_cli = Client(f"ubot_{len(clients)}", api_id=API_ID, api_hash=API_HASH, session_string=string_session, in_memory=True)
    await new_cli.start()
    clients.append(new_cli)
    
    await message.reply("Session successfully create and database me save ho gaya!")

@Client.on_message(filters.command("delsession"))
async def del_session_cmd(client: Client, message: Message):
    if not await is_auth(message.from_user.id):
        return
    from main import clients
    if len(message.command) < 2:
        return await message.reply(f"Usage: `/delsession <client_index (0 to {len(clients)-1})>`")
    idx = int(message.command[1])
    if 0 <= idx < len(clients):
        cli = clients.pop(idx)
        s_str = await cli.export_session_string()
        await cli.stop()
        await delete_session(s_str)
        await message.reply(f"Client index `{idx}` remove aur disconnect kar diya gaya.")
    else:
        await message.reply("Invalid index.")
