import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import UserAlreadyParticipant, InviteRequestSent, FloodWait
from database import is_auth

@Client.on_message(filters.command("addallsessions") & filters.group)
async def add_all_sessions_to_group(client: Client, message: Message):
    if message.sender_chat and message.sender_chat.id == message.chat.id:
        pass
    elif not message.from_user or not await is_auth(message.from_user.id):
        return

    from main import clients
    if not clients:
        return await message.reply("⚠️ **No active userbot sessions found.** Use `/create` or `/addsession` first.")

    chat = message.chat
    chat_id = chat.id
    status_msg = await message.reply(f"🔄 **Adding all `{len(clients)}` userbot session(s) to {chat.title}...**")

    # Public username ya Private invite link nikalna
    join_target = None
    if getattr(chat, "username", None):
        join_target = chat.username
    else:
        try:
            invite_obj = await client.create_chat_invite_link(chat_id, name="AutoAddSessions")
            join_target = invite_obj.invite_link
        except Exception:
            try:
                full_chat = await client.get_chat(chat_id)
                join_target = getattr(full_chat, "invite_link", None)
            except Exception:
                join_target = None

    joined = []
    already = []
    failed = []

    for idx, ubot in enumerate(clients):
        tag = f"`#{idx + 1}`"
        try:
            me = await ubot.get_me()
            tag = f"`#{idx + 1}` ({me.first_name})"
        except Exception:
            pass

        # Pehle check karo ID pehle se group me hai ya nahi
        try:
            await ubot.get_chat_member(chat_id, "me")
            already.append(tag)
            continue
        except Exception:
            pass

        if not join_target:
            failed.append(f"{tag} (Bot needs 'Invite Users via Link' Admin right)")
            continue

        try:
            await ubot.join_chat(join_target)
            joined.append(tag)
        except UserAlreadyParticipant:
            already.append(tag)
        except InviteRequestSent:
            failed.append(f"{tag} (Join Request Pending — Approve in Group)")
        except FloodWait as fw:
            await asyncio.sleep(fw.value)
            try:
                await ubot.join_chat(join_target)
                joined.append(tag)
            except Exception as e2:
                failed.append(f"{tag} ({type(e2).__name__})")
        except Exception as e:
            failed.append(f"{tag} ({type(e).__name__})")

        await asyncio.sleep(1.5)

    report = (
        f"👥 **Add All Sessions Report**\n"
        f"────────────────────────\n"
        f"• **Group:** {chat.title}\n"
        f"• **Newly Joined ({len(joined)}):** {', '.join(joined) if joined else 'None'}\n"
        f"• **Already Present ({len(already)}):** {', '.join(already) if already else 'None'}\n"
        f"• **Failed ({len(failed)}):** {', '.join(failed) if failed else 'None'}"
    )
    await status_msg.edit(report)
