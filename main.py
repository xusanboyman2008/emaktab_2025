import asyncio
import os
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from aiohttp import web

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logging.getLogger("aiogram").setLevel(logging.DEBUG)

from bot import dp, bot, send_json
from database import init, create_grades, get_setting
from login_web import app
from captcha_manager import run_captcha_scheduler


async def run_scheduler():
    """Native standard-library cron scheduler dynamically adapting to configured check time."""
    tz = ZoneInfo("Asia/Tashkent")
    while True:
        check_time = await get_setting("check_time", "07:00")
        try:
            h_str, m_str = check_time.split(":")
            h, m = int(h_str), int(m_str)
        except Exception:
            h, m = 7, 0

        now = datetime.now(tz)
        target = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        sleep_seconds = (target - now).total_seconds()
        print(f"⏰ Keyingi avtomatik tekshiruv: {target.strftime('%Y-%m-%d %H:%M')} (kutilmoqda: {sleep_seconds:.0f}s)")

        while target > datetime.now(tz):
            cur_time = await get_setting("check_time", "07:00")
            if cur_time != check_time:
                break
            remaining = (target - datetime.now(tz)).total_seconds()
            if remaining <= 0:
                break
            await asyncio.sleep(min(30.0, remaining))

        now = datetime.now(tz)
        if abs((now - target).total_seconds()) < 60:
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
    asyncio.create_task(run_captcha_scheduler())
    await run_server()
    print("🚀 Bot va veb-server muvaffaqiyatli ishga tushirildi!")
    await bot.delete_webhook(drop_pending_updates=True)
    used_updates = dp.resolve_used_update_types()
    logging.info(f"Ishlatiladigan yangilanish turlari: {used_updates}")
    await dp.start_polling(bot, allowed_updates=used_updates)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot va veb-xizmat to'xtatildi.")
