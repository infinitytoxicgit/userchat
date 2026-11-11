

from pyrogram import Client, filters
from pyrogram.types import Message
from config import OWNER_ID
from database import is_auth, add_auth, remove_auth, get_all_auth

@Client.on_message(filters.command("auth") & filters.user(OWNER_ID))
async def auth_add_cmd(client: Client, message: Message):
    if len(message.command) < 2 and not message.reply_to_message:
        return await message.reply("Usage: `/auth @user` ya `/auth [user_id]`")
    user_id = message.reply_to_message.from_user.id if message.reply_to_message else int(message.command[1])
    await add_auth(user_id)
    await message.reply(f"User `{user_id}` ko auth list me add kar diya hai.")

@Client.on_message(filters.command("delauth") & filters.user(OWNER_ID))
async def auth_del_cmd(client: Client, message: Message):
    if len(message.command) < 2 and not message.reply_to_message:
        return await message.reply("Usage: `/delauth @user` ya `/delauth [user_id]`")
    user_id = message.reply_to_message.from_user.id if message.reply_to_message else int(message.command[1])
    await remove_auth(user_id)
    await message.reply(f"User `{user_id}` ko auth list se hata diya hai.")

@Client.on_message(filters.command("authlist"))
async def auth_list_cmd(client: Client, message: Message):
    if not await is_auth(message.from_user.id):
        return
    auths = await get_all_auth()
    text = "**Authorized Users:**\n"
    text += f"- `{OWNER_ID}` (Master Owner)\n"
    for uid in auths:
        text += f"- `{uid}`\n"
    await message.reply(text)

@Client.on_message(filters.command("stats"))
async def stats_cmd(client: Client, message: Message):
    if not await is_auth(message.from_user.id):
        return
    from main import clients
    from database import chats_col
    total_chats = await chats_col.count_documents({})
    await message.reply(
        f"**Bot System Stats**\n\n"
        f"Total Active Sessions: `{len(clients)}`\n"
        f"Configured Chats: `{total_chats}`"
    )
