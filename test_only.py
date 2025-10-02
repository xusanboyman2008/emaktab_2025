import asyncio

import aiohttp

URL = "https://market.notpixel.org/api/v1/task/claim/3"

HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-encoding": "gzip, deflate, br, zstd",
    "accept-language": "en-US,en;q=0.9",
    "origin": "https://market.notpixel.org",
    "referer": "https://market.notpixel.org/profile",
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0",
    "x-hash": "eyJ1c2VyIjoie1wiaWRcIjo3MTIyNDU0MTE4LFwiZmlyc3RfbmFtZVwiOlwi4oia8J2QkfCdkI7wnZCL8J2QhPCdkJfihKJcIixcImxhc3RfbmFtZVwiOlwiXCIsXCJ1c2VybmFtZVwiOlwiS1JDUllQVE9PRkZsQ0lBTFwiLFwibGFuZ3VhZ2VfY29kZVwiOlwiZW5cIixcImFsbG93c193cml0ZV90b19wbVwiOnRydWUsXCJwaG90b191cmxcIjpcImh0dHBzOlxcL1xcL3QubWVcXC9pXFwvdXNlcnBpY1xcLzMyMFxcL3FCZmdZc3JoeTI1YW9QY3lhUG5pTWhlQ0hRVGNlZnp3TDB2SmgyTWJmWkN3b2FYeThLN1Jld0huSjRHUHBXQjcuc3ZnXCJ9IiwiY2hhdF9pbnN0YW5jZSI6IjU1NjgzODE4MDQ3NjQ4NjkxOTYiLCJjaGF0X3R5cGUiOiJzZW5kZXIiLCJhdXRoX2RhdGUiOiIxNzU5NDE2MTMyIiwic2lnbmF0dXJlIjoiajEwbHZZS3BPUkZwVjd3Z0JQSTB5SWNJc05aMHQtTnA2QUxTandWYW9GbkNnamI3SDR1SHMyOFZoWFlleV9vWHkyWUN5QkltX1VvWjdfS1FzcmhrQXciLCJoYXNoIjoiODk5YmQzZmI4N2JlYmU2MTQ0NDNjNmYzNjI4ZTZiNjMzMmUwOWI2MDEwZWEyMjA4ZTNhYTkxOTZjZDI5MjVjZiJ9", }


async def send_request(session, idx: int):
    try:
        # First try WITHOUT content-type and no body
        headers_no_ct = {k: v for k, v in HEADERS.items() if k.lower() != "content-type"}
        async with session.post(URL, headers=headers_no_ct) as resp:
            if resp.status == 415 or resp.status == 400:
                # Retry with JSON body
                async with session.post(URL, headers={**HEADERS, "content-type": "application/json"}, json={}) as resp2:
                    text2 = await resp2.text()
                    a = 0
                    if resp.status == '201':
                        a += 1
                    print(f"[{idx}] Retry -> Status: {resp2.status}, Body: {text2}", a)
                    return text2
            text = await resp.text()

            print(f"[{idx}] Status: {resp.status}, Body: {text}")
            return text
    except Exception as e:
        print(f"[{idx}] Error: {e}")
        return None


async def run_parallel(total=1000):
    async with aiohttp.ClientSession() as session:
        tasks = [send_request(session, i) for i in range(total)]
        return await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(run_parallel(2000))
