import asyncio
import os
import threading

from bot import dp, bot, send_json
from database import init
from login_web import app




async def main2():
    await init()
    asyncio.create_task(send_json())
    await dp.start_polling(bot, skip_updates=True)




def run_flask():
    port = int(os.environ.get("PORT", 5000))  # 5000 for local dev, Render will override
    app.run(port=port, debug=False, use_reloader=False)

if __name__ == "__main__":
    try:
        print("bot started")
        #
        # # # Start Flask in a thread
        # flask_thread = threading.Thread(target=run_flask)
        # flask_thread.start()

        # Run bot loop
        asyncio.run(main2())

    except (KeyboardInterrupt, RuntimeError):
        print("bot stopped")
