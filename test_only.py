import aiohttp
import asyncio

URL = "https://market.notpixel.org/api/v1/task/claim/1"

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
    "x-hash": "eyJ1c2VyIjoie1wiaWRcIjo1MzY5NTY3ODEzLFwiZmlyc3RfbmFtZVwiOlwiS0FJUEFLXCIsXCJsYXN0X25hbWVcIjpcIlwiLFwibGFuZ3VhZ2VfY29kZVwiOlwiZW5cIixcInBob3RvX3VybFwiOlwiaHR0cHM6XFwvXFwvdC5tZVxcL2lcXC91c2VycGljXFwvMzIwXFwvenlyUDYyQWM2U29jYkk1V1pwaERRN25YWUFoaTF3b1RwWlB1eHFpRmhWZFFBcG9KNm1xa2w4dXdEakdObGZoNy5zdmdcIn0iLCJjaGF0X2luc3RhbmNlIjoiLTQ5OTU4NzAwNTU2MTQ0NjY0MTUiLCJjaGF0X3R5cGUiOiJwcml2YXRlIiwic3RhcnRfcGFyYW0iOiJyXzY1ODg2MzEwMDgiLCJhdXRoX2RhdGUiOiIxNzU5MjU1NjMzIiwic2lnbmF0dXJlIjoiMFppLTVCX1RTUjhJYWljOG1QeUtzZG9CeGowUGlVYW01Y3l4V2U4S3A5NUZkaERFR0xOS2hKUHc2Sm9iQ3pzSXRjQkNwMlBLVExuY19aQks5eVhoQUEiLCJoYXNoIjoiMjgzZTM5Nzc4YTY5YmFlYTRlMTZjMjQ2ZDBhNzEwMTQwODM3MmM4MzcyMTBhY2Y0NWNlY2IzOTAwNTZiZWNhYSJ9",  # ⚠️ replace with real one
}


async def send_request(session, idx: int):
    try:
        # First try WITHOUT content-type and no body
        headers_no_ct = {k: v for k, v in HEADERS.items() if k.lower() != "content-type"}
        async with session.post(URL, headers=headers_no_ct) as resp:
            if resp.status == 415 or resp.status == 400:
                # Retry with JSON body
                async with session.post(URL, headers={**HEADERS, "content-type": "application/json"}, json={}) as resp2:
                    text2 = await resp2.text()
                    print(f"[{idx}] Retry -> Status: {resp2.status}, Body: {text2}")
                    return text2
            text = await resp.text()
            a= 0
            if resp.status == '201':
                a +=1
            print(f"[{idx}] Status: {resp.status}, Body: {text}",a)
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
