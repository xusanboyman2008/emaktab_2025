# import asyncio
# import websockets
# import json
# import binascii
# import re
# import struct
#
# url = """
# wss://director.voidgame.io/?t=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIyYzdlY2EyZi1jZTU0LTQxYzYtOGFiOS1hODNiNDI3MDY2OGEiLCJpYXQiOjE3NTk3NzA0OTMsIm5iZiI6MTc1OTc3MDQ5MywiZXhwIjoxNzYwNjM0NDkzLCJhdWQiOiJ2b2lkZ2FtZV9iYWNrZW5kIiwiaXNzIjoiaHR0cHM6Ly9hcHAudm9pZGdhbWUuaW8vIiwianRpIjoiODRiYjkxNjktOWFkOC00Mzc5LWEwNDctMDdkMjg3ZDI3YmY5In0.pshND9MboBAZJr8nyZBzgVS8hrNV4C8_SkrFf9KfAQU&gameMode=RANKED_TEAMS
# """
#
# def extract_from_binary(data: bytes):
#     """Extract human-readable info from binary game update."""
#     output = []
#
#     # Extract strings (names, skins, URLs)
#     strings = re.findall(b'[\x20-\x7e]{3,}', data)
#     if strings:
#         output.append("📝 Strings found:")
#         for s in strings:
#             try:
#                 output.append(f"  - {s.decode('utf-8')}")
#             except:
#                 pass
#
#     # Possible cell IDs (uint32 little-endian, reasonable range)
#     output.append("\n🆔 Possible Cell IDs:")
#     for i in range(0, len(data), 4):
#         if i + 4 <= len(data):
#             id_val = struct.unpack('<I', data[i:i+4])[0]
#             if 1 <= id_val <= 20000:  # Typical cell ID range
#                 output.append(f"  Offset {i}: {id_val}")
#
#     # Possible positions (int32 LE / 5.0 for pixel coords)
#     output.append("\n📍 Possible Positions (x/y /5):")
#     pos_count = 0
#     for i in range(0, len(data), 8):  # Assume pairs of x,y
#         if i + 8 <= len(data):
#             x = struct.unpack('<i', data[i:i+4])[0] / 5.0
#             y = struct.unpack('<i', data[i+4:i+8])[0] / 5.0
#             if -20000 < x < 20000 and -20000 < y < 20000:
#                 output.append(f"  Offset {i}: ({x:.1f}, {y:.1f})")
#                 pos_count += 1
#                 if pos_count >= 20:  # Limit to avoid spam
#                     break
#
#     # Possible sizes (uint16 LE)
#     output.append("\n📏 Possible Sizes:")
#     size_count = 0
#     for i in range(1, len(data), 4):  # Offset to avoid overlap
#         if i + 2 <= len(data):
#             size = struct.unpack('<H', data[i:i+2])[0]
#             if 10 <= size <= 2000:
#                 output.append(f"  Offset {i}: {size}")
#                 size_count += 1
#                 if size_count >= 20:
#                     break
#
#     # Possible colors (3 consecutive bytes 0-255, skip non-color like 0x00)
#     output.append("\n🎨 Possible Colors (RGB):")
#     color_count = 0
#     for i in range(0, len(data) - 2, 3):
#         if i + 3 <= len(data):
#             r, g, b = data[i:i+3]
#             if 10 <= r <= 255 and 10 <= g <= 255 and 10 <= b <= 255:  # Skip black/transparent
#                 output.append(f"  Offset {i}: RGB({r}, {g}, {b})")
#                 color_count += 1
#                 if color_count >= 10:
#                     break
#
#     return "\n".join(output) if output else "No extractable data."
#
# async def main():
#     async with websockets.connect(url) as ws:
#         print("✅ Connected")
#         async for message in ws:
#             print(message)
#             if isinstance(message, bytes):
#                 first_byte = message[0]
#                 try:
#                     if first_byte == 0x93:
#                         # UUID
#                         uuid_str = message[1:-1].decode('utf-8')
#                         print(f"🔑 UUID: {uuid_str}")
#                     elif len(message) > 1 and message[1:2] in [b'd', b'\x90']:
#                         # JSON
#                         json_str = message[1:-1].decode('utf-8')
#                         parsed = json.loads(json_str)
#                         print(f"📄 {message[1:2].decode('utf-8', errors='ignore')}JSON: {json.dumps(parsed, indent=2)}")
#                     elif first_byte == 0x10:
#                         # Binary world update - extract readable parts
#                         print("🌍 World Update:")
#                         readable = extract_from_binary(message)
#                         print(readable)
#                     else:
#                         # Other binary: hex dump
#                         hex_dump = binascii.hexlify(message).decode('utf-8')
#                         print(f"🔢 Binary (hex): {hex_dump[:200]}...")  # Truncate long ones
#                 except Exception as e:
#                     print(f"❌ Parse error: {e}")
#                     print(f"📩 Raw: {repr(message)}")
#                     print(f"🔢 Hex: {binascii.hexlify(message).decode('utf-8')}")
#             else:
#                 print(f"📩 Text: {message}")
#
# asyncio.run(main())
#
#
#
import asyncio

