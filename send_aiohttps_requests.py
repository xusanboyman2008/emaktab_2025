import aiohttp
import asyncio
from http.cookies import SimpleCookie
from database import bulk_update_logins, give_captcha_100
from login_by_username import login_by_user

url = "https://login.emaktab.uz"


async def fetch(session, student_id, student, sem):
    headers = {
        "Host": "login.emaktab.uz",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:144.0) Gecko/20100101 Firefox/144.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Sec-GPC": "1",
        "Connection": "keep-alive",
        "Cookie": student.get("last_cookie", ''),
        "Upgrade-Insecure-Requests": "1"
    }

    async with sem:
        try:
            async with session.get(url, headers=headers, allow_redirects=False) as response:
                all_cookies = session.cookie_jar.filter_cookies(url)
                new_cookies = [f"{k}={v.value}" for k, v in all_cookies.items()]
                has_auth = any("UZDnevnikAuth_a" in kv for kv in new_cookies)
                return student_id, has_auth, new_cookies
        except Exception as e:
            print(f"⚠️ Fetch error for {student_id}: {e}")
            return student_id, False, []


async def handle_expired_cookie(sid, student_data, session, sem):
    async with sem:
        username = student_data.get("username")
        password = student_data.get("password")
        captcha_id = await give_captcha_100(student_data.get('login_id'))

        login_len, new_cookie = await login_by_user(
            username, password, use_captcha=True, captcha_id=captcha_id, session=session
        )

        if login_len >= 4 and new_cookie and "UZDnevnikAuth_a" in new_cookie:
            student_data["last_login"] = True
            student_data["last_cookie"] = new_cookie
            return {
                "login_id": student_data.get("login_id"),
                "last_login": True,
                "last_cookie": new_cookie
            }
        else:
            student_data["last_login"] = False
            return {
                "login_id": student_data.get("login_id"),
                "last_login": False,
                "last_cookie": student_data.get("last_cookie", "")
            }


async def cookie_login(students_dict, bot=None):
    sem = asyncio.Semaphore(50)
    connector = aiohttp.TCPConnector(limit=100, ttl_dns_cache=300, keepalive_timeout=60)
    timeout = aiohttp.ClientTimeout(total=20, connect=5)

    db_updates = []

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = [fetch(session, sid, s, sem) for sid, s in students_dict.items()]
        results = await asyncio.gather(*tasks)

        expired_tasks = []
        sem_relogin = asyncio.Semaphore(8)

        for sid, success, new_cookies in results:
            old_cookie = students_dict[sid].get("last_cookie", "")
            cookie = SimpleCookie()
            if old_cookie:
                try:
                    cookie.load(old_cookie)
                except Exception:
                    pass

            for kv in new_cookies:
                key, _, value = kv.partition("=")
                key = key.strip()
                if key:
                    cookie[key] = value

            merged_cookie = "; ".join([f"{k}={v}" for k, v in cookie.items()])
            students_dict[sid]["last_cookie"] = merged_cookie
            students_dict[sid]["last_login"] = success

            if not success:
                expired_tasks.append(handle_expired_cookie(sid, students_dict[sid], session, sem_relogin))
            else:
                if students_dict[sid].get("login_id"):
                    db_updates.append({
                        "login_id": students_dict[sid]["login_id"],
                        "last_login": True,
                        "last_cookie": merged_cookie
                    })

        if expired_tasks:
            relogin_results = await asyncio.gather(*expired_tasks)
            for res in relogin_results:
                if res and res.get("login_id"):
                    db_updates.append(res)

    # Bulk update DB in a single fast transaction
    if db_updates:
        await bulk_update_logins(db_updates)

    return students_dict


async def login_single_username(sid, data, session, sem):
    async with sem:
        username = data.get("username")
        password = data.get("password")

        for attempt in range(2):
            captcha_id = await give_captcha_100(data.get('login_id'))
            login_len, cookie = await login_by_user(
                username, password, use_captcha=True, captcha_id=captcha_id, session=session
            )
            if login_len >= 4 and cookie and "UZDnevnikAuth_a" in cookie:
                data["last_login"] = True
                data["last_cookie"] = cookie
                return {
                    "login_id": data.get("login_id"),
                    "last_login": True,
                    "last_cookie": cookie
                }
            else:
                data["last_login"] = False
                if attempt == 1:
                    return {
                        "login_id": data.get("login_id"),
                        "last_login": False,
                        "last_cookie": data.get("last_cookie", "")
                    }
        return None


async def username_login(students_dict):
    sem = asyncio.Semaphore(8)
    connector = aiohttp.TCPConnector(limit=50, ttl_dns_cache=300, keepalive_timeout=60)
    timeout = aiohttp.ClientTimeout(total=20, connect=5)

    db_updates = []
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = [login_single_username(sid, data, session, sem) for sid, data in students_dict.items()]
        results = await asyncio.gather(*tasks)
        for r in results:
            if r and r.get("login_id"):
                db_updates.append(r)

    if db_updates:
        await bulk_update_logins(db_updates)

    return students_dict


async def send_request_main(students, bot=None):
    cookie_logins = {}
    username_logins = {}

    for sid, data in students.items():
        if data.get("last_cookie"):
            cookie_logins[sid] = data
        else:
            username_logins[sid] = data

    updated = {}

    if cookie_logins:
        updated.update(await cookie_login(cookie_logins, bot))

    if username_logins:
        updated.update(await username_login(username_logins))

    return updated
