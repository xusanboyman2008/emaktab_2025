import asyncio
import threading

from bot import dp, bot, login_schedule
from database import init
from login_web import app
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot import send_json

scheduler = AsyncIOScheduler()
UZBEKISTAN_TZ = pytz.timezone("Asia/Tashkent")



async def main2():
    scheduler.add_job(
        login_schedule,
        trigger="cron",
        hour=6,
        minute=0,
        timezone=UZBEKISTAN_TZ,
    )
    scheduler.start()
    await init()
    # run send_json in background
    asyncio.create_task(send_json())
    await dp.start_polling(bot, skip_updates=True)

async def main():
    await init()
    # await main2()
    await dp.start_polling(bot)


def run_flask():
    app.run(debug=True, use_reloader=False,port=0000)  # disable reloader so it doesn’t run twice


if __name__ == "__main__":
    try:
        print("bot started")

        # Start Flask in a thread
        flask_thread = threading.Thread(target=run_flask)
        flask_thread.start()

        # Run bot loop
        asyncio.run(main2())

    except (KeyboardInterrupt, RuntimeError):
        print("bot stopped")
