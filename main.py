import asyncio
import logging
import pyrogram.utils
import pyrogram.errors

for _err_name in ("GroupcallForbidden", "GroupcallInvalid", "GroupcallJoinMissing"):
    if not hasattr(pyrogram.errors, _err_name):
        setattr(pyrogram.errors, _err_name, pyrogram.errors.RPCError)

pyrogram.utils.MIN_CHANNEL_ID = -1009999999999

from pyrogram import Client
from config import API_ID, API_HASH, BOT_TOKEN, OWNER_ID
from database import get_all_sessions

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("MultiBot")

bot = Client(
    "MainBot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    plugins=dict(root="plugins")
)

clients = []

async def init_clients():
    sessions = await get_all_sessions()
    logger.info(f"Loading {len(sessions)} saved userbot sessions...")
    for idx, s in enumerate(sessions):
        try:
            cli = Client(
                name=f"ubot_{idx}",
                api_id=API_ID,
                api_hash=API_HASH,
                session_string=s,
                in_memory=True
            )
            await cli.start()
            clients.append(cli)
            await asyncio.sleep(1)
        except Exception as e:
            err_msg = f"⚠️ **Session #{idx + 1} Start Failed:**\n`{type(e).__name__}: {e}`"
            logger.error(err_msg)
            try:
                await bot.send_message(OWNER_ID, err_msg)
            except Exception:
                pass

async def stop_all_clients():
    for cli in list(clients):
        try:
            await cli.stop()
        except Exception:
            pass
    clients.clear()
    try:
        await bot.stop()
    except Exception:
        pass

async def main():
    await bot.start()
    bot_me = await bot.get_me()
    logger.info(f"Bot started as @{bot_me.username}")

    await init_clients()
    logger.info(f"Active Userbot Clients: {len(clients)}")

    await asyncio.Event().wait()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
