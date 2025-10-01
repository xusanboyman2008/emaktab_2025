import aiohttp
import asyncio

URL = "https://market.notpixel.org/api/v1/product/owned?category=pending&type=sticker"

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
    "x-hash": "eyJ1c2VyIjoie1wiaWRcIjo4MjA0OTQzMDI4LFwiZmlyc3RfbmFtZVwiOlwiLlwiLFwibGFzdF9uYW1lXCI6XCJcIixcInVzZXJuYW1lXCI6XCJSTkdfU0NBTVwiLFwibGFuZ3VhZ2VfY29kZVwiOlwiZW5cIixcImFsbG93c193cml0ZV90b19wbVwiOnRydWUsXCJwaG90b191cmxcIjpcImh0dHBzOlxcL1xcL3QubWVcXC9pXFwvdXNlcnBpY1xcLzMyMFxcLzB6cHZRRl9fV3BmZWNJQm5PN2FObkpaTENsdWl3d3FIWFkyaGxYbkhKQ01QODBIaFVBSjVLODNEdGZwZmdhMVAuc3ZnXCJ9IiwiY2hhdF9pbnN0YW5jZSI6IjcwMDEzOTgxNDU0MTAyMTQ3OTYiLCJjaGF0X3R5cGUiOiJzZW5kZXIiLCJhdXRoX2RhdGUiOiIxNzU5Mjk3Njg0Iiwic2lnbmF0dXJlIjoiUUFmYzM4aTFvcG9wUWFrWG0yd1J6MkhpN0dZekROVVdUVHJsTGZMbnp0T25LSDZKTE9NUGhLNFJ2ak9rTjNFSE81VFdENEJ4RFJOUzJKSXJHekF1QlEiLCJoYXNoIjoiMGIyNTkyYTE5ZjQ1NTBiOWQyYjdiNTFmMTU3MzAzYWI3MjhkNjM3YjU2YjYwNTcyMTU2MzlkMDgzNjVhN2VhYSJ9",  # ⚠️ replace with real one
}


async def send_request(session, idx: int):
    try:
        # First try WITHOUT content-type and no body
        headers_no_ct = {k: v for k, v in HEADERS.items() if k.lower() != "content-type"}
        async with session.get(URL, headers=headers_no_ct) as resp:
            if resp.status == 415 or resp.status == 400:
                # Retry with JSON body
                async with session.get(URL, headers={**HEADERS, "content-type": "application/json"}, json={}) as resp2:
                    text2 = await resp2.text()
                    a= 0
                    if resp.status == '201':
                        a +=1
                    print(f"[{idx}] Retry -> Status: {resp2.status}, Body: {text2}",a)
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
    asyncio.run(run_parallel(1))
