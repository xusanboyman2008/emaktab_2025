import asyncio
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from aiohttp import web

from bot import dp, bot, send_json
from database import init, create_grades
from login_web import app


async def run_scheduler():
    """Native standard-library cron scheduler without external dependencies."""
    tz = ZoneInfo("Asia/Tashkent")
    while True:
        now = datetime.now(tz)
        target = now.replace(hour=7, minute=0, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        sleep_seconds = (target - now).total_seconds()
        print(f"⏰ Keyingi avtomatik tekshiruv: {target.strftime('%Y-%m-%d %H:%M')} (kutilmoqda: {sleep_seconds:.0f}s)")
        await asyncio.sleep(sleep_seconds)
        try:
            await send_json()
        except Exception as e:
            print("⚠️ Rejali tekshiruvda xatolik:", e)


async def run_server():
    """Runs aiohttp web server concurrently on the specified port."""
    port = int(os.environ.get("PORT", 8480))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"🌐 Veb-server ishga tushdi: http://0.0.0.0:{port}")


async def main():
    await init()
    await create_grades()
    asyncio.create_task(run_scheduler())
    await run_server()
    print("🚀 Bot va veb-server muvaffaqiyatli ishga tushirildi!")
    await dp.start_polling(bot, skip_updates=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot va veb-xizmat to'xtatildi.")
