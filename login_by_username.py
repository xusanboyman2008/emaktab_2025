import asyncio
import requests
from captcha_code import get_captcha_code  # OCR solver


async def login_by_user(username, password, captcha_id=None, use_captcha=False,captcha_text=None):
    session = requests.Session()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    if not captcha_id:
        captcha_id = "f61a11f3-1cee-448c-ad2b-fd2eee8f9b2d"

    # Solve captcha if required
    if not captcha_text:
        captcha_text = ""
    if use_captcha:
        captcha_text = get_captcha_code(captcha_id)
        print("✅ Captcha solved:", captcha_text)
    payload = {
        "exceededAttempts": "False",
        "ReturnUrl": "",
        "FingerprintId": "",
        "login": username,
        "password": password,
        "Captcha.Id": captcha_id,
        "Captcha.Input": captcha_text,
    }
    print(payload)
    # Send login request
    r = session.post("https://login.emaktab.uz/login/", headers=headers, data=payload)

    # Collect cookies from cookie jar
    cookies = {c.name: c.value for c in session.cookies}

    # Also parse Set-Cookie header to catch missing ones
    set_cookie_header = r.headers.get("Set-Cookie", "")
    if set_cookie_header:
        for part in set_cookie_header.split(","):
            items = part.split(";")[0].strip().split("=")
            if len(items) == 2:
                k, v = items
                cookies[k] = v

    # Manually ensure important defaults exist
    defaults = {
        "a_r_p_i": "13.2",
        "dnevnik_rr": "False",
        "t1": "",
        "t2": "",
    }
    for k, v in defaults.items():
        cookies.setdefault(k, v)

    # Build cookie string in correct format
    cookies_len = len(r.cookies)
    print(r.cookies)
    cookie_string = "; ".join([f"{k}={v}" for k, v in cookies.items()])
    print(cookie_string)
    return cookies_len,cookie_string


async def main():
    cookie_string = await login_by_user("xusanboyabdulxayev", "12345678x", use_captcha=False)

    # Retry with captcha if key auth cookie is missing
    if "UZDnevnikAuth_a" not in cookie_string:
        print("⚠️ Missing UZDnevnikAuth_a, retrying with captcha...")
        cookie_string = await login_by_user("xusanboyabdulxayev", "12345678x", use_captcha=True)

    print("✅ Ready to use cookie string:\n", cookie_string)
    return cookie_string


if __name__ == "__main__":
    asyncio.run(main())
