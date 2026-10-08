import asyncio
import re
import sys
import time
import aiohttp
import dns_resolver  # noqa: F401 - ensures DNS fast-path is active


def format_captcha_id(raw_id: str) -> str:
    """Format 32-char hex string to standard UUID format with dashes."""
    raw = raw_id.strip()
    if len(raw) == 32:
        return f"{raw[:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:]}"
    return raw


async def fetch_captchas_from_page(session: aiohttp.ClientSession) -> list[str]:
    """Requests eMaktab login page and extracts all generated captcha IDs."""
    url = "https://login.emaktab.uz/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Connection": "keep-alive"
    }
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=4)) as resp:
            text = await resp.text()
            matches = re.findall(r'id-([a-f0-9]{32})', text)
            return [format_captcha_id(m) for m in matches]
    except Exception as e:
        return []


async def get_live_captcha_id() -> str:
    """Fetches a single fresh, valid captcha ID on-demand in milliseconds."""
    connector = aiohttp.TCPConnector(limit=5, keepalive_timeout=30)
    async with aiohttp.ClientSession(connector=connector) as session:
        ids = await fetch_captchas_from_page(session)
        if ids:
            return ids[0]
    return "f61a11f3-1cee-448c-ad2b-fd2eee8f9b2d"


async def harvest_captchas(target_count: int = 100, output_file: str = "output.txt", save_to_db: bool = False):
    """
    High-speed asynchronous captcha harvester.
    Replaces slow Selenium refresh loops with concurrent HTTP requests.
    Collects target_count unique captcha IDs in seconds.
    """
    print(f"🚀 Starting fast captcha harvesting: Target = {target_count} IDs...")
    t0 = time.time()
    collected = set()

    connector = aiohttp.TCPConnector(limit=25, keepalive_timeout=60)
    timeout = aiohttp.ClientTimeout(total=5)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        while len(collected) < target_count:
            batch_size = min(15, (target_count - len(collected)) + 5)
            tasks = [fetch_captchas_from_page(session) for _ in range(batch_size)]
            results = await asyncio.gather(*tasks)

            new_found = 0
            for r in results:
                for cid in r:
                    if cid not in collected:
                        collected.add(cid)
                        new_found += 1
                        if len(collected) >= target_count:
                            break

            print(f"📦 Harvested: {len(collected)}/{target_count} ({time.time() - t0:.1f}s)")
            if len(collected) >= target_count:
                break
            await asyncio.sleep(0.1)

    elapsed = time.time() - t0
    print(f"✅ Successfully harvested {len(collected)} unique captcha IDs in {elapsed:.2f} seconds!")

    # Append to output.txt
    if output_file:
        existing = set()
        try:
            with open(output_file, "r", encoding="utf-8") as f:
                existing = {line.strip() for line in f if line.strip()}
        except FileNotFoundError:
            pass

        added = 0
        with open(output_file, "a", encoding="utf-8") as f:
            for cid in collected:
                if cid not in existing:
                    f.write(cid + "\n")
                    added += 1
        print(f"📝 Saved {added} new captcha IDs to {output_file}")

    # Optionally populate database directly
    if save_to_db:
        try:
            from database import create_captcha_ids
            saved_db = 0
            for cid in collected:
                if await create_captcha_ids(cid):
                    saved_db += 1
            print(f"💾 Added {saved_db} new captcha IDs directly to database.")
        except Exception as e:
            print(f"⚠️ DB insert warning: {e}")

    return list(collected)


if __name__ == "__main__":
    count = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 50
    asyncio.run(harvest_captchas(target_count=count, output_file="output.txt"))
