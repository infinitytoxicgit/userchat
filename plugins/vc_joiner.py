import os
import wave
import random
import asyncio
from pyrogram import Client, filters, raw
from pyrogram.types import Message
from pyrogram.errors import UserAlreadyParticipant
from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream, AudioQuality
from database import is_auth

pytgcalls_instances = {}
started_calls = set()
active_vc_sessions = {}      # {client_idx: chat_id}
persistent_vc_chats = {}     # {chat_id: [client_idx1, client_idx2, ...]}

SILENT_AUDIO = "silence.wav"

def ensure_silent_audio():
    if not os.path.exists(SILENT_AUDIO):
        with wave.open(SILENT_AUDIO, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(48000)
            wf.writeframes(b"\x00\x00" * 48000 * 10)

def make_stream():
    ensure_silent_audio()
    return MediaStream(
        SILENT_AUDIO,
        audio_parameters=AudioQuality.HIGH,
        video_flags=MediaStream.Flags.IGNORE
    )

def get_call_instance(client_instance, idx: int) -> PyTgCalls:
    if idx not in pytgcalls_instances:
        call_app = PyTgCalls(client_instance)

        @call_app.on_update()
        async def _keep_alive_handler(client, update):
            cid = active_vc_sessions.get(idx)
            if cid and idx in persistent_vc_chats.get(cid, []):
                if "StreamEnded" in type(update).__name__:
                    try:
                        await call_app.play(cid, make_stream())
                    except Exception:
                        pass

        pytgcalls_instances[idx] = call_app
    return pytgcalls_instances[idx]

async def prepare_userbot_peer(cli: Client, chat):
    chat_id = chat.id
    if getattr(chat, "username", None):
        try:
            await cli.join_chat(chat.username)
        except UserAlreadyParticipant:
            pass
        except Exception:
            pass

    try:
        await cli.resolve_peer(chat_id)
    except Exception:
        async for dialog in cli.get_dialogs(limit=100):
            if dialog.chat.id == chat_id:
                break
        await cli.resolve_peer(chat_id)

async def is_vc_active_and_start_if_admin(cli: Client, chat_id: int) -> tuple[bool, str]:
    try:
        peer = await cli.resolve_peer(chat_id)
        if isinstance(peer, raw.types.InputPeerChannel):
            full = await cli.invoke(raw.functions.channels.GetFullChannel(channel=peer))
        else:
            full = await cli.invoke(raw.functions.messages.GetFullChat(chat_id=peer.chat_id))

        if getattr(full.full_chat, "call", None):
            return True, "Active"

        # VC off hai — ab userbot admin rights se start karne ki koshish karo
        await cli.invoke(
            raw.functions.phone.CreateGroupCall(
                peer=peer,
                random_id=random.randint(10000, 999999999),
                title="Voice Chat"
            )
        )
        await asyncio.sleep(2)
        return True, "Auto-Started by Admin Userbot"
    except Exception as e:
        err = str(e)
        if "GROUPCALL_ALREADY_STARTED" in err:
            return True, "Active"
        if "CHAT_ADMIN_REQUIRED" in err or "GROUPCALL_FORBIDDEN" in err:
            return False, "VC is OFF & Userbot lacks 'Manage Video Chats' Admin right"
        return False, f"{type(e).__name__}: {e}"

async def connect_single_session_to_vc(cli: Client, idx: int, chat) -> tuple[bool, str]:
    chat_id = chat.id
    call_app = get_call_instance(cli, idx)

    try:
        await prepare_userbot_peer(cli, chat)
    except Exception as e:
        return False, f"Userbot not in group ({type(e).__name__})"

    # Pehle check karo VC on hai ya nahi; off hai aur userbot admin hai toh auto-start karo
    vc_ok, vc_status = await is_vc_active_and_start_if_admin(cli, chat_id)
    if not vc_ok:
        return False, vc_status

    try:
        if idx not in started_calls:
            await asyncio.wait_for(call_app.start(), timeout=15)
            started_calls.add(idx)

        if idx in active_vc_sessions and active_vc_sessions[idx] != chat_id:
            try:
                await call_app.leave_call(active_vc_sessions[idx])
            except Exception:
                pass

        await asyncio.wait_for(call_app.play(chat_id, make_stream()), timeout=15)
        active_vc_sessions[idx] = chat_id
        return True, vc_status
    except asyncio.TimeoutError:
        return False, "Connection Timeout"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"

@Client.on_message(filters.command("joinvc") & filters.group)
async def join_vc_handler(client: Client, message: Message):
    if not message.from_user or not await is_auth(message.from_user.id):
        return

    from main import clients
    if not clients:
        return await message.reply("⚠️ **No active userbot sessions found.** Use `/create` or `/addsession` first.")

    chat_id = message.chat.id
    args = message.text.split()[1:]

    if not args:
        return await message.reply(
            "📌 **Voice Chat Controller:**\n"
            "• `/joinvc 1 2` — Connect specific IDs & lock 24/7\n"
            "• `/joinvc all` — Connect all active IDs & lock 24/7\n"
            "• `/leavevc` — Disconnect & disable auto-rejoin\n"
            "• `/vcstatus` — Check active VC sessions"
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
        return await message.reply(f"❌ **Invalid Session ID.** Available sessions: `1` to `{len(clients)}`.")

    status_msg = await message.reply(f"🔄 **Connecting {len(target_indices)} session(s) to Voice Chat...**")

    # 24/7 Persistent Lock ON karo
    existing = persistent_vc_chats.get(chat_id, [])
    for idx in target_indices:
        if idx not in existing:
            existing.append(idx)
    persistent_vc_chats[chat_id] = existing

    # Agar koi admin userbot list me hai toh usko pehle run karo taaki wo VC start kar de
    ordered_indices = sorted(target_indices)
    joined_list = []
    failed_list = []

    for idx in ordered_indices:
        ok, info = await connect_single_session_to_vc(clients[idx], idx, message.chat)
        if ok:
            tag = " *(Started VC)*" if "Auto-Started" in info else ""
            joined_list.append(f"`#{idx + 1}`{tag}")
        else:
            failed_list.append(f"`#{idx + 1}` ({info})")
        await asyncio.sleep(1)

    report = (
        f"🎙️ **Voice Chat Connection Report**\n"
        f"────────────────────────\n"
        f"• **Group:** {message.chat.title}\n"
        f"• **Connected ({len(joined_list)}):** {', '.join(joined_list) if joined_list else 'None'}\n"
        f"• **Failed ({len(failed_list)}):** {', '.join(failed_list) if failed_list else 'None'}\n"
        f"• **24/7 Auto-Rejoin:** `🟢 ENABLED` (Until `/leavevc`)"
    )
    await status_msg.edit(report)

@Client.on_message(filters.video_chat_started & filters.group)
async def auto_rejoin_on_vc_restart(client: Client, message: Message):
    chat_id = message.chat.id
    if chat_id not in persistent_vc_chats or not persistent_vc_chats[chat_id]:
        return

    from main import clients
    await asyncio.sleep(2.5)
    rejoined = []
    failed = []
    for idx in list(persistent_vc_chats[chat_id]):
        if 0 <= idx < len(clients):
            ok, info = await connect_single_session_to_vc(clients[idx], idx, message.chat)
            if ok:
                rejoined.append(f"`#{idx + 1}`")
            else:
                failed.append(f"`#{idx + 1}` ({info})")
            await asyncio.sleep(1)

    if rejoined:
        await message.reply(f"♻️ **Auto-Rejoined Voice Chat:** {', '.join(rejoined)}")
    elif failed:
        await message.reply(f"⚠️ **Auto-Rejoin Failed:** {', '.join(failed)}")

@Client.on_message(filters.command("leavevc") & filters.group)
async def leave_vc_handler(client: Client, message: Message):
    if not message.from_user or not await is_auth(message.from_user.id):
        return

    chat_id = message.chat.id
    args = message.text.split()[1:]

    status_msg = await message.reply("🔄 **Disconnecting from Voice Chat...**")

    if args and args[0].lower() != "all":
        target_indices = [int(x) - 1 for x in args if x.isdigit()]
    else:
        target_indices = list(set(
            persistent_vc_chats.get(chat_id, []) +
            [idx for idx, cid in active_vc_sessions.items() if cid == chat_id]
        ))

    left_list = []
    for idx in target_indices:
        if chat_id in persistent_vc_chats and idx in persistent_vc_chats[chat_id]:
            persistent_vc_chats[chat_id].remove(idx)
        if idx in pytgcalls_instances:
            try:
                await pytgcalls_instances[idx].leave_call(chat_id)
            except Exception:
                pass
        if active_vc_sessions.get(idx) == chat_id:
            active_vc_sessions.pop(idx, None)
        left_list.append(f"`#{idx + 1}`")

    if chat_id in persistent_vc_chats and not persistent_vc_chats[chat_id]:
        persistent_vc_chats.pop(chat_id, None)

    await status_msg.edit(
        f"🛑 **Disconnected from Voice Chat**\n"
        f"────────────────────────\n"
        f"• **Group:** {message.chat.title}\n"
        f"• **Removed IDs:** {', '.join(left_list) if left_list else 'None'}\n"
        f"• **24/7 Auto-Rejoin:** `🔴 DISABLED`"
    )

@Client.on_message(filters.command("vcstatus"))
async def vc_status_handler(client: Client, message: Message):
    if not message.from_user or not await is_auth(message.from_user.id):
        return

    if not active_vc_sessions and not persistent_vc_chats:
        return await message.reply("📴 **No active Voice Chat sessions right now.**")

    lines = ["🎙️ **Active Voice Chat Sessions:**\n"]
    for idx, cid in active_vc_sessions.items():
        lock = "🔒 Auto-Rejoin ON" if idx in persistent_vc_chats.get(cid, []) else ""
        lines.append(f"• **Session #{idx + 1}** ➔ `{cid}` {lock}")

    await message.reply("\n".join(lines))
