import asyncio
from http.cookies import SimpleCookie

import aiohttp

from login_by_username import login_by_user
from database import add_captcha_id, get_free_captcha, create_user
from database import update_logins
from database import create_login

url = "https://emaktab.uz/userfeed/"


async def fetch(session, student_id, student, sem):
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Cookie": student["last_cookie"],
    }

    async with sem:  # limit concurrency to 50
        async with session.get(url, headers=headers) as response:
            all_cookies = session.cookie_jar.filter_cookies(url)
            new_cookies = [f"{k}={v.value}" for k, v in all_cookies.items()]

            print(len(new_cookies), student_id)
            success = True if len(new_cookies) > 3 else False
            return student_id, success, new_cookies


async def cookie_login(students_dict):
    sem = asyncio.Semaphore(50)  # 👈 limit to 50 concurrent fetches
    connector = aiohttp.TCPConnector(limit=70)  # also limit open TCP connections

    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [
            fetch(session, sid, s, sem)
            for sid, s in students_dict.items()
        ]

        results = await asyncio.gather(*tasks)

        for sid, success, new_cookies in results:
            if not new_cookies:
                students_dict[sid]["last_login"] = success
                continue

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

            await update_logins(
                login_id=students_dict[sid]["login_id"],
                last_login=success,
                last_cookie=merged_cookie
            )

        return students_dict


async def username_login(students_dict):
    for sid, data in students_dict.items():
        print(f"[{sid}] Logging in {data.get('username')}:{data.get('password')}")

        username = data.get("username")
        password = data.get("password")
        tg_id = data.get("tg_id")
        login, cookie = await login_by_user(username, password)

        # Retry once if login fails
        if login != 4:
            user = await create_user(tg_id if tg_id else 6588631008)
            captcha = user.captcha_for_web
            if not user.captcha_for_web:
                captcha=await add_captcha_id(await get_free_captcha(),tg_id=tg_id,is_bot=False)
            login, cookie = await login_by_user(username, password,use_captcha=captcha)

        last_login = (login == 4)
        new_cookie = cookie if last_login else data.get("last_cookie")
        students_dict[sid]["last_login"] = last_login
        students_dict[sid]["last_cookie"] = new_cookie
        if login >=4:
            if students_dict[sid]['login_id']:
                await update_logins(login_id=students_dict[sid]["login_id",''],last_login=students_dict[sid]['last_login'],last_cookie=students_dict[sid]["last_cookie"])
                return students_dict
            school_number = await create_user(tg_id=tg_id)
            # await create_login(password=students_dict[sid]['password'],last_login=students_dict[sid]['last_login'],cookie=students_dict[sid]["last_cookie"],username=students_dict[sid]['username'],school_number_id=school_number.school_id,grade=students_dict[sid]['grade'])
        return students_dict

# Example students
student = {
    's1': {
        "username": "xusanboyabdulxayev",
        "password": "12345678x",
        "last_login": True,
        "last_cookie": 'UZDnevnikAuth_a=0GJ4M2iLIT4Ns6kItRPYSESWOBJr0UywOF5ujFeca4iiWp4onaC27CC9i03FL8%2F7YQXJW4%2FjSUGWR6Z0UlY0HCbFoueZ2zzkOqISmfsnsk8IcLE478bHc5Y9SK9TccUnA6lBEQ%3D%3D; a_r_p_i=13.2; dnevnik_rr=False; sst=93bbdacb-2366-41d0-b8c5-92e56cac11f2%7C13%2F09%2F2025%2016%3A21%3A45; t0=1000006479820; t1=; t2=; UZDnevnikAuth_l=aRr37m5bT8jHhzgrIXS47u5XuWLQTmBZC%2BdxWX29OXDY2iXmPGt05tqU2x2lGxZxFGj%2Byn98EvLMv6uYg7eT%2FQ641gr3AEBzMYcaEkAwWyCoy4tJdxSvA9V11Zp24Cu3z%2FDuR7KtjLac7nzkJm0%2FvUAefiP%2BRZlZgjg5YYNb0K%2BfkEOG7ntn9RsK%2FDQpywmepNujwTaaOa5rc%2Fd79QRF6B9Kdy8TMcAD4NyGRlldHgAMCVCzOe8Shn8UOUUSHUSvBJtbV8iHhYBJK%2BbRjEwiDt1dbPIODDWhFuwKvivcZu86IZguUBTKdNx6WPH0L4F5V78xSg%3D%3D'
    },
    's2': {
        "username": "xusanboyabdulxayev",
        "password": "12345678x",
        'last_login': True,
        'last_cookie': 'UZDnevnikAuth_a=0GJ4M2iLIT4Ns6kItRPYSESWOBJr0UywOF5ujFeca4iiWp4onaC27CC9i03FL8%2F7YQXJW4%2FjSUGWR6Z0UlY0HCbFoueZ2zzkOqISmfsnsk8IcLE478bHc5Y9SK9TccUnA6lBEQ%3D%3D; a_r_p_i=13.2; dnevnik_rr=False; sst=93bbdacb-2366-41d0-b8c5-92e56cac11f2%7C13%2F09%2F2025%2016%3A25%3A13; t0=1000006479820; t1=; t2=; UZDnevnikAuth_l=aRr37m5bT8jHhzgrIXS47u5XuWLQTmBZC%2BdxWX29OXDY2iXmPGt05tqU2x2lGxZxFGj%2Byn98EvLMv6uYg7eT%2FQ641gr3AEBzMYcaEkAwWyCoy4tJdxSvA9V11Zp24Cu3z%2FDuR7KtjLac7nzkJm0%2FvUAefiP%2BRZlZgjg5YYNb0K%2BfkEOG7ntn9RsK%2FDQpywmepNujwTaaOa5rc%2Fd79QRF6B9Kdy8TMcAD4NyGRlldHgAMCVCzOe8Shn8UOUUSHUSvBJtbV8iHhYBJK%2BbRjEwiDt1dbPIODDWhFuwKvivcZu86IZguUBTKdNx6WPH0L4F5V78xSg%3D%3D'
    }
}


async def send_request_main(students):
    cookie_logins = {}
    username_logins = {}
    for sid, data in students.items():
        if data['last_cookie']:
            cookie_logins[sid] = data
        else:
            username_logins[sid] = data

    updated = {}
    if cookie_logins:
        updated.update(await cookie_login(cookie_logins))
        print('a')
    if username_logins:
        print('b')
        updated.update(await username_login(username_logins))

    print("✅ Final result:", updated)
    return updated


if __name__ == "__main__":
    asyncio.run(send_request_main())
