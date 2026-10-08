import asyncio
import aiohttp
from captcha_code import get_captcha_code

_GLOBAL_SESSION = None


def get_shared_session():
    global _GLOBAL_SESSION
    if _GLOBAL_SESSION is None or _GLOBAL_SESSION.closed:
        connector = aiohttp.TCPConnector(limit=50, ttl_dns_cache=300, keepalive_timeout=60)
        jar = aiohttp.CookieJar(unsafe=True)
        timeout = aiohttp.ClientTimeout(total=15, connect=5)
        _GLOBAL_SESSION = aiohttp.ClientSession(connector=connector, cookie_jar=jar, timeout=timeout)
    return _GLOBAL_SESSION


async def login_by_user(
    username: str,
    password: str,
    captcha_id: str = None,
    use_captcha: bool = False,
    captcha_text: str = None,
    session: aiohttp.ClientSession = None
):
    if not captcha_id:
        captcha_id = "f61a11f3-1cee-448c-ad2b-fd2eee8f9b2d"

    if use_captcha and not captcha_text:
        captcha_text = await asyncio.to_thread(get_captcha_code, captcha_id)

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
    own_session = False
    if session is None:
        connector = aiohttp.TCPConnector(limit=10, ttl_dns_cache=300, keepalive_timeout=30)
        timeout = aiohttp.ClientTimeout(total=15, connect=5)
        session = aiohttp.ClientSession(connector=connector, cookie_jar=jar, timeout=timeout)
        own_session = True

    try:
        async with session.post("https://login.emaktab.uz/", data=payload, headers=headers, allow_redirects=False) as resp:
            # Extract cookies from response headers and jar
            cookies = {}
            for cookie in session.cookie_jar:
                cookies[cookie.key] = cookie.value

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

    finally:
        if own_session and not session.closed:
            await session.close()


async def main():
    cookies_len, cookie_string = await login_by_user("xusanboyabdulxayev", "12345678x", use_captcha=False)
    if "UZDnevnikAuth_a" not in cookie_string:
        print("⚠️ Missing auth cookie, retrying with fast captcha...")
        cookies_len, cookie_string = await login_by_user("xusanboyabdulxayev", "12345678x", use_captcha=True)

    print("✅ Cookie string:\n", cookie_string)
    return cookie_string


if __name__ == "__main__":
    asyncio.run(main())