import aiohttp

URL = "https://onegift.work/api/graphql"

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
    "authorization": "query_id=AAHgh7YIAwAAAOCHtgheXcvS&user=%7B%22id%22%3A6588631008%2C%22first_name%22%3A%22%28%E2%96%BA__%E2%97%84%29%20T_T%20X_X%20xusanboyman%22%2C%22last_name%22%3A%22%E2%A0%9B%E2%A0%9B%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A1%B7%E2%A2%B6%E2%A3%A6%E2%A3%B6%E2%A3%B6%E2%A3%A4%E2%A3%A4%E2%A3%A4%E2%A3%80%20%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%B7%E2%A1%80%20%E2%A0%89%E2%A0%89%E2%A0%89%E2%A0%99%E2%A0%BB%E2%A3%BF%E2%A3%BF%E2%A0%BF%E2%A0%BF%E2%A0%9B%E2%A0%9B%E2%A0%9B%E2%A0%BB%E2%A3%BF%E2%A3%BF%E2%A3%87%22%2C%22username%22%3A%22xusanboyman200%22%2C%22language_code%22%3A%22en%22%2C%22allows_write_to_pm%22%3Atrue%2C%22photo_url%22%3A%22https%3A%5C%2F%5C%2Ft.me%5C%2Fi%5C%2Fuserpic%5C%2F320%5C%2FABKucBBOPE9qSGZbrWEF4xW6wrAlil-YqDxjQfABvEOlAI0lJIBU15Q2npDYdUbN.svg%22%7D&auth_date=1760257459&signature=lVqhnEk7UPFuCvLu9DcVK---q4Ir-6n5QSEXhaZwS8E0IIjaChRobc6a2bQ3n73EiqST8K4HQIY7emiDXlDgAQ&hash=fbcacb29ad45a9fb3b547ff1a36ded76d55a71180914bb8ea3c4760cae292eca",
    "cookie": "__ddg9_=84.54.66.177; __ddg1_=fDEXvMAfPD0HG2WFl3ag; __ddg8_=kdBmCKW0VrpbPkD6; __ddg10_=1760257482"
}


payload = {
    "operationName": "OpenCase",
    "variables": {
        "caseId": "2",
        "spinsCount": 1
    },
    "query": "mutation OpenCase($caseId: String!, $spinsCount: Float!) {\n  openCase(caseId: $caseId, spinsCount: $spinsCount) {\n    id\n    giftId\n    originalGiftId\n    title\n    background\n    rarity_permille\n    slug\n    amount\n    animationUrl\n    type\n    win_amount\n    starsAmount\n    starsGiftId\n    __typename\n  }\n}"
}

async def send_request(session, idx: int):
    try:
        # First try WITHOUT content-type and no body
        headers_no_ct = {k: v for k, v in HEADERS.items() if k.lower() != "content-type"}
        async with session.post(URL, headers=headers_no_ct) as resp:
            if resp.status == 415 or resp.status == 400:
                # Retry with JSON body
                async with session.post(URL, headers={**HEADERS, "content-type": "application/json"}, json=payload) as resp2:
                    text2 = await resp2.text()
                    a = 0
                    if resp2.status == '201':
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
    asyncio.run(run_parallel(100))
