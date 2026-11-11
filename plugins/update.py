import os
import sys
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from config import OWNER_ID
from database import is_auth

@Client.on_message(filters.command("update") & filters.private)
@Client.on_message(filters.command("update") & filters.group)
async def git_update(client: Client, message: Message):
    # Sirf Master Owner ya Authorized Admins ke liye
    if not await is_auth(message.from_user.id):
        return

    # User ko DM aur chat dono jagah notice
    status_msg = await message.reply("🔄 **Checking for upstream updates via Git...**")
    
    # Git pull process execute
    process = await asyncio.create_subprocess_shell(
        "git pull",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    output = stdout.decode().strip()
    errors = stderr.decode().strip()

    if "Already up to date." in output:
        msg_text = "✅ **Bot is already up-to-date with upstream branch.**\nKoi new changes nahi hain."
        await status_msg.edit(msg_text)
        if message.chat.id != OWNER_ID:
            await client.send_message(OWNER_ID, msg_text)
        return

    # Agar new commits pull hue hain
    update_report = (
        "🚀 **Git Pull Successful!**\n\n"
        f"**Git Output:**\n`{output}`\n\n"
        "📦 Installing any new dependencies & restarting core processes..."
    )
    await status_msg.edit(update_report)
    
    # Owner ke DM me alert
    if message.chat.id != OWNER_ID:
        await client.send_message(OWNER_ID, update_report)

    # Auto requirements install check
    req_proc = await asyncio.create_subprocess_shell(
        "pip install --no-cache-dir -r requirements.txt",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    await req_proc.communicate()

    # Restart bot instance gracefully
    restart_alert = "♻️ **Restarting Bot Engine now... Reconnecting all sessions.**"
    await client.send_message(OWNER_ID, restart_alert)

    # Process replace
    os.execl(sys.executable, sys.executable, "main.py")
