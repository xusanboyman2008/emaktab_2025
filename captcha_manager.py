import asyncio
import os
import sqlite3
import time
import aiohttp
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from captcha_finder import fetch_captchas_from_page, get_live_captcha_id
from captcha_code import get_captcha_code

DB_PATH = '/home/ubuntu/emaktab_2025/database.sqlite3' if os.path.exists('/home/ubuntu/emaktab_2025/database.sqlite3') else '/home/xusanboyman/emaktab_2025/database.sqlite3'
UZB_TZ = ZoneInfo("Asia/Tashkent")


def _get_db_connection():
    return sqlite3.connect(DB_PATH)


async def verify_captcha(captcha_id: str) -> tuple[bool, str | None]:
    """
    Verifies that a captcha ID is valid by downloading its image and solving with OCR.
    Returns (True, solved_code) if valid digits (>=4) are returned, else (False, None).
    """
    if not captcha_id:
        return False, None
    try:
        code = await asyncio.to_thread(get_captcha_code, captcha_id)
        if code and len(code) >= 4 and code.isdigit():
            return True, code
        return False, None
    except Exception:
        return False, None


async def harvest_fresh_captchas(target_count: int = 10) -> list[str]:
    """
    Harvests fresh, tested and working captchas from eMaktab.
    Saves verified captchas into the Captcha_ids database table.
    """
    print(f"🚀 [CAPTCHA] Harvesting {target_count} fresh working captchas...")
    connector = aiohttp.TCPConnector(limit=15, keepalive_timeout=30)
    timeout = aiohttp.ClientTimeout(total=6)
    
    saved_captchas = []
    attempts = 0
    max_attempts = 15

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        while len(saved_captchas) < target_count and attempts < max_attempts:
            attempts += 1
            # Fetch candidate IDs from eMaktab login page
            raw_cids = await fetch_captchas_from_page(session)
            if not raw_cids:
                await asyncio.sleep(0.5)
                continue

            con = _get_db_connection()
            cur = con.cursor()
            
            for cid in raw_cids:
                if len(saved_captchas) >= target_count:
                    break
                
                # Check if already in DB
                cur.execute("SELECT id FROM Captcha_ids WHERE captcha_id = ?;", (cid,))
                if cur.fetchone():
                    continue

                # Verify and solve via OCR
                is_valid, solved_code = await verify_captcha(cid)
                if is_valid and solved_code:
                    try:
                        cur.execute(
                            "INSERT INTO Captcha_ids (captcha_id, is_occupied, last_used) VALUES (?, 0, datetime('now'));",
                            (cid,)
                        )
                        con.commit()
                        saved_captchas.append(cid)
                        print(f"✅ [CAPTCHA] Verified & saved: {cid[:8]}... (code: {solved_code}) [{len(saved_captchas)}/{target_count}]")
                    except sqlite3.IntegrityError:
                        pass

            con.close()
            await asyncio.sleep(0.3)

    print(f"🎯 [CAPTCHA] Harvest complete: {len(saved_captchas)}/{target_count} captchas saved to DB.")
    return saved_captchas


async def cleanup_old_or_invalid_captchas(max_pool_size: int = 25) -> dict:
    """
    Tests existing captchas in Captcha_ids.
    Removes dead/unresponsive ones and trims the oldest to maintain a clean pool of max_pool_size.
    """
    con = _get_db_connection()
    cur = con.cursor()
    cur.execute("SELECT id, captcha_id FROM Captcha_ids ORDER BY id ASC;")
    rows = cur.fetchall()
    con.close()

    if not rows:
        return {"deleted_invalid": 0, "deleted_oldest": 0, "remaining": 0}

    deleted_invalid = 0
    # Test existing captchas for responsiveness
    for cid_id, cid in rows:
        is_valid, _ = await verify_captcha(cid)
        if not is_valid:
            con = _get_db_connection()
            cur = con.cursor()
            cur.execute("DELETE FROM Captcha_ids WHERE id = ?;", (cid_id,))
            con.commit()
            con.close()
            deleted_invalid += 1

    # Check remaining count and prune oldest if exceeding max_pool_size
    con = _get_db_connection()
    cur = con.cursor()
    cur.execute("SELECT id FROM Captcha_ids ORDER BY id ASC;")
    current_ids = [r[0] for r in cur.fetchall()]
    
    deleted_oldest = 0
    if len(current_ids) > max_pool_size:
        excess = len(current_ids) - max_pool_size
        to_delete = current_ids[:excess]
        cur.execute(f"DELETE FROM Captcha_ids WHERE id IN ({','.join('?' for _ in to_delete)});", to_delete)
        con.commit()
        deleted_oldest = excess

    cur.execute("SELECT count(*) FROM Captcha_ids;")
    remaining = cur.fetchone()[0]
    con.close()

    print(f"🧹 [CAPTCHA] Cleaned: {deleted_invalid} invalid, {deleted_oldest} oldest pruned. Remaining pool: {remaining}")
    return {
        "deleted_invalid": deleted_invalid,
        "deleted_oldest": deleted_oldest,
        "remaining": remaining
    }


