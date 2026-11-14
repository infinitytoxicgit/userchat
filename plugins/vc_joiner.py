import os
import wave
import random
import asyncio
from pyrogram import Client, filters, raw
from pyrogram.types import Message
from pyrogram.errors import UserAlreadyParticipant
from pytgcalls import PyTgCalls
from pytgcalls.types import MediaStream
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
            wf.writeframes(b"\x00\x00" * 48000 * 5)

def get_call_instance(client_instance, idx: int) -> PyTgCalls:
    if idx not in pytgcalls_instances:
        call_app = PyTgCalls(client_instance)

        @call_app.on_update()
        async def _keep_alive_handler(client, update):
            # Jab tak chat persistent_vc_chats me hai aur session assigned hai, silent loop chalu rakho
            cid = active_vc_sessions.get(idx)
            if cid and idx in persistent_vc_chats.get(cid, []):
                if "StreamEnded" in type(update).__name__:
                    try:
                        ensure_silent_audio()
                        await call_app.play(
                            cid,
                            MediaStream(SILENT_AUDIO, video_flags=MediaStream.Flags.IGNORE)
                        )
                    except Exception:
                        pass

        pytgcalls_instances[idx] = call_app
    return pytgcalls_instances[idx]

async def resolve_and_prepare_chat(cli: Client, chat):
    chat_id = chat.id
    # Public group ho toh username se join karo
    if getattr(chat, "username", None):
        try:
            await cli.join_chat(chat.username)
        except UserAlreadyParticipant:
            pass
        except Exception:
            pass

    # Private group peer cache load karo taaki PyTgCalls hang na ho
    try:
        await cli.get_chat(chat_id)
    except Exception:
        async for dialog in cli.get_dialogs(limit=50):
            if dialog.chat.id == chat_id:
                break

async def try_start_group_vc(cli: Client, chat_id: int) -> tuple[bool, str]:
    try:
        peer = await cli.resolve_peer(chat_id)
        await cli.invoke(
            raw.functions.phone.CreateGroupCall(
                peer=peer,
                random_id=random.randint(10000, 999999999),
                title="Voice Chat"
            )
        )
        await asyncio.sleep(1.5)
        return True, "Started"
    except Exception as e:
        err = str(e)
        if "GROUPCALL_ALREADY_STARTED" in err:
            return True, "Already Active"
        if "CHAT_ADMIN_REQUIRED" in err:
            return False, "VC is off & Userbot is not Admin to start it"
        return False, type(e).__name__

async def connect_single_session_to_vc(cli: Client, idx: int, chat) -> tuple[bool, str]:
    chat_id = chat.id
    call_app = get_call_instance(cli, idx)
    ensure_silent_audio()
    stream = MediaStream(SILENT_AUDIO, video_flags=MediaStream.Flags.IGNORE)

    try:
        await resolve_and_prepare_chat(cli, chat)

        if idx not in started_calls:
            await asyncio.wait_for(call_app.start(), timeout=15)
            started_calls.add(idx)

        if idx in active_vc_sessions and active_vc_sessions[idx] != chat_id:
            try:
                await call_app.leave_call(active_vc_sessions[idx])
            except Exception:
                pass

        try:
            await asyncio.wait_for(call_app.play(chat_id, stream), timeout=15)
        except Exception as play_err:
            err_str = str(play_err)
            # Agar group me VC band hai toh admin hone par khud start kare
            if "NoActiveGroupCall" in type(play_err).__name__ or "GROUPCALL" in err_str.upper() or "not found" in err_str.lower():
                started, reason = await try_start_group_vc(cli, chat_id)
                if not started:
                    return False, f"VC Not Started ({reason})"
                await asyncio.wait_for(call_app.play(chat_id, stream), timeout=15)
            else:
                raise play_err

        active_vc_sessions[idx] = chat_id
        return True, "Connected"
    except asyncio.TimeoutError:
        return False, "Timeout (Check if Userbot is in this Group)"
    except Exception as e:
        return False, f"{type(e).__name__}"

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

    # Persistent VC lock ON kar do is group ke liye
    existing = persistent_vc_chats.get(chat_id, [])
    for idx in target_indices:
        if idx not in existing:
            existing.append(idx)
    persistent_vc_chats[chat_id] = existing

    joined_list = []
    failed_list = []

    for idx in target_indices:
        ok, info = await connect_single_session_to_vc(clients[idx], idx, message.chat)
        if ok:
            joined_list.append(f"`#{idx + 1}`")
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

# Agar VC end hokar dubara start ho toh automatically assigned IDs rejoin kar lein
@Client.on_message(filters.video_chat_started & filters.group)
async def auto_rejoin_on_vc_restart(client: Client, message: Message):
    chat_id = message.chat.id
    if chat_id not in persistent_vc_chats or not persistent_vc_chats[chat_id]:
        return

    from main import clients
    await asyncio.sleep(2)
    rejoined = []
    for idx in list(persistent_vc_chats[chat_id]):
        if 0 <= idx < len(clients):
            ok, _ = await connect_single_session_to_vc(clients[idx], idx, message.chat)
            if ok:
                rejoined.append(f"`#{idx + 1}`")
            await asyncio.sleep(1)

    if rejoined:
        await message.reply(f"♻️ **Auto-Rejoined Voice Chat:** {', '.join(rejoined)}")

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
