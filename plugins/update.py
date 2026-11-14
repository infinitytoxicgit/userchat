import os
import sys
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from config import OWNER_ID, UPSTREAM_BRANCH
from database import is_auth

@Client.on_message(filters.command("update") & (filters.private | filters.group))
async def git_update(client: Client, message: Message):
    # Anonymous admin check (agar group se anonymous admin ne bheja ho)
    if message.sender_chat and message.sender_chat.id == message.chat.id:
        pass
    elif not message.from_user or not await is_auth(message.from_user.id):
        return

    status_msg = await message.reply("🔄 **Checking for upstream updates via Git...**")

    # Purana commit hash check karo
    old_proc = await asyncio.create_subprocess_shell(
        "git rev-parse --short HEAD",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    old_out, _ = await old_proc.communicate()
    old_commit = old_out.decode().strip()

    # Fetch aur Hard Reset taaki local edits kabhi conflict na karein
    pull_cmd = f"git fetch origin {UPSTREAM_BRANCH} && git reset --hard origin/{UPSTREAM_BRANCH}"
    process = await asyncio.create_subprocess_shell(
        pull_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    errors = stderr.decode().strip()

    if process.returncode != 0:
        return await status_msg.edit(f"❌ **Git Update Failed:**\n`{errors}`")

    # Naya commit hash aur message check karo
    new_proc = await asyncio.create_subprocess_shell(
        "git log -1 --oneline",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    new_out, _ = await new_proc.communicate()
    latest_log = new_out.decode().strip()
    new_commit = latest_log.split()[0] if latest_log else ""

    if old_commit == new_commit:
        msg_text = f"✅ **Bot is already up-to-date!**\n**Current Commit:** `{latest_log}`"
        await status_msg.edit(msg_text)
        if message.chat.id != OWNER_ID:
            await client.send_message(OWNER_ID, msg_text)
        return

    update_report = (
        "🚀 **Git Update Successful!**\n\n"
        f"**Updated:** `{old_commit}..{new_commit}`\n"
        f"**Latest:** `{latest_log}`\n\n"
        "📦 Installing any new dependencies & restarting core processes..."
    )
    await status_msg.edit(update_report)

    if message.chat.id != OWNER_ID:
        await client.send_message(OWNER_ID, update_report)

    # Auto requirements install
    req_proc = await asyncio.create_subprocess_shell(
        f"{sys.executable} -m pip install --no-cache-dir -r requirements.txt",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    await req_proc.communicate()

    await client.send_message(OWNER_ID, "♻️ **Restarting Bot Engine now... Reconnecting all sessions.**")

    # Process replace with active venv python
    os.execl(sys.executable, sys.executable, "main.py")
