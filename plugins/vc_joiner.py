import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from pytgcalls import PyTgCalls
from pytgcalls.types import AudioPiped
from pytgcalls.exceptions import AlreadyJoinedError
from database import is_auth

# Session Index -> PyTgCalls Instance
pytgcalls_instances = {}

# Session Index -> Active Chat ID (track rakhne ke liye kaunsi ID kis GC me hai)
active_vc_sessions = {}

def get_call_instance(client_instance, idx: int) -> PyTgCalls:
    if idx not in pytgcalls_instances:
        call_app = PyTgCalls(client_instance)
        pytgcalls_instances[idx] = call_app
    return pytgcalls_instances[idx]

@Client.on_message(filters.command("joinvc") & filters.group)
async def join_vc_handler(client: Client, message: Message):
    if not await is_auth(message.from_user.id):
        return
        
    from main import clients
    if not clients:
        return await message.reply("⚠️ Koi userbot session loaded nahi hai! Pehle `/create` ya `/addsession` karo.")

    chat_id = message.chat.id
    args = message.text.split()[1:]

    if not args:
        return await message.reply("📌 **Usage:**\n• `/joinvc 1 2 3` (specific IDs)\n• `/joinvc all` (saari IDs ek sath)")

    # Target session indices parse karna
    target_indices = []
    if args[0].lower() == "all":
        target_indices = list(range(len(clients)))
    else:
        for item in args:
            for num in item.replace(",", " ").split():
                if num.isdigit():
                    idx = int(num) - 1  # 1-based to 0-based index
                    if 0 <= idx < len(clients):
                        target_indices.append(idx)

    if not target_indices:
        return await message.reply(f"❌ Invalid index! Total active sessions: `{len(clients)}`")

    status_msg = await message.reply(f"⏳ **Target IDs ({len(target_indices)}) ko is group ki VC me join karwa rahe hain...**")
    
    joined_count = 0
    failed_count = 0

    # Dummy silent audio track taaki VC connection active rahe aur drop na ho
    dummy_stream = AudioPiped("http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4")

    for idx in target_indices:
        cli = clients[idx]
        call_app = get_call_instance(cli, idx)

        try:
            # Agar call app start nahi hai toh start karo
            if not call_app.is_connected:
                await call_app.start()

            # Agar ID pehle se kisi dusri GC me hai toh pehle wahan se leave karwao
            if idx in active_vc_sessions and active_vc_sessions[idx] != chat_id:
                try:
                    await call_app.leave_group_call(active_vc_sessions[idx])
                except Exception:
                    pass

            # Current group ki voice chat me join
            await call_app.join_group_call(chat_id, dummy_stream)
            active_vc_sessions[idx] = chat_id
            joined_count += 1
            await asyncio.sleep(1) # Flood wait bypass delay
            
        except AlreadyJoinedError:
            active_vc_sessions[idx] = chat_id
            joined_count += 1
        except Exception as e:
            failed_count += 1

    await status_msg.edit(
        f"✅ **VC Join Task Completed!**\n\n"
        f"• Group: **{message.chat.title}** (`{chat_id}`)\n"
        f"• Successfully Joined: `{joined_count}` IDs\n"
        f"• Failed: `{failed_count}`"
    )

@Client.on_message(filters.command("leavevc") & filters.group)
async def leave_vc_handler(client: Client, message: Message):
    if not await is_auth(message.from_user.id):
        return

    chat_id = message.chat.id
    args = message.text.split()[1:]
    
    left_count = 0
    status_msg = await message.reply("⏳ **IDs ko is group ki VC se leave karwa rahe hain...**")

    # Specific index ya sabhi IDs leave karwane ka option
    if args and args[0].lower() != "all":
        target_indices = [int(x) - 1 for x in args if x.isdigit()]
    else:
        # Default: Is group me jitni bhi IDs active hain sabko leave karwao
        target_indices = [idx for idx, cid in active_vc_sessions.items() if cid == chat_id]

    for idx in target_indices:
        if idx in pytgcalls_instances:
            call_app = pytgcalls_instances[idx]
            try:
                await call_app.leave_group_call(chat_id)
                active_vc_sessions.pop(idx, None)
                left_count += 1
            except Exception:
                pass

    await status_msg.edit(
        f"🚪 **VC Leave Task Completed!**\n\n"
        f"• Group: **{message.chat.title}**\n"
        f"• Left: `{left_count}` IDs"
    )