# # # # pip install selenium webdriver-manager
# # #
# # # import time
# # # import random
# # # import threading
# # # from selenium import webdriver
# # # from selenium.webdriver.common.by import By
# # # from selenium.webdriver.chrome.service import Service
# # # from selenium.webdriver.support.ui import WebDriverWait
# # # from selenium.webdriver.support import expected_conditions as EC
# # # from webdriver_manager.chrome import ChromeDriverManager
# # #
# # # URL = "https://smmnakrutka.ru/free-telegram-followers"
# # #
# # # def click_loop(driver, idx):
# # #     """Loop that clicks wheel_button every 5–10 minutes in one Chrome window"""
# # #     wait = WebDriverWait(driver, 20)
# # #     while True:
# # #         try:
# # #             button = wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "wheel_button")))
# # #             button.click()
# # #             print(f"[Window {idx}] ✅ Clicked wheel_button")
# # #         except Exception as e:
# # #             print(f"[Window {idx}] ❌ Could not click - {e}")
# # #
# # #         # random delay between 5–10 minutes
# # #         delay = random.randint(1,5)
# # #         print(f"[Window {idx}] ⏳ Waiting {delay//60}m {delay%60}s until next click...")
# # #         time.sleep(delay)
# # #
# # # def open_multiple_chromes(url: str, windows: int = 5):
# # #     options = webdriver.ChromeOptions()
# # #     options.add_argument("--start-maximized")
# # #
# # #     drivers = []
# # #     threads = []
# # #     try:
# # #         for i in range(windows):
# # #             driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
# # #             driver.get(url)
# # #             drivers.append(driver)
# # #
# # #             # start a separate thread for clicking loop
# # #             t = threading.Thread(target=click_loop, args=(driver, i+1), daemon=True)
# # #             t.start()
# # #             threads.append(t)
# # #
# # #         print(f"✅ Opened {windows} Chrome windows. Clicking started!")
# # #
# # #         # keep the main program alive
# # #         input("Press Enter to stop and close all windows...")
# # #
# # #     finally:
# # #         for d in drivers:
# # #             d.quit()
# # #
# # # if __name__ == "__main__":
# # #     open_multiple_chromes(URL, windows=1)
# # import aiohttp
# # import asyncio
# # import json
# #
# # URL = "https://api.gorilla-case.app/v1/games/roulette/spin"
# #
# # HEADERS = {
# #     "accept": "*/*",
# #     "accept-encoding": "gzip, deflate, br, zstd",
# #     "accept-language": "en-US,en;q=0.9",
# #     "content-type": "application/json",
# #     "origin": "https://client.gorilla-case.app",
# #     "referer": "https://client.gorilla-case.app/",
# #     "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
# #                   "AppleWebKit/537.36 (KHTML, like Gecko) "
# #                   "Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0",
# #     "launch-params":"user=%7B%22id%22%3A6588631008%2C%22first_name%22%3A%22%28%E2%96%BA__%E2%97%84%29%20T_T%20X_X%20xusanboyman%22%2C%22last_name%22%3A%22%E2%A0%9B%E2%A0%9B%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A1%B7%E2%A2%B6%E2%A3%A6%E2%A3%B6%E2%A3%B6%E2%A3%A4%E2%A3%A4%E2%A3%A4%E2%A3%80%20%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%B7%E2%A1%80%20%E2%A0%89%E2%A0%89%E2%A0%89%E2%A0%99%E2%A0%BB%E2%A3%BF%E2%A3%BF%E2%A0%BF%E2%A0%BF%E2%A0%9B%E2%A0%9B%E2%A0%9B%E2%A0%BB%E2%A3%BF%E2%A3%BF%E2%A3%87%22%2C%22username%22%3A%22xusanboyman200%22%2C%22language_code%22%3A%22en%22%2C%22photo_url%22%3A%22https%3A%5C%2F%5C%2Ft.me%5C%2Fi%5C%2Fuserpic%5C%2F320%5C%2FABKucBBOPE9qSGZbrWEF4xW6wrAlil-YqDxjQfABvEOlAI0lJIBU15Q2npDYdUbN.svg%22%7D&chat_instance=-3234088089658042812&chat_type=channel&auth_date=1759394558&signature=KN0SQ_sGagKnvfNZxTD5_gB-APWyDi9GBrKHq5CQOXOBxQpqGsYogkOkUz4osqYG2qLdn46ujpejVx2jGNZzBw&hash=e0fbabadb821049b7b53b07cd38fb75ca9f5fa4df71804d6e5306be5702a9c8d"
# #     # add more headers if the API requires auth/cookies
# # }
# #
# # PAYLOAD = {
# #     "caseUid": "5a76351f-e721-4bb9-8fa2-a383a2879cac",
# #     "currency": "none",
# #     "demo": False
# # }
# #
# #
# # async def spin(session, idx):
# #     try:
# #         async with session.post(URL, headers=HEADERS, json=PAYLOAD) as resp:
# #             try:
# #                 text = await resp.text(errors="ignore")  # ignore bad chars
# #             except UnicodeDecodeError:
# #                 text = (await resp.read()).hex()[:200]  # fallback: show as hex
# #             print(f"[{idx}] Status: {resp.status}, Body: {text[:200]}")
# #             return resp.status
# #     except Exception as e:
# #         print(f"[{idx}] Error: {e}")
# #         return None
# #
# #
# #
# # async def main():
# #     async with aiohttp.ClientSession() as session:
# #         tasks = [spin(session, i) for i in range(1, 101)]
# #         results = await asyncio.gather(*tasks)
# #
# #     # Count status codes
# #     from collections import Counter
# #     counts = Counter(results)
# #     print("\nSummary:", dict(counts))
# #
# #
# # if __name__ == "__main__":
# #     asyncio.run(main())
# #
# import aiohttp
# import asyncio
# import random
# from collections import Counter
#
# URL = "https://api.tgmrkt.io/api/v1/lootboxes/roll"
#
# HEADERS = {
#     "accept": "*/*",
#     "accept-encoding": "gzip, deflate, br, zstd",
#     "accept-language": "en-US,en;q=0.9",
#     "content-type": "application/json",
#     "origin": "https://cdn.tgmrkt.io",
#     "referer": "https://cdn.tgmrkt.io/",
#     "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
#                   "AppleWebKit/537.36 (KHTML, like Gecko) "
#                   "Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0",
#     "authorization": "54f40c6f-8082-4716-89ec-65d2bcb98b79"
# }
#
# # Payloads
# PAYLOADS =     {
#     "lootboxName": "3_ton_infl_digitality",
#     "isDemo": True
# }
#
#
#
# async def spin(session, idx):
#     payload = PAYLOADS # pick randomly
#     try:
#         async with session.post(URL, headers=HEADERS, data=payload) as resp:
#             try:
#                 text = await resp.text(errors="ignore")  # decode if possible
#             except Exception:
#                 text = (await resp.read()).hex()[:200]  # fallback: hex
#             print(f"[{idx}] Status: {resp.status}, Payload: {payload}, Body: {text[:200]}")
#             return resp.status
#     except Exception as e:
#         print(f"[{idx}] Error: {e}")
#         return None
#
#
# async def main():
#     async with aiohttp.ClientSession() as session:
#         tasks = [spin(session, i) for i in range(1, 2)]
#         results = await asyncio.gather(*tasks)
#
#     counts = Counter(results)
#     print("\nSummary:", dict(counts))
#
#
# if __name__ == "__main__":
#     asyncio.run(main())
#