# # # # # # pip install selenium webdriver-manager
# # # # #
# # # # # import time
# # # # # import random
# # # # # import threading
# # # # # from selenium import webdriver
# # # # # from selenium.webdriver.common.by import By
# # # # # from selenium.webdriver.chrome.service import Service
# # # # # from selenium.webdriver.support.ui import WebDriverWait
# # # # # from selenium.webdriver.support import expected_conditions as EC
# # # # # from webdriver_manager.chrome import ChromeDriverManager
# # # # #
# # # # # URL = "https://smmnakrutka.ru/free-telegram-followers"
# # # # #
# # # # # def click_loop(driver, idx):
# # # # #     """Loop that clicks wheel_button every 5–10 minutes in one Chrome window"""
# # # # #     wait = WebDriverWait(driver, 20)
# # # # #     while True:
# # # # #         try:
# # # # #             button = wait.until(EC.element_to_be_clickable((By.CLASS_NAME, "wheel_button")))
# # # # #             button.click()
# # # # #             print(f"[Window {idx}] ✅ Clicked wheel_button")
# # # # #         except Exception as e:
# # # # #             print(f"[Window {idx}] ❌ Could not click - {e}")
# # # # #
# # # # #         # random delay between 5–10 minutes
# # # # #         delay = random.randint(1,5)
# # # # #         print(f"[Window {idx}] ⏳ Waiting {delay//60}m {delay%60}s until next click...")
# # # # #         time.sleep(delay)
# # # # #
# # # # # def open_multiple_chromes(url: str, windows: int = 5):
# # # # #     options = webdriver.ChromeOptions()
# # # # #     options.add_argument("--start-maximized")
# # # # #
# # # # #     drivers = []
# # # # #     threads = []
# # # # #     try:
# # # # #         for i in range(windows):
# # # # #             driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
# # # # #             driver.get(url)
# # # # #             drivers.append(driver)
# # # # #
# # # # #             # start a separate thread for clicking loop
# # # # #             t = threading.Thread(target=click_loop, args=(driver, i+1), daemon=True)
# # # # #             t.start()
# # # # #             threads.append(t)
# # # # #
# # # # #         print(f"✅ Opened {windows} Chrome windows. Clicking started!")
# # # # #
# # # # #         # keep the main program alive
# # # # #         input("Press Enter to stop and close all windows...")
# # # # #
# # # # #     finally:
# # # # #         for d in drivers:
# # # # #             d.quit()
# # # # #
# # # # # if __name__ == "__main__":
# # # # #     open_multiple_chromes(URL, windows=1)
# # # # import aiohttp
# # # # import asyncio
# # # # import json
# # # #
# # # # URL = "https://api.gorilla-case.app/v1/games/roulette/spin"
# # # #
# # # # HEADERS = {
# # # #     "accept": "*/*",
# # # #     "accept-encoding": "gzip, deflate, br, zstd",
# # # #     "accept-language": "en-US,en;q=0.9",
# # # #     "content-type": "application/json",
# # # #     "origin": "https://client.gorilla-case.app",
# # # #     "referer": "https://client.gorilla-case.app/",
# # # #     "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
# # # #                   "AppleWebKit/537.36 (KHTML, like Gecko) "
# # # #                   "Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0",
# # # #     "launch-params":"user=%7B%22id%22%3A6588631008%2C%22first_name%22%3A%22%28%E2%96%BA__%E2%97%84%29%20T_T%20X_X%20xusanboyman%22%2C%22last_name%22%3A%22%E2%A0%9B%E2%A0%9B%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A1%B7%E2%A2%B6%E2%A3%A6%E2%A3%B6%E2%A3%B6%E2%A3%A4%E2%A3%A4%E2%A3%A4%E2%A3%80%20%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%BF%E2%A3%B7%E2%A1%80%20%E2%A0%89%E2%A0%89%E2%A0%89%E2%A0%99%E2%A0%BB%E2%A3%BF%E2%A3%BF%E2%A0%BF%E2%A0%BF%E2%A0%9B%E2%A0%9B%E2%A0%9B%E2%A0%BB%E2%A3%BF%E2%A3%BF%E2%A3%87%22%2C%22username%22%3A%22xusanboyman200%22%2C%22language_code%22%3A%22en%22%2C%22photo_url%22%3A%22https%3A%5C%2F%5C%2Ft.me%5C%2Fi%5C%2Fuserpic%5C%2F320%5C%2FABKucBBOPE9qSGZbrWEF4xW6wrAlil-YqDxjQfABvEOlAI0lJIBU15Q2npDYdUbN.svg%22%7D&chat_instance=-3234088089658042812&chat_type=channel&auth_date=1759394558&signature=KN0SQ_sGagKnvfNZxTD5_gB-APWyDi9GBrKHq5CQOXOBxQpqGsYogkOkUz4osqYG2qLdn46ujpejVx2jGNZzBw&hash=e0fbabadb821049b7b53b07cd38fb75ca9f5fa4df71804d6e5306be5702a9c8d"
# # # #     # add more headers if the API requires auth/cookies
# # # # }
# # # #
# # # # PAYLOAD = {
# # # #     "caseUid": "5a76351f-e721-4bb9-8fa2-a383a2879cac",
# # # #     "currency": "none",
# # # #     "demo": False
# # # # }
# # # #
# # # #
# # # # async def spin(session, idx):
# # # #     try:
# # # #         async with session.post(URL, headers=HEADERS, json=PAYLOAD) as resp:
# # # #             try:
# # # #                 text = await resp.text(errors="ignore")  # ignore bad chars
# # # #             except UnicodeDecodeError:
# # # #                 text = (await resp.read()).hex()[:200]  # fallback: show as hex
# # # #             print(f"[{idx}] Status: {resp.status}, Body: {text[:200]}")
# # # #             return resp.status
# # # #     except Exception as e:
# # # #         print(f"[{idx}] Error: {e}")
# # # #         return None
# # # #
# # # #
# # # #
# # # # async def main():
# # # #     async with aiohttp.ClientSession() as session:
# # # #         tasks = [spin(session, i) for i in range(1, 101)]
# # # #         results = await asyncio.gather(*tasks)
# # # #
# # # #     # Count status codes
# # # #     from collections import Counter
# # # #     counts = Counter(results)
# # # #     print("\nSummary:", dict(counts))
# # # #
# # # #
# # # # if __name__ == "__main__":
# # # #     asyncio.run(main())
# # # #
# # # import aiohttp
# # # import asyncio
# # # import random
# # # from collections import Counter
# # #
# # # URL = "https://api.tgmrkt.io/api/v1/lootboxes/roll"
# # #
# # # HEADERS = {
# # #     "accept": "*/*",
# # #     "accept-encoding": "gzip, deflate, br, zstd",
# # #     "accept-language": "en-US,en;q=0.9",
# # #     "content-type": "application/json",
# # #     "origin": "https://cdn.tgmrkt.io",
# # #     "referer": "https://cdn.tgmrkt.io/",
# # #     "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
# # #                   "AppleWebKit/537.36 (KHTML, like Gecko) "
# # #                   "Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0",
# # #     "authorization": "54f40c6f-8082-4716-89ec-65d2bcb98b79"
# # # }
# # #
# # # # Payloads
# # # PAYLOADS =     {
# # #     "lootboxName": "3_ton_infl_digitality",
# # #     "isDemo": True
# # # }
# # #
# # #
# # #
# # # async def spin(session, idx):
# # #     payload = PAYLOADS # pick randomly
# # #     try:
# # #         async with session.post(URL, headers=HEADERS, data=payload) as resp:
# # #             try:
# # #                 text = await resp.text(errors="ignore")  # decode if possible
# # #             except Exception:
# # #                 text = (await resp.read()).hex()[:200]  # fallback: hex
# # #             print(f"[{idx}] Status: {resp.status}, Payload: {payload}, Body: {text[:200]}")
# # #             return resp.status
# # #     except Exception as e:
# # #         print(f"[{idx}] Error: {e}")
# # #         return None
# # #
# # #
# # # async def main():
# # #     async with aiohttp.ClientSession() as session:
# # #         tasks = [spin(session, i) for i in range(1, 2)]
# # #         results = await asyncio.gather(*tasks)
# # #
# # #     counts = Counter(results)
# # #     print("\nSummary:", dict(counts))
# # #
# # #
# # # if __name__ == "__main__":
# # #     asyncio.run(main())
# # #
