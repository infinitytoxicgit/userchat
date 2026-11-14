import time
import asyncio
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import MessageNotModified
from config import API_ID, API_HASH, OWNER_ID, CHATBOT_API_KEY
from database import is_auth, chats_col, get_all_sessions, sessions_col, delete_session

def get_main_buttons():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 Refresh Stats", callback_data="refresh_panel"),
            InlineKeyboardButton("🛑 Leave All VCs", callback_data="leave_all_vc")
        ],
        [
            InlineKeyboardButton("📱 Sessions (Name/Number)", callback_data="panel_sessions"),
            InlineKeyboardButton("🎙️ VC & Groups Info", callback_data="panel_vc_groups")
        ],
        [
            InlineKeyboardButton("➕ Login New Session", callback_data="panel_login_session"),
            InlineKeyboardButton("🔑 See String Sessions", callback_data="panel_see_strings")
        ]
    ])

async def build_panel_content():
    from main import clients
    from plugins.vc_joiner import active_vc_sessions

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
            phone = f"+{me.phone_number}" if me.phone_number else "NoPhone"
            vc_tag = f" | 🎙️ VC (`{active_vc_sessions[idx]}`)" if idx in active_vc_sessions else ""
            sessions_detail_text += f"`[{idx + 1}]` **{me.first_name}** (`{phone}`){vc_tag}\n"
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
        f"🎙️ **Active VC Connections:** `{len(active_vc_sessions)}`\n\n"
        "👥 **Groups Stats:**\n"
        f"• Total Configured GCs: `{len(active_gcs)}`\n"
        f"• Chatbot Active: `{chatbot_enabled_count}` Groups\n"
        f"• Welcome System Active: `{welcome_enabled_count}` Groups\n"
        "────────────────────────\n"
        f"🕒 **Last Updated:** `{now_time}`"
    )

    return panel_text, get_main_buttons()

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

@Client.on_callback_query(filters.regex("^panel_login_session$"))
async def panel_login_session_cb(client: Client, query: CallbackQuery):
    if not await is_auth(query.from_user.id):
        return await query.answer("Access Denied.", show_alert=True)

    await query.answer("📱 Login process started!")
    from plugins.session_mgr import start_create_flow
    await start_create_flow(client, query.message.chat.id, query.from_user.id)

@Client.on_callback_query(filters.regex("^panel_see_strings$"))
async def panel_see_strings_cb(client: Client, query: CallbackQuery):
    if not await is_auth(query.from_user.id):
        return await query.answer("Access Denied.", show_alert=True)

    from main import clients
    if not clients:
        return await query.answer("⚠️ Abhi koi active session login nahi hai!", show_alert=True)

    await query.answer("📩 Active String Sessions bhej rahe hain...")
    for idx, cli in enumerate(clients, 1):
        try:
            me = await cli.get_me()
            s_str = await cli.export_session_string()
            phone = f"+{me.phone_number}" if me.phone_number else "Unknown"
            await client.send_message(
                query.from_user.id,
                f"🔑 **ACTIVE SESSION #{idx}**\n"
                f"• **Name:** {me.first_name} (`{me.id}`)\n"
                f"• **Phone:** `{phone}`\n\n"
                f"**Pyrogram v2 String (Tap to Copy):**\n`{s_str}`"
            )
        except Exception as e:
            await client.send_message(query.from_user.id, f"❌ Session #{idx} export error: `{e}`")

@Client.on_callback_query(filters.regex("^panel_reactivate$"))
async def panel_reactivate_cb(client: Client, query: CallbackQuery):
    if not await is_auth(query.from_user.id):
        return await query.answer("Access Denied.", show_alert=True)

    from main import clients
    db_docs = await sessions_col.find({}).to_list(length=100)
    if not db_docs:
        return await query.answer("⚠️ Database me koi session nahi hai!", show_alert=True)

    live_strings = set()
    for cli in clients:
        try:
            live_strings.add(await cli.export_session_string())
        except Exception:
            pass

    reconnected = 0
    failed = 0
    await query.answer("🔄 Reconnecting inactive sessions...")

    for doc in db_docs:
        s_str = doc.get("session")
        if s_str and s_str not in live_strings:
            try:
                new_cli = Client(f"ubot_re_{int(time.time())}", api_id=API_ID, api_hash=API_HASH, session_string=s_str, in_memory=True)
                await new_cli.start()
                clients.append(new_cli)
                reconnected += 1
                await asyncio.sleep(1)
            except Exception:
                failed += 1

    if failed > 0 and reconnected == 0:
        await client.send_message(
            query.from_user.id,
            f"⚠️ **{failed} Session(s) Telegram se permanently expire (`AUTH_KEY_UNREGISTERED`) ho chuke hain.**\n"
            "Unhe dubara login karne ke liye **➕ Login New Session** button dabao."
        )
    else:
        await client.send_message(
            query.from_user.id,
            f"🔄 **Reactivate Result:**\n• Reconnected: `{reconnected}`\n• Expired (Re-login needed): `{failed}`"
        )

    await panel_sessions_cb(client, query)

