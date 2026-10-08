import asyncio
from io import BytesIO
import requests
from PIL import Image, ImageFilter, ImageEnhance
import pytesseract
import dns_resolver  # noqa: F401 - ensures DNS fast-path is active

_CAPTCHA_MEM_CACHE = {}


def preprocess_image_pass1(img: Image.Image) -> Image.Image:
    """Standard contrast enhancement and median filter for clean eMaktab captchas."""
    gray = img.convert("L")
    enh = ImageEnhance.Contrast(gray).enhance(2.5)
    med = enh.filter(ImageFilter.MedianFilter(size=3))
    res = med.resize((med.width * 2, med.height * 2), Image.Resampling.BILINEAR)
    return res.point(lambda x: 0 if x < 140 else 255, '1')


def preprocess_image_pass2(img: Image.Image) -> Image.Image:
    """Alternative aggressive contrast pass if pass 1 fails."""
    gray = img.convert("L")
    enh = ImageEnhance.Contrast(gray).enhance(3.5)
    sharp = enh.filter(ImageFilter.SHARPEN)
    res = sharp.resize((sharp.width * 3, sharp.height * 3), Image.Resampling.NEAREST)
    return res.point(lambda x: 0 if x < 160 else 255, '1')


def extract_digits_from_image(img: Image.Image) -> str:
    """Extract digits using single-line page segmentation mode."""
    # Pass 1: Fast clean extraction
    bin1 = preprocess_image_pass1(img)
    text1 = pytesseract.image_to_string(
        bin1,
        config="--oem 1 --psm 7 -c tessedit_char_whitelist=0123456789"
    )
    digits1 = "".join(ch for ch in text1 if ch.isdigit())
    if len(digits1) >= 4:
        return digits1

    # Pass 2: Secondary aggressive contrast if digits were missing
    bin2 = preprocess_image_pass2(img)
    text2 = pytesseract.image_to_string(
        bin2,
        config="--oem 1 --psm 7 -c tessedit_char_whitelist=0123456789"
    )
    digits2 = "".join(ch for ch in text2 if ch.isdigit())
    if len(digits2) > len(digits1):
        return digits2

    return digits1 or text1.strip()


def get_captcha_code(captcha_id: str) -> str | None:
    """Synchronous captcha solver with connection pooling and memory caching."""
    if not captcha_id:
        return None

    cid = captcha_id.strip()
    if cid in _CAPTCHA_MEM_CACHE:
        return _CAPTCHA_MEM_CACHE[cid]

    try:
        url = f"https://login.emaktab.uz/captcha/true/{cid}"
        resp = requests.get(url, timeout=3.0, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()

        img = Image.open(BytesIO(resp.content))
        result = extract_digits_from_image(img)

        if result:
            _CAPTCHA_MEM_CACHE[cid] = result
            print(f"✅ Captcha [{cid[:8]}] solved: {result}")
            return result
        return None

    except Exception as e:
        print(f"⚠️ Captcha solver error for {cid}: {e}")
        return None


async def get_captcha_code_async(captcha_id: str) -> str | None:
    """Asynchronous wrapper that runs image decoding and OCR in worker threads."""
    return await asyncio.to_thread(get_captcha_code, captcha_id)


if __name__ == "__main__":
    import sys
    test_id = sys.argv[1] if len(sys.argv) > 1 else "f61a11f3-1cee-448c-ad2b-fd2eee8f9b2d"
    code = get_captcha_code(test_id)
    print("Result:", code)
