# import aiohttp
# import asyncio
#
# URL = "https://market.notpixel.org/api/v1/task/claim/1"
#
# HEADERS = {
#     "accept": "application/json, text/plain, */*",
#     "accept-encoding": "gzip, deflate, br, zstd",
#     "accept-language": "en-US,en;q=0.9",
#     "origin": "https://market.notpixel.org",
#     "referer": "https://market.notpixel.org/profile",
#     "sec-fetch-dest": "empty",
#     "sec-fetch-mode": "cors",
#     "sec-fetch-site": "same-origin",
#     "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
#                   "AppleWebKit/537.36 (KHTML, like Gecko) "
#                   "Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0",
#     "x-hash": "eyJ1c2VyIjoie1wiaWRcIjo3MDU3OTEwODY4LFwiZmlyc3RfbmFtZVwiOlwi4pm+77iPXCIsXCJsYXN0X25hbWVcIjpcIlwiLFwidXNlcm5hbWVcIjpcIlVWWl9RaXJvbF8wMVwiLFwibGFuZ3VhZ2VfY29kZVwiOlwiZW5cIixcInBob3RvX3VybFwiOlwiaHR0cHM6XFwvXFwvdC5tZVxcL2lcXC91c2VycGljXFwvMzIwXFwvYkg0NFBHdU1zY0JkUkZOMXl2SmItNER1MnlUZU1iaXNDZDBaSWVRV0k1T3BVN3dSOGYzWHc3bVhPenAzaXRycS5zdmdcIn0iLCJjaGF0X2luc3RhbmNlIjoiLTY3MzI4NzMwNjAwMzMyMzQyNyIsImNoYXRfdHlwZSI6InByaXZhdGUiLCJzdGFydF9wYXJhbSI6InJfNjU4ODYzMTAwOCIsImF1dGhfZGF0ZSI6IjE3NTkzNDIwOTciLCJzaWduYXR1cmUiOiJBSXBKVkZTalFFNGs5NGFPWEtnWUdZaGVuN2EySG9LbnR2a05DMmwyR1ZMdF9xeDU0U3QxeEZtMU9NSnlCTnpGQjJBQXY5Q1FBOGd4ci1IXzFNd3BBUSIsImhhc2giOiI4OWMyY2NmMzE3N2ZjZjg2NjE5MzNjYTczOThmOTI0YjAxOTU2ZWRkMjg1NTYyOWY3NzgzNTgyMDMyOTUwNTYyIn0=",  # ⚠️ replace with real one
# }
# # URL = "https://gmeow-api-prod.anomalygames.ai/api/quests"
# # HEADERS = {
# #     "Accept": "*/*",
# #     "Accept-Encoding": "gzip, deflate, br, zstd",
# #     "Accept-Language": "en-US,en;q=0.5",
# #     "Connection": "keep-alive",
# #     "Content-Type": "application/json",
# #     "Host": "gmeow-api-prod.anomalygames.ai",
# #     "Origin": "https://www.gmeow.gg",
# #     "Referer": "https://www.gmeow.gg/",
# #     "Sec-Fetch-Dest": "empty",
# #     "Sec-Fetch-Mode": "cors",
# #     "Sec-Fetch-Site": "cross-site",
# #     "Sec-GPC": "1",
# #     "TE": "trailers",
# #     "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:143.0) Gecko/20100101 Firefox/143.0"
# # }
# #
# # # Payload
# # payload = {
# #     "novalink_user_id": "yc0u3xkdjorafmhun4ae1ykk",
# #     "quest_id":157,
# # }
# async def send_request(session, idx: int):
#     try:
#         # First try WITHOUT content-type and no body
#         headers_no_ct = {k: v for k, v in HEADERS.items() if k.lower() != "content-type"}
#         async with session.post(URL, headers=headers_no_ct) as resp:
#             if resp.status == 415 or resp.status == 400:
#                 # Retry with JSON body
#                 async with session.post(URL,headers={**HEADERS, "content-type": "application/json"}, json={}) as resp2:
#                     text2 = await resp2.text()
#                     a= 0
#                     if resp.status == '201':
#                         a +=1
#                     print(f"[{idx}] Retry -> Status: {resp2.status}, Body: {text2}",a)
#                     return text2
#             text = await resp.text()
#
#             print(f"[{idx}] Status: {resp.status}, Body: {text}")
#             return text
#     except Exception as e:
#         print(f"[{idx}] Error: {e}")
#         return None
#
#
# async def run_parallel(total=1000):
#     async with aiohttp.ClientSession() as session:
#         tasks = [send_request(session, i) for i in range(total)]
#         return await asyncio.gather(*tasks)
#
#
# if __name__ == "__main__":
#     asyncio.run(run_parallel(2000))
# pip install selenium webdriver-manager

import time
import random
import threading
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

URL = "https://smmnakrutka.ru/free-telegram-followers"

def click_loop(driver, idx):
    """Loop that clicks wheel_button every 5–10 minutes in one Chrome window"""
    wait = WebDriverWait(driver, 20)
    while True:
        try:
            button = wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "wheel_button")))
            button.click()
            print(f"[Window {idx}] ✅ Clicked wheel_button")
        except Exception as e:
            print(f"[Window {idx}] ❌ Could not click - {e}")

        # random delay between 5–10 minutes
        delay = random.randint(1,5)
        print(f"[Window {idx}] ⏳ Waiting {delay//60}m {delay%60}s until next click...")
        time.sleep(delay)

def open_multiple_chromes(url: str, windows: int = 5):
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")

    drivers = []
    threads = []
    try:
        for i in range(windows):
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
            driver.get(url)
            drivers.append(driver)

            # start a separate thread for clicking loop
            t = threading.Thread(target=click_loop, args=(driver, i+1), daemon=True)
            t.start()
            threads.append(t)

        print(f"✅ Opened {windows} Chrome windows. Clicking started!")

        # keep the main program alive
        input("Press Enter to stop and close all windows...")

    finally:
        for d in drivers:
            d.quit()

if __name__ == "__main__":
    open_multiple_chromes(URL, windows=1)
