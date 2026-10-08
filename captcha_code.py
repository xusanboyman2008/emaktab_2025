import requests
from io import BytesIO
from PIL import Image, ImageFilter, ImageEnhance
import pytesseract

_CAPTCHA_MEM_CACHE = {}


def get_captcha_code(captcha_id: str) -> str | None:
    if not captcha_id:
        return None

    if captcha_id in _CAPTCHA_MEM_CACHE:
        return _CAPTCHA_MEM_CACHE[captcha_id]

    try:
        url = f"https://login.emaktab.uz/captcha/true/{captcha_id}"
        response = requests.get(url, timeout=2.5)
        response.raise_for_status()

        img = Image.open(BytesIO(response.content))
        img = img.convert("L")
        img = ImageEnhance.Contrast(img).enhance(2.5)
        img = img.filter(ImageFilter.MedianFilter(size=3))
        img = img.resize((img.width * 2, img.height * 2), Image.Resampling.BILINEAR)
        img = img.point(lambda x: 0 if x < 140 else 255, '1')

        # Fast OCR with whitelist
        raw_text = pytesseract.image_to_string(
            img,
            config="--oem 1 --psm 8 -c tessedit_char_whitelist=0123456789"
        )
        digits = "".join(ch for ch in raw_text if ch.isdigit())
        result = digits or raw_text.strip()

        if result:
            _CAPTCHA_MEM_CACHE[captcha_id] = result
        return result

    except Exception as e:
        print(f"⚠️ Fast OCR error for {captcha_id}: {e}")
        return None


if __name__ == "__main__":
    print(get_captcha_code("f61a11f3-1cee-448c-ad2b-fd2eee8f9b2d"))
