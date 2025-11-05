import asyncio
import os
import threading
from hypercorn.asyncio import serve
from hypercorn.config import Config
from bot import dp, bot, send_json
from database import init
from login_web import app




async def main2():
    await init()
    asyncio.create_task(send_json())
    await dp.start_polling(bot, skip_updates=True)




def run_flask():
    port = int(os.environ.get("PORT", 8480))  # 5000 for local dev, Render will override
    app.run(port=port, debug=False, use_reloader=False)


async def run_flask2():
    config = Config()
    config.bind = ["0.0.0.0:8480"]
    await serve(app, config)

async def joind():
    asyncio.create_task(main2())
    await run_flask2()


if __name__ == "__main__":
    import asyncio

    async def start_all():
        print("bot started")
        await init()
        asyncio.create_task(send_json())
        asyncio.create_task(dp.start_polling(bot, skip_updates=True))

        # Run Quart (Hypercorn) on same event loop
        config = Config()
        config.bind = ["0.0.0.0:8480"]
        await serve(app, config)

    try:
        asyncio.run(start_all())
    except (KeyboardInterrupt, RuntimeError):
        print("bot stopped")