@Client.on_callback_query(filters.regex("^panel_sessions$"))
async def panel_sessions_cb(client: Client, query: CallbackQuery):
    if not await is_auth(query.from_user.id):
        return await query.answer("Access Denied.", show_alert=True)

    from main import clients
    from plugins.vc_joiner import active_vc_sessions
    db_docs = await sessions_col.find({}).to_list(length=100)

    live_map = {}
    for idx, cli in enumerate(clients):
        try:
            s_str = await cli.export_session_string()
            live_map[s_str] = idx
        except Exception:
            pass

    text = "📱 **SESSIONS MANAGER (NAME + NUMBER)**\n────────────────────────\n\n"
    if db_docs:
        for idx, doc in enumerate(db_docs, 1):
            s_str = doc.get("session", "")
            name = doc.get("name") or "Unknown Name"
            phone = doc.get("phone") or "No Phone"
            uid = doc.get("user_id") or ""
            if s_str in live_map:
                mem_idx = live_map[s_str]
                vc_tag = f" | 🎙️ VC: `{active_vc_sessions[mem_idx]}`" if mem_idx in active_vc_sessions else ""
                status = f"🟢 Active{vc_tag}"
            else:
                status = "🔴 Deactivated/Dead"

            id_part = f" (`{uid}`)" if uid else ""
            text += f"`[{idx}]` **{name}**{id_part}\n    └ 📞 `{phone}` — **{status}**\n"
    else:
        text += "• Abhi koi session saved nahi hai.\n"

    text += "\n────────────────────────\n💡 `/delsession <num>` se specific session hata sakte ho."

    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ Login New Session", callback_data="panel_login_session"),
            InlineKeyboardButton("🔄 Reactivate All", callback_data="panel_reactivate")
        ],
        [
            InlineKeyboardButton("🔑 See String Sessions", callback_data="panel_see_strings"),
            InlineKeyboardButton("🧹 Clean Dead", callback_data="panel_clean_dead")
        ],
        [
            InlineKeyboardButton("🔙 Back to Main Panel", callback_data="refresh_panel")
        ]
    ])

    try:
        await query.message.edit_text(text, reply_markup=buttons)
        await query.answer()
    except MessageNotModified:
        await query.answer("Already up to date!")

@Client.on_callback_query(filters.regex("^panel_clean_dead$"))
async def panel_clean_dead_cb(client: Client, query: CallbackQuery):
    if not await is_auth(query.from_user.id):
        return await query.answer("Access Denied.", show_alert=True)

    await query.answer("🧹 Checking & cleaning dead sessions...", show_alert=False)
    all_s = await get_all_sessions()
    removed = 0
    for s in all_s:
        try:
            test = Client(f"chk_{int(time.time())}", api_id=API_ID, api_hash=API_HASH, session_string=s, in_memory=True)
            await test.start()
            await test.stop()
        except Exception:
            await delete_session(s)
            removed += 1

    await query.answer(f"✅ {removed} Dead Sessions Cleaned!", show_alert=True)
    await panel_sessions_cb(client, query)

@Client.on_callback_query(filters.regex("^panel_vc_groups$"))
async def panel_vc_groups_cb(client: Client, query: CallbackQuery):
    if not await is_auth(query.from_user.id):
        return await query.answer("Access Denied.", show_alert=True)

    from main import clients
    from plugins.vc_joiner import active_vc_sessions

    text = "🎙️ **ACTIVE VOICE CHATS & GROUPS**\n────────────────────────\n\n"
    text += f"🔊 **Live VC Tracker ({len(active_vc_sessions)}):**\n"

    if active_vc_sessions:
        for idx, cid in active_vc_sessions.items():
            acc_name = f"ID #{idx + 1}"
            if 0 <= idx < len(clients):
                try:
                    me = await clients[idx].get_me()
                    acc_name = f"{me.first_name} (`#{idx + 1}`)"
                except Exception:
                    pass
            try:
                chat = await client.get_chat(cid)
                gc_title = chat.title or "Private Group"
            except Exception:
                gc_title = "Group"
            text += f"• {acc_name} ➔ **{gc_title}** (`{cid}`)\n"
    else:
        text += "• Abhi koi bhi ID kisi VC me nahi hai.\n"

    text += "\n👥 **Configured Groups List:**\n"
    chats_list = await chats_col.find({}).to_list(length=50)
    if chats_list:
        for idx, doc in enumerate(chats_list, 1):
            cid = doc.get("chat_id")
            cb = "🟢" if doc.get("chatbot") else "🔴"
            wl = "🟢" if doc.get("welcome") else "🔴"
            try:
                chat = await client.get_chat(cid)
                title = chat.title or str(cid)
            except Exception:
                title = str(cid)
            text += f"`[{idx}]` **{title}** (`{cid}`)\n    └ AI Chat: {cb} | Welcome: {wl}\n"
    else:
        text += "• Abhi koi group database me configured nahi hai.\n"

    buttons = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🛑 Leave All VCs", callback_data="leave_all_vc"),
            InlineKeyboardButton("🔄 Refresh", callback_data="panel_vc_groups")
        ],
        [
            InlineKeyboardButton("🔙 Back to Main Panel", callback_data="refresh_panel")
        ]
    ])

    try:
        await query.message.edit_text(text, reply_markup=buttons)
        await query.answer()
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
