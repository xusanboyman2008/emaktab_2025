import asyncio
import os
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from hypercorn.asyncio import serve
from hypercorn.config import Config

from bot import dp, bot, send_json
from database import init, create_grades
from login_web import app


async def run_scheduler():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        send_json,
        trigger="cron",
        hour=7,
        minute=0,
        timezone=pytz.timezone("Asia/Tashkent"),
    )
    scheduler.start()


async def run_server():
    config = Config()
    port = int(os.environ.get("PORT", 8480))
    config.bind = [f"0.0.0.0:{port}"]
    await serve(app, config)


async def main():
    await init()
    await create_grades()
    await run_scheduler()
    print("🚀 Bot va Web-server bir vaqtda ishga tushirildi...")
    await asyncio.gather(
        dp.start_polling(bot, skip_updates=True),
        run_server()
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot va veb-xizmat to'xtatildi.")