async def nightly_captcha_cycle(target_new: int = 10) -> dict:
    """
    Executed every night in the middle of the night (03:00 Tashkent time):
    1. Prunes dead or outdated captchas.
    2. Harvests fresh working captchas to replenish pool.
    """
    print("🌙 [CAPTCHA] Starting nightly maintenance cycle...")
    clean_res = await cleanup_old_or_invalid_captchas(max_pool_size=25)
    harvested = await harvest_fresh_captchas(target_count=target_new)
    
    con = _get_db_connection()
    cur = con.cursor()
    cur.execute("SELECT count(*) FROM Captcha_ids;")
    total_now = cur.fetchone()[0]
    con.close()

    summary = {
        "timestamp": datetime.now(UZB_TZ).strftime("%Y-%m-%d %H:%M:%S"),
        "yangi_qoshildi": len(harvested),
        "ochirilgan_yaroqsiz": clean_res["deleted_invalid"],
        "ochirilgan_eski": clean_res["deleted_oldest"],
        "jami_faol_kapchalar": total_now
    }
    print(f"🌟 [CAPTCHA] Nightly cycle completed: {summary}")
    return summary


async def get_ready_captcha() -> tuple[str, str]:
    """
    Gets a fresh, pre-verified captcha ID and solves it on-demand (or uses cached code).
    Updates last_used in DB. If DB is empty, harvests on-demand immediately.
    Returns: (captcha_id, solved_code)
    """
    con = _get_db_connection()
    cur = con.cursor()
    # Prefer unoccupied or oldest used captcha
    cur.execute("SELECT id, captcha_id FROM Captcha_ids WHERE is_occupied = 0 ORDER BY id DESC LIMIT 1;")
    row = cur.fetchone()
    if not row:
        cur.execute("SELECT id, captcha_id FROM Captcha_ids ORDER BY last_used ASC LIMIT 1;")
        row = cur.fetchone()

    cid = None
    if row:
        cid_id, cid = row
        cur.execute("UPDATE Captcha_ids SET last_used = datetime('now'), is_occupied = 1 WHERE id = ?;", (cid_id,))
        con.commit()
    con.close()

    if not cid:
        # Fallback: fetch live on-demand
        cid = await get_live_captcha_id()

    # Solve via OCR
    code = await asyncio.to_thread(get_captcha_code, cid)
    if not code:
        # If solving failed, fetch fresh live captcha
        cid = await get_live_captcha_id()
        code = await asyncio.to_thread(get_captcha_code, cid)

    return cid, code or "1234"


def get_captcha_pool_status() -> dict:
    """Returns overview of the current captcha pool."""
    con = _get_db_connection()
    cur = con.cursor()
    cur.execute("SELECT count(*) FROM Captcha_ids;")
    total = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM Captcha_ids WHERE is_occupied = 0;")
    free_cnt = cur.fetchone()[0]
    cur.execute("SELECT min(last_used), max(last_used) FROM Captcha_ids;")
    min_date, max_date = cur.fetchone()
    con.close()
    return {
        "jami_kapchalar": total,
        "bosh_kapchalar": free_cnt,
        "band_kapchalar": total - free_cnt,
        "eng_eski_sana": str(min_date),
        "eng_yangi_sana": str(max_date)
    }


async def run_captcha_scheduler():
    """
    Background scheduler for automated captcha maintenance:
    - Runs immediately on startup if pool < 5.
    - Runs nightly at 03:00 Tashkent time.
    """
    # 1. Startup check: replenish immediately if empty or low
    status = get_captcha_pool_status()
    if status["jami_kapchalar"] < 5:
        print(f"⚠️ [CAPTCHA] Pool has only {status['jami_kapchalar']} captchas on startup. Running initial harvest...")
        try:
            await harvest_fresh_captchas(target_count=10)
        except Exception as e:
            print(f"⚠️ [CAPTCHA] Initial harvest error: {e}")

    # 2. Nightly loop at 03:00 AM Tashkent time
    while True:
        now = datetime.now(UZB_TZ)
        target = now.replace(hour=3, minute=0, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        sleep_secs = (target - now).total_seconds()
        print(f"🌙 [CAPTCHA] Keyingi tungi kapcha yangilanishi: {target.strftime('%Y-%m-%d %H:%M')} (kutilmoqda: {sleep_secs:.0f}s)")

        # Wait until target
        while target > datetime.now(UZB_TZ):
            remaining = (target - datetime.now(UZB_TZ)).total_seconds()
            if remaining <= 0:
                break
            await asyncio.sleep(min(60.0, remaining))

        # Run nightly maintenance
        try:
            await nightly_captcha_cycle(target_new=10)
        except Exception as e:
            print(f"⚠️ [CAPTCHA] Tungi siklda xatolik: {e}")
        await asyncio.sleep(120)  # avoid double trigger within same minute
