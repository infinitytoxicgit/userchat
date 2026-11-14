from pyrogram import Client, filters
from pyrogram.types import Message
from config import OWNER_ID
from database import is_auth, add_auth, remove_auth, get_all_auth

async def resolve_target_user(client: Client, message: Message):
    if message.reply_to_message and message.reply_to_message.from_user:
        user = message.reply_to_message.from_user
        return user.id, user.mention

    if len(message.command) < 2:
        return None, None

    target = message.command[1].strip()
    try:
        user_id = int(target)
        try:
            user = await client.get_users(user_id)
            return user.id, user.mention
        except Exception:
            return user_id, f"`{user_id}`"
    except ValueError:
        try:
            user = await client.get_users(target)
            return user.id, user.mention
        except Exception as e:
            return "ERROR", str(e)

@Client.on_message(filters.command(["auth", "addauth"]) & filters.user(OWNER_ID))
async def auth_add_cmd(client: Client, message: Message):
    user_id, mention = await resolve_target_user(client, message)

    if not user_id:
        return await message.reply("📌 **Usage:** `/auth @username`, `/auth [user_id]`, ya kisi user ke message par reply karo.")

    if user_id == "ERROR":
        return await message.reply(f"❌ User nahi mila! Make sure user ne bot start kiya ho ya valid ID ho.\n`{mention}`")

    await add_auth(user_id)
    await message.reply(f"✅ {mention} (`{user_id}`) ko auth list me add kar diya hai.")

@Client.on_message(filters.command(["delauth", "removeauth"]) & filters.user(OWNER_ID))
async def auth_del_cmd(client: Client, message: Message):
    user_id, mention = await resolve_target_user(client, message)

    if not user_id:
        return await message.reply("📌 **Usage:** `/delauth @username`, `/delauth [user_id]`, ya reply karo.")

    if user_id == "ERROR":
        return await message.reply(f"❌ Invalid user!\n`{mention}`")

    await remove_auth(user_id)
    await message.reply(f"🗑️ {mention} (`{user_id}`) ko auth list se hata diya hai.")

@Client.on_message(filters.command("authlist"))
async def auth_list_cmd(client: Client, message: Message):
    if not await is_auth(message.from_user.id):
        return
    auths = await get_all_auth()
    text = "👑 **Authorized Users:**\n\n"
    text += f"• `{OWNER_ID}` **(Master Owner)**\n"
    for uid in auths:
        if uid != OWNER_ID:
            try:
                u = await client.get_users(uid)
                text += f"• {u.mention} (`{uid}`)\n"
            except Exception:
                text += f"• `{uid}`\n"
    await message.reply(text)

@Client.on_message(filters.command("stats"))
async def stats_cmd(client: Client, message: Message):
    if not await is_auth(message.from_user.id):
        return
    from main import clients
    from database import chats_col
    total_chats = await chats_col.count_documents({})
    await message.reply(
        f"📊 **Bot System Stats**\n\n"
        f"• **Total Active Sessions:** `{len(clients)}`\n"
        f"• **Configured Chats:** `{total_chats}`"
    )
