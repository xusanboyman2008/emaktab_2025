import asyncio
import aiohttp
from captcha_code import get_captcha_code


async def login_by_user(username: str, password: str, captcha_id: str = None, use_captcha: bool = False, captcha_text: str = None):
    if not captcha_id:
        captcha_id = "f61a11f3-1cee-448c-ad2b-fd2eee8f9b2d"

    if use_captcha and not captcha_text:
        captcha_text = await asyncio.to_thread(get_captcha_code, captcha_id)
        print("✅ Captcha solved:", captcha_text)

    headers = {
        "Host": "login.emaktab.uz",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:144.0) Gecko/20100101 Firefox/144.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }

    payload = {
        "exceededAttempts": "False",
        "ReturnUrl": "",
        "FingerprintId": "",
        "login": username,
        "password": password,
        "Captcha.Id": captcha_id,
        "Captcha.Input": captcha_text or "",
    }

    jar = aiohttp.CookieJar(unsafe=True)
    timeout = aiohttp.ClientTimeout(total=20)

    try:
        async with aiohttp.ClientSession(cookie_jar=jar, headers=headers, timeout=timeout) as session:
            async with session.post("https://login.emaktab.uz/", data=payload, allow_redirects=False) as resp:
                cookies = {cookie.key: cookie.value for cookie in jar}

                # Parse Set-Cookie headers for any additional cookies
                for sc in resp.headers.getall("Set-Cookie", []):
                    part = sc.split(";")[0].strip()
                    if "=" in part:
                        k, v = part.split("=", 1)
                        cookies[k.strip()] = v.strip()

                defaults = {
                    "a_r_p_i": "13.2",
                    "dnevnik_rr": "False",
                    "t1": "",
                    "t2": "",
                }
                for k, v in defaults.items():
                    cookies.setdefault(k, v)

                cookie_string = "; ".join([f"{k}={v}" for k, v in cookies.items()])
                cookies_len = len([k for k in cookies if k not in defaults])
                return cookies_len, cookie_string
    except Exception as e:
        print(f"⚠️ Login error for {username}: {e}")
        return 0, ""


async def main():
    cookies_len, cookie_string = await login_by_user("xusanboyabdulxayev", "12345678x", use_captcha=False)
    if "UZDnevnikAuth_a" not in cookie_string:
        print("⚠️ Missing UZDnevnikAuth_a, retrying with captcha...")
        cookies_len, cookie_string = await login_by_user("xusanboyabdulxayev", "12345678x", use_captcha=True)

    print("✅ Ready to use cookie string:\n", cookie_string)
    return cookie_string


if __name__ == "__main__":
    asyncio.run(main())
