from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from config import OWNER_ID, CHATBOT_API_KEY
from database import is_auth, get_all_sessions, chats_col

START_TEXT = (
    "👋 **Welcome to Group Activator & Multi-VC Bot!**\n\n"
    "Main ek multi-session userbot controller hoon. Mere zariye aap ek saath kai Telegram IDs ko "
    "Voice Chat (VC) me bitha sakte ho, AI Chatbot se group active rakh sakte ho, aur custom "
    "Welcome messages manage kar sakte ho.\n\n"
    "👇 **Neeche diye gaye buttons par tap karke har feature ko detail me samjhein:**"
)

MAIN_BUTTONS = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("📱 Session Manager", callback_data="help_session"),
        InlineKeyboardButton("🎙️ Multi-VC Joiner", callback_data="help_vc")
    ],
    [
        InlineKeyboardButton("🤖 AI Chatbot", callback_data="help_chatbot"),
        InlineKeyboardButton("🎉 Welcome System", callback_data="help_welcome")
    ],
    [
        InlineKeyboardButton("👑 Auth & Owner", callback_data="help_auth"),
        InlineKeyboardButton("📊 Live System Panel", callback_data="open_live_panel")
    ]
])

BACK_BUTTON = InlineKeyboardMarkup([
    [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="back_home")]
])

@Client.on_message(filters.command(["start", "help"]))
async def start_command(client: Client, message: Message):
    await message.reply(START_TEXT, reply_markup=MAIN_BUTTONS)

@Client.on_message(filters.command(["session", "sessions"]))
async def session_shortcut(client: Client, message: Message):
    if not await is_auth(message.from_user.id):
        return
    from main import clients
    saved = await get_all_sessions()

    text = (
        f"📱 **Session Manager Overview**\n\n"
        f"• Active Running IDs: `{len(clients)}`\n"
        f"• Saved in Database: `{len(saved)}`\n\n"
        "**Commands:**\n"
        "• `/create` - Number aur OTP daal kar auto session generate karo\n"
        "• `/addsession <string>` - Purana Pyrogram string session add karo\n"
        "• `/delsession <index>` - Session delete karo (e.g., `/delsession 0`)\n"
        "• `/panel` - Sabhi active accounts ke naam aur IDs dekho"
    )
    await message.reply(text, reply_markup=BACK_BUTTON)

@Client.on_callback_query(filters.regex("^help_"))
async def help_callbacks(client: Client, query: CallbackQuery):
    data = query.data

    if data == "help_session":
        text = (
            "📱 **1. Session Manager (Multi-Account Setup)**\n\n"
            "• `/create` — Bot aapse phone number, OTP aur 2FA password maangega aur khud Pyrogram session bana kar live start kar dega.\n"
            "• `/addsession <session_string>` — Pehle se bane Pyrogram v2 string session ko direct add karne ke liye.\n"
            "• `/session` — Total active sessions ka status dekhne ke liye.\n"
            "• `/delsession <index>` — Kisi account ko hatane ke liye (index `0` se start hota hai)."
        )
    elif data == "help_vc":
        text = (
            "🎙️ **2. Multi-VC Joiner (Group Voice Chat)**\n\n"
            "Jis group me aap ye commands daloge, aapki userbot IDs **sirf usi group ki VC** me jakar baith jayengi:\n\n"
            "• `/joinvc all` — Sabhi connected IDs ko ek saath group ki VC me join karwane ke liye.\n"
            "• `/joinvc 1 2 3` — Sirf chuni hui IDs (1st, 2nd aur 3rd) ko VC me bithane ke liye.\n"
            "• `/leavevc` — Us group ki VC se sabhi IDs ko bahar nikalne ke liye.\n"
            "• `/leavevc 2` — Sirf kisi ek specific ID ko VC se hatane ke liye."
        )
    elif data == "help_chatbot":
        text = (
            "🤖 **3. AI Userbot Chatbot (Auto-Tag & Reply)**\n\n"
            "• `/chatbot on` — Is group me AI userbot chatting chalu karne ke liye.\n"
            "• `/chatbot disable` — Is group me AI chatting band karne ke liye.\n\n"
            "Jab bhi group me koi userbot ko tag karega ya reply karega, connected IDs me se koi ek account user ko tag karke jawab dega."
        )
    elif data == "help_welcome":
        text = (
            "🎉 **4. Custom Welcome System**\n\n"
            "Auto-accept OFF hai. Jab admin manually request approve karega ya member join karega, tab welcome message jayega:\n\n"
            "• `/welcome on` — Group me welcome messages chalu karne ke liye.\n"
            "• `/welcome disable` — Band karne ke liye.\n"
            "• `/editwelcomemessage <text> | <Btn> - <URL>` — Custom message aur button set karne ke liye.\n\n"
            "**Tags:** `{mention}`, `{name}`, `{id}`"
        )
    elif data == "help_auth":
        text = (
            "👑 **5. Auth & System Control Commands**\n\n"
            "• `/auth <user_id>` — Kisi dusre user ko bot access dene ke liye (Sirf Owner).\n"
            "• `/delauth <user_id>` — Access wapas lene ke liye.\n"
            "• `/authlist` — Sabhi authorized users ki list.\n"
            "• `/panel` ya `/details` — DM me sabhi IDs, groups aur API status dekhne ke liye.\n"
            "• `/update` — GitHub se latest code pull karke bot restart karne ke liye."
        )
    else:
        return

    await query.message.edit_text(text, reply_markup=BACK_BUTTON)

@Client.on_callback_query(filters.regex("^back_home$"))
async def back_home_cb(client: Client, query: CallbackQuery):
    await query.message.edit_text(START_TEXT, reply_markup=MAIN_BUTTONS)

@Client.on_callback_query(filters.regex("^open_live_panel$"))
async def open_panel_from_btn(client: Client, query: CallbackQuery):
    if not await is_auth(query.from_user.id):
        return await query.answer("Sirf Owner/Auth users ke liye!", show_alert=True)

    from main import clients
    total_sessions = await get_all_sessions()
    total_chats = await chats_col.count_documents({})
    api_status = "🟢 Active" if CHATBOT_API_KEY else "🔴 Not Set"

    panel_text = (
        "👑 **LIVE SYSTEM PANEL**\n"
        "────────────────────────\n"
        f"🔑 **Chatbot API:** {api_status}\n"
        f"📱 **Active Sessions:** `{len(clients)}/{len(total_sessions)}`\n"
        f"👥 **Configured Groups:** `{total_chats}`\n"
        "────────────────────────\n"
        "Full account list ke liye `/panel` bhejein."
    )
    await query.message.edit_text(panel_text, reply_markup=BACK_BUTTON)
