import os
import asyncio
import subprocess
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import UserAlreadyParticipant
from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream
from database import is_auth

pytgcalls_instances = {}
started_calls = set()
active_vc_sessions = {}

SILENT_AUDIO = "silence.mp3"

def ensure_silent_audio():
    if not os.path.exists(SILENT_AUDIO):
        subprocess.run(
            ["ffmpeg", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", "5", "-q:a", "9", "-acodec", "libmp3lame", SILENT_AUDIO, "-y"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

def get_call_instance(client_instance, idx: int) -> PyTgCalls:
    if idx not in pytgcalls_instances:
        pytgcalls_instances[idx] = PyTgCalls(client_instance)
    return pytgcalls_instances[idx]

@Client.on_message(filters.command("joinvc") & filters.group)
async def join_vc_handler(client: Client, message: Message):
    if not message.from_user or not await is_auth(message.from_user.id):
        return

    from main import clients
    if not clients:
        return await message.reply("⚠️ Koi userbot session loaded nahi hai! Pehle `/create` ya `/addsession` karo.")

    chat_id = message.chat.id
    args = message.text.split()[1:]

    if not args:
        return await message.reply(
            "📌 **Usage:**\n"
            "• `/joinvc 1 2 3` — Specific IDs ko VC me bhejne ke liye\n"
            "• `/joinvc all` — Sabhi connected IDs ko ek sath VC me bhejne ke liye\n"
            "• `/vcstatus` — Kaunsi ID kis VC me hai check karne ke liye"
        )

    target_indices = []
    if args[0].lower() == "all":
        target_indices = list(range(len(clients)))
    else:
        for item in args:
            for num in item.replace(",", " ").split():
                if num.isdigit():
                    idx = int(num) - 1
                    if 0 <= idx < len(clients) and idx not in target_indices:
                        target_indices.append(idx)

    if not target_indices:
        return await message.reply(f"❌ Invalid ID number! Total active sessions: `{len(clients)}`")

    ensure_silent_audio()
    status_msg = await message.reply(f"⏳ **Target IDs ({len(target_indices)}) ko is group ki VC me join karwa rahe hain...**")

    joined_list = []
    failed_list = []

    stream = MediaStream(
        SILENT_AUDIO,
        video_flags=MediaStream.Flags.IGNORE
    )

    for idx in target_indices:
        cli = clients[idx]
        call_app = get_call_instance(cli, idx)

        try:
            # Agar userbot group me nahi hai toh public username se join karne ki koshish kare
            if message.chat.username:
                try:
                    await cli.join_chat(message.chat.username)
                except UserAlreadyParticipant:
                    pass
                except Exception:
                    pass

            if idx not in started_calls:
                await call_app.start()
                started_calls.add(idx)

            # Agar ID pehle se kisi dusri GC me hai toh wahan se leave karwao
            if idx in active_vc_sessions and active_vc_sessions[idx] != chat_id:
                try:
                    await call_app.leave_call(active_vc_sessions[idx])
                except Exception:
                    pass

            await call_app.play(chat_id, stream)
            active_vc_sessions[idx] = chat_id
            joined_list.append(f"`#{idx + 1}`")
            await asyncio.sleep(1.2)

        except Exception as e:
            err_name = type(e).__name__
            failed_list.append(f"`#{idx + 1}` ({err_name})")

    report = (
        f"✅ **VC Join Task Completed!**\n\n"
        f"• **Group:** {message.chat.title} (`{chat_id}`)\n"
        f"• **Joined ({len(joined_list)}):** {', '.join(joined_list) if joined_list else 'None'}\n"
        f"• **Failed ({len(failed_list)}):** {', '.join(failed_list) if failed_list else 'None'}"
    )
    await status_msg.edit(report)

@Client.on_message(filters.command("leavevc") & filters.group)
async def leave_vc_handler(client: Client, message: Message):
    if not message.from_user or not await is_auth(message.from_user.id):
        return

    chat_id = message.chat.id
    args = message.text.split()[1:]

    left_list = []
    status_msg = await message.reply("⏳ **IDs ko is group ki VC se leave karwa rahe hain...**")

    if args and args[0].lower() != "all":
        target_indices = [int(x) - 1 for x in args if x.isdigit()]
    else:
        target_indices = [idx for idx, cid in active_vc_sessions.items() if cid == chat_id]

    for idx in target_indices:
        if idx in pytgcalls_instances:
            call_app = pytgcalls_instances[idx]
            try:
                await call_app.leave_call(chat_id)
                active_vc_sessions.pop(idx, None)
                left_list.append(f"`#{idx + 1}`")
            except Exception:
                active_vc_sessions.pop(idx, None)

    await status_msg.edit(
        f"🚪 **VC Leave Task Completed!**\n\n"
        f"• **Group:** {message.chat.title}\n"
        f"• **Left ({len(left_list)}):** {', '.join(left_list) if left_list else 'None'}"
    )

@Client.on_message(filters.command("vcstatus"))
async def vc_status_handler(client: Client, message: Message):
    if not message.from_user or not await is_auth(message.from_user.id):
        return

    if not active_vc_sessions:
        return await message.reply("📴 Abhi koi bhi userbot ID kisi Voice Chat me active nahi hai.")

    lines = ["🎙️ **Active VC Connections:**\n"]
    for idx, cid in active_vc_sessions.items():
        lines.append(f"• **ID #{idx + 1}** ➔ Chat `{cid}`")

    await message.reply("\n".join(lines))
