from pyrogram import Client, filters
from pyrogram.types import ChatMemberUpdated, Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ChatMemberStatus
from database import is_auth, get_chat_settings, update_chat_settings

@Client.on_message(filters.command("welcome"))
async def welcome_toggle(client: Client, message: Message):
    if not await is_auth(message.from_user.id):
        return
    if len(message.command) < 2:
        return await message.reply("Usage: `/welcome on` ya `/welcome disable`")
    action = message.command[1].lower()
    if action in ["on", "enable"]:
        await update_chat_settings(message.chat.id, "welcome", True)
        await message.reply("Welcome system **ON** ho gaya (Auto-accept OFF hai, sirf manual approve/join par message jayega).")
    elif action in ["off", "disable"]:
        await update_chat_settings(message.chat.id, "welcome", False)
        await message.reply("Welcome system **DISABLED** ho gaya.")

@Client.on_message(filters.command("editwelcomemessage"))
async def edit_welcome_cmd(client: Client, message: Message):
    if not await is_auth(message.from_user.id):
        return
    if len(message.text.split(None, 1)) < 2:
        return await message.reply(
            "**Usage:** `/editwelcomemessage <message> | <Button Text> - <Button URL>`\n\n"
            "**Example:**\n"
            "`/editwelcomemessage Welcome {mention} to our group! | Join Channel - https://t.me/telegram`\n\n"
            "**Tags:** `{mention}`, `{name}`, `{id}`\n"
            "*(Premium emojis aur quotes bhi direct paste kar sakte ho)*"
        )
    
    raw_input = message.text.split(None, 1)[1]
    
    if "|" in raw_input and "-" in raw_input.split("|", 1)[1]:
        msg_part, btn_part = raw_input.split("|", 1)
        btn_text, btn_url = btn_part.split("-", 1)
        await update_chat_settings(message.chat.id, "welcome_msg", msg_part.strip())
        await update_chat_settings(message.chat.id, "welcome_btn_text", btn_text.strip())
        await update_chat_settings(message.chat.id, "welcome_btn_url", btn_url.strip())
    else:
        await update_chat_settings(message.chat.id, "welcome_msg", raw_input.strip())
        await update_chat_settings(message.chat.id, "welcome_btn_text", "")
        await update_chat_settings(message.chat.id, "welcome_btn_url", "")

    await message.reply("✅ Welcome template aur button update ho gaya!")

@Client.on_chat_member_updated()
async def welcome_on_member_join(client: Client, update: ChatMemberUpdated):
    if not update.new_chat_member:
        return

    old_status = update.old_chat_member.status if update.old_chat_member else None
    new_status = update.new_chat_member.status

    if old_status in [None, ChatMemberStatus.LEFT, ChatMemberStatus.RESTRICTED] and new_status == ChatMemberStatus.MEMBER:
        chat_id = update.chat.id
        user = update.new_chat_member.user
        if user.is_bot:
            return

        settings = await get_chat_settings(chat_id)
        if settings.get("welcome", False):
            raw_msg = settings.get("welcome_msg", "Welcome {mention}!")
            formatted = raw_msg.replace("{mention}", f"[{user.first_name}](tg://user?id={user.id})") \
                               .replace("{name}", user.first_name) \
                               .replace("{id}", str(user.id))
            
            btn_text = settings.get("welcome_btn_text")
            btn_url = settings.get("welcome_btn_url")
            
            markup = None
            if btn_text and btn_url and btn_url.startswith("http"):
                markup = InlineKeyboardMarkup([[InlineKeyboardButton(btn_text, url=btn_url)]])

            await client.send_message(chat_id, formatted, reply_markup=markup)
