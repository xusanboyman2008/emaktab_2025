import pytesseract
from PIL import Image, ImageFilter, ImageEnhance
import requests
from io import BytesIO

def get_captcha_code(captcha_id: str):
    try:
        url = f"https://login.emaktab.uz/captcha/true/{captcha_id}"
        response = requests.get(url, timeout=3)
        response.raise_for_status()

        img = Image.open(BytesIO(response.content))
        img = img.convert("L")
        img = ImageEnhance.Contrast(img).enhance(2.5)
        img = img.filter(ImageFilter.MedianFilter(size=3))
        img = img.resize((img.width * 3, img.height * 3))
        img = img.point(lambda x: 0 if x < 140 else 255, '1')

        raw_text = pytesseract.image_to_string(img, config="--psm 8 -c tessedit_char_whitelist=0123456789")
        digits = "".join(ch for ch in raw_text if ch.isdigit())

        print(f"✅ Captcha text: {raw_text.strip()} => {digits}")
        return digits or raw_text.strip()

    except Exception as e:
        print(f"⚠️ OCR Error: {e}")
        return None

if __name__ == "__main__":
    get_captcha_code("f61a11f3-1cee-448c-ad2b-fd2eee8f9b2d")
