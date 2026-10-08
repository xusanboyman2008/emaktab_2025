import aiohttp
import asyncio
from http.cookies import SimpleCookie
from database import update_logins, give_captcha_100
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


async def handle_expired_cookie(sid, student_data):
    username = student_data.get("username")
    password = student_data.get("password")
    captcha_id = await give_captcha_100(student_data.get('login_id'))

    login_len, new_cookie = await login_by_user(
        username, password, use_captcha=True, captcha_id=captcha_id
    )

    if login_len >= 4 and new_cookie and "UZDnevnikAuth_a" in new_cookie:
        print(f"✅ [{sid}] Auto-refreshed cookie successfully")
        student_data["last_login"] = True
        student_data["last_cookie"] = new_cookie
        if student_data.get("login_id"):
            await update_logins(
                login_id=student_data["login_id"],
                last_login=True,
                last_cookie=new_cookie
            )
    else:
        print(f"❌ [{sid}] Failed to auto-refresh cookie.")
        student_data["last_login"] = False


async def cookie_login(students_dict, bot=None):
    sem = asyncio.Semaphore(50)
    connector = aiohttp.TCPConnector(limit=100)
    timeout = aiohttp.ClientTimeout(total=30)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = [fetch(session, sid, s, sem) for sid, s in students_dict.items()]
        results = await asyncio.gather(*tasks)

        expired_tasks = []

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

            merged_cookie = "; ".join([f"{k}={v.value}" for k, v in cookie.items()])
            students_dict[sid]["last_cookie"] = merged_cookie
            students_dict[sid]["last_login"] = success

            if not success:
                print(f"⚠️ [{sid}] Cookie expired. Retrying with username login...")
                expired_tasks.append(handle_expired_cookie(sid, students_dict[sid]))
            else:
                if students_dict[sid].get("login_id"):
                    await update_logins(
                        login_id=students_dict[sid]["login_id"],
                        last_login=True,
                        last_cookie=merged_cookie
                    )

        if expired_tasks:
            # Process up to 5 concurrent expired refreshes
            sem_relogin = asyncio.Semaphore(5)
            async def bounded_expired(task):
                async with sem_relogin:
                    return await task
            await asyncio.gather(*(bounded_expired(t) for t in expired_tasks))

    return students_dict


async def login_single_username(sid, data, sem):
    async with sem:
        username = data.get("username")
        password = data.get("password")
        print(f"[{sid}] Trying username login: {username}")

        for attempt in range(2):
            captcha_id = await give_captcha_100(data.get('login_id'))
            login_len, cookie = await login_by_user(
                username, password, use_captcha=True, captcha_id=captcha_id
            )
            if login_len >= 4 and cookie and "UZDnevnikAuth_a" in cookie:
                data["last_login"] = True
                data["last_cookie"] = cookie
                if data.get("login_id"):
                    await update_logins(
                        login_id=data["login_id"],
                        last_login=True,
                        last_cookie=cookie
                    )
                print(f"✅ [{sid}] Username login success on attempt {attempt+1}")
                return
            else:
                print(f"⚠️ [{sid}] Username login failed (attempt {attempt+1})")
                data["last_login"] = False
                if attempt == 1 and data.get("login_id"):
                    await update_logins(
                        login_id=data["login_id"],
                        last_login=False,
                        last_cookie=data.get("last_cookie", "")
                    )


async def username_login(students_dict):
    sem = asyncio.Semaphore(5)
    tasks = [login_single_username(sid, data, sem) for sid, data in students_dict.items()]
    await asyncio.gather(*tasks)
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

    # Step 1: Try cookie login
    if cookie_logins:
        updated.update(await cookie_login(cookie_logins, bot))
        print("✅ Cookie login attempt done.")

    # Step 2: For users who had no cookies initially
    if username_logins:
        print("➡️ Logging in users with no cookies at all...")
        updated.update(await username_login(username_logins))

    print("✅ Final results ready.")
    return updated


if __name__ == "__main__":
    example_students = {
        "s1": {
            "username": "xusanboyabdulxayev",
            "password": "12345678x",
            "last_login": True,
            "last_cookie": "UZDnevnikAuth_a=abc; a_r_p_i=13.2;"
        }
    }
    asyncio.run(send_request_main(example_students))
