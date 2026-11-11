from pyrogram import Client, filters
from pyrogram.types import ChatJoinRequest, Message, InlineKeyboardMarkup, InlineKeyboardButton
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
        await message.reply("Welcome system **ON** ho gaya.")
    elif action in ["off", "disable"]:
        await update_chat_settings(message.chat.id, "welcome", False)
        await message.reply("Welcome system **DISABLED** ho gaya.")

@Client.on_message(filters.command("editwelcomemessage"))
async def edit_welcome_cmd(client: Client, message: Message):
    if not await is_auth(message.from_user.id):
        return
    if len(message.text.split(None, 1)) < 2:
        return await message.reply("Usage: `/editwelcomemessage Hello {mention}! Welcome to our group.`\n\nCustom tags: `{mention}`, `{name}`, `{id}`")
    
    new_text = message.text.split(None, 1)[1]
    await update_chat_settings(message.chat.id, "welcome_msg", new_text)
    await message.reply("Welcome template update ho gaya! Premium emojis aur links isme fully supported hain.")

# Handles join requests (request accept trigger)
@Client.on_chat_join_request()
async def auto_accept_and_welcome(client: Client, request: ChatJoinRequest):
    chat_id = request.chat.id
    user = request.from_user
    
    # Request approve karo
    await request.approve()
    
    settings = await get_chat_settings(chat_id)
    if settings.get("welcome", False):
        raw_msg = settings.get("welcome_msg", "Welcome {mention}!")
        formatted = raw_msg.replace("{mention}", f"[{user.first_name}](tg://user?id={user.id})") \
                           .replace("{name}", user.first_name) \
                           .replace("{id}", str(user.id))
        
        # Inline buttons ke sath send
        buttons = InlineKeyboardMarkup([
            [InlineKeyboardButton("Join Channel", url="https://t.me/telegram")]
        ])
        await client.send_message(chat_id, formatted, reply_markup=buttons)
