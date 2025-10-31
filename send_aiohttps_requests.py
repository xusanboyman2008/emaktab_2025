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
        "Cookie": student.get("last_cookie",''),
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Priority": "u=0, i"
    }


    async with sem:
        async with session.get(url, headers=headers, allow_redirects=False) as response:
            all_cookies = session.cookie_jar.filter_cookies(url)
            new_cookies = [f"{k}={v.value}" for k, v in all_cookies.items()]

            has_auth = any("UZDnevnikAuth_a" in kv for kv in new_cookies)
            success = True if has_auth else False

            return student_id, success, new_cookies


async def cookie_login(students_dict, bot=False):
    sem = asyncio.Semaphore(50)
    connector = aiohttp.TCPConnector(limit=100)
    timeout = aiohttp.ClientTimeout(total=30)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        tasks = [fetch(session, sid, s, sem) for sid, s in students_dict.items()]
        results = await asyncio.gather(*tasks)

        for sid, success, new_cookies in results:
            old_cookie = students_dict[sid].get("last_cookie", "")
            cookie = SimpleCookie()
            cookie.load(old_cookie)

            for kv in new_cookies:
                key, _, value = kv.partition("=")
                key = key.strip()
                if key:
                    cookie[key] = value

            merged_cookie = "; ".join([f"{k}={v.value}" for k, v in cookie.items()])
            students_dict[sid]["last_cookie"] = merged_cookie
            students_dict[sid]["last_login"] = success

            # ✅ If cookie expired, immediately relogin
            if not success:
                print(f"⚠️ [{sid}] Cookie expired. Retrying with username login...")
                username = students_dict[sid]["username"]
                password = students_dict[sid]["password"]
                captcha_id = await give_captcha_100(students_dict[sid].get('login_id'))

                login, new_cookie = await login_by_user(
                    username, password, use_captcha=True, captcha_id=captcha_id
                )

                if login >= 4 and "UZDnevnikAuth_a" in new_cookie:
                    print(f"✅ [{sid}] Auto-refreshed cookie successfully")
                    students_dict[sid]["last_login"] = True
                    students_dict[sid]["last_cookie"] = new_cookie
                    await update_logins(
                        login_id=students_dict[sid]["login_id"],
                        last_login=True,
                        last_cookie=new_cookie
                    )
                else:
                    print(f"❌ [{sid}] Failed to auto-refresh cookie.")

            else:
                await update_logins(
                    login_id=students_dict[sid]["login_id"],
                    last_login=True,
                    last_cookie=merged_cookie
                )

        if bot:
            await bot.send_message(text="Cookies updated ✅", chat_id=6588631008)

    return students_dict


async def username_login(students_dict):
    for sid, data in students_dict.items():
        username = data.get("username")
        password = data.get("password")
        tg_id = data.get("tg_id", 6588631008)

        print(f"[{sid}] Trying username login: {username}:{password}")

        # Retry up to 2 times if failed
        for attempt in range(2):
            captcha_id = await give_captcha_100(data.get('login_id'))
            login, cookie = await login_by_user(username, password,use_captcha=True,captcha_id=captcha_id)
            print(login)
            if login >=4 and cookie and "UZDnevnikAuth_a" in cookie:
                students_dict[sid]["last_login"] = True
                students_dict[sid]["last_cookie"] = cookie

                if data.get("login_id"):
                    await update_logins(
                        login_id=data["login_id"],
                        last_login=True,
                        last_cookie=cookie
                    )
                print(f"✅ [{sid}] Username login success on attempt {attempt+1}")
                break  # stop retry loop after success
            else:
                print(f"⚠️ [{sid}] Username login failed (attempt {attempt+1})")

                students_dict[sid]["last_login"] = False

                if attempt == 1:  # after 2 attempts
                    if data.get("login_id"):
                        await update_logins(
                            login_id=data["login_id"],
                            last_login=False,
                            last_cookie=data.get("last_cookie", "")
                        )

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

    # Step 2: For those whose cookie login failed, use username login
    failed_after_cookie = {
        sid: data for sid, data in updated.items() if not data.get("last_login")
    }
    if failed_after_cookie:
        print(f"🔁 Retrying {len(failed_after_cookie)} failed users with username login...")
        updated.update(await username_login(failed_after_cookie))

    # Step 3: Add users who had no cookies at all initially
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
        },
        "s2": {
            "username": "another",
            "password": "pass",
            "last_login": False,
            "last_cookie": ""
        },
    }

    asyncio.run(send_request_main(example_students))
