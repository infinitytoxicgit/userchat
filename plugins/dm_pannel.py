from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import MessageNotModified
from config import OWNER_ID, CHATBOT_API_KEY
from database import is_auth, chats_col, get_all_sessions

async def build_panel_content():
    from main import clients

    total_sessions = await get_all_sessions()
    active_in_mem = len(clients)

    chats_cursor = chats_col.find({})
    active_gcs = []
    chatbot_enabled_count = 0
    welcome_enabled_count = 0

    async for doc in chats_cursor:
        active_gcs.append(doc.get("chat_id"))
        if doc.get("chatbot"):
            chatbot_enabled_count += 1
        if doc.get("welcome"):
            welcome_enabled_count += 1

    sessions_detail_text = ""
    for idx, cli in enumerate(clients):
        try:
            me = await cli.get_me()
            sessions_detail_text += f"`[{idx + 1}]` {me.first_name} (`{me.id}`) | @{me.username or 'NoUser'}\n"
        except Exception:
            sessions_detail_text += f"`[{idx + 1}]` [Offline/Reconnecting]\n"

    if not sessions_detail_text:
        sessions_detail_text = "No userbot sessions active currently.\n"

    api_status = "🟢 Active" if CHATBOT_API_KEY else "🔴 Not Configured"
    now_time = datetime.now().strftime("%I:%M:%S %p")

    panel_text = (
        "👑 **MASTER OWNER STATUS PANEL**\n"
        "────────────────────────\n\n"
        "🤖 **Bot Engine:** Pyrogram Async Multi-Client\n"
        f"🔑 **Chatbot AI API:** {api_status}\n\n"
        f"📊 **Connected Sessions:** `{active_in_mem}/{len(total_sessions)}`\n"
        f"{sessions_detail_text}\n"
        "👥 **Groups Stats:**\n"
        f"• Total Configured GCs: `{len(active_gcs)}`\n"
        f"• Chatbot Active: `{chatbot_enabled_count}` Groups\n"
        f"• Welcome System Active: `{welcome_enabled_count}` Groups\n"
        "────────────────────────\n"
        f"🕒 **Last Updated:** `{now_time}`\n"
        "• `/update` - Pull commits & restart\n"
        "• `/create` - Generate and link new session\n"
        "• `/authlist` - Check all authorized IDs"
    )

    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 Refresh Stats", callback_data="refresh_panel"),
            InlineKeyboardButton("🛑 Leave All VCs", callback_data="leave_all_vc")
        ]
    ])
    return panel_text, buttons

@Client.on_message(filters.command(["panel", "details"]) & filters.private)
async def owner_details_panel(client: Client, message: Message):
    if not message.from_user or not await is_auth(message.from_user.id):
        return
    panel_text, buttons = await build_panel_content()
    await message.reply(panel_text, reply_markup=buttons)

@Client.on_callback_query(filters.regex("^refresh_panel$"))
async def refresh_panel_cb(client: Client, query: CallbackQuery):
    if not await is_auth(query.from_user.id):
        return await query.answer("Access Denied.", show_alert=True)

    panel_text, buttons = await build_panel_content()
    try:
        await query.message.edit_text(panel_text, reply_markup=buttons)
        await query.answer("✅ Stats Refreshed!")
    except MessageNotModified:
        await query.answer("Already up to date!")

@Client.on_callback_query(filters.regex("^leave_all_vc$"))
async def leave_all_vc_cb(client: Client, query: CallbackQuery):
    if not await is_auth(query.from_user.id):
        return await query.answer("Access Denied.", show_alert=True)

    from plugins.vc_joiner import pytgcalls_instances, active_vc_sessions
    left = 0
    for idx, cid in list(active_vc_sessions.items()):
        if idx in pytgcalls_instances:
            try:
                await pytgcalls_instances[idx].leave_call(cid)
                left += 1
            except Exception:
                pass
        active_vc_sessions.pop(idx, None)

    await query.answer(f"🛑 {left} VC connections closed!", show_alert=True)
    panel_text, buttons = await build_panel_content()
    try:
        await query.message.edit_text(panel_text, reply_markup=buttons)
    except MessageNotModified:
        pass
