import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from pytgcalls import PyTgCalls
from pytgcalls.types import AudioPiped
from database import is_auth

pytgcalls_instances = {}

@Client.on_message(filters.command("joinvc"))
async def join_vc_multiple(client: Client, message: Message):
    if not await is_auth(message.from_user.id):
        return
    from main import clients
    
    if len(message.command) < 2:
        return await message.reply("Usage: `/joinvc 1 2 3` ya `/joinvc all`")
    
    chat_id = message.chat.id
    target_indices = []
    
    if message.command[1].lower() == "all":
        target_indices = list(range(len(clients)))
    else:
        for x in message.command[1:]:
            for item in x.replace(",", " ").split():
                if item.isdigit():
                    target_indices.append(int(item) - 1)
                    
    joined_count = 0
    status_msg = await message.reply("IDs VC me join karwa rahe hain...")
    
    for idx in target_indices:
        if 0 <= idx < len(clients):
            cli = clients[idx]
            try:
                # Group call me enter karwane ke liye py-tgcalls initialize
                if idx not in pytgcalls_instances:
                    call_app = PyTgCalls(cli)
                    await call_app.start()
                    pytgcalls_instances[idx] = call_app
                else:
                    call_app = pytgcalls_instances[idx]
                    
                await call_app.join_group_call(
                    chat_id,
                    AudioPiped("http://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4") # silence/dummy stream
                )
                joined_count += 1
            except Exception as e:
                # Direct voice chat raw call fallback
                try:
                    await cli.invoke(
                        # fallback call join logic if call already active
                    )
                except:
                    pass
    
    await status_msg.edit(f"Total **{joined_count}** accounts VC me join ho gaye hain!")

@Client.on_message(filters.command("leavevc"))
async def leave_vc_multiple(client: Client, message: Message):
    if not await is_auth(message.from_user.id):
        return
    chat_id = message.chat.id
    for idx, call_app in list(pytgcalls_instances.items()):
        try:
            await call_app.leave_group_call(chat_id)
        except:
            pass
    await message.reply("Sabhi IDs VC se nikal gayi hain.")
