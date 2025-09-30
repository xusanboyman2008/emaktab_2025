import requests


def get_captcha_code(captcha_id="f61a11f3-1cee-448c-ad2b-fd2eee8f9b2d"):
    api_url = "https://api.ocr.space/parse/imageurl"
    payload = {
        'apikey': 'K84441460188957',   # replace with your real API key
        'url': f"https://login.emaktab.uz/captcha/true/{captcha_id}",
        'language': 'eng'
    }

    # OCR.Space expects POST with form data, not GET
    r = requests.get(api_url, data=payload)
    result = r.json()

    if result.get("IsErroredOnProcessing"):
        print("❌ Error:", result.get("ErrorMessage"))
        return "0000"
    parsed_text = result["ParsedResults"][0]["ParsedText"].strip()
    # Extract only digits from captcha
    digits = "".join([ch for ch in parsed_text if ch.isdigit()])

    print("✅ Captcha text:", parsed_text, "=>", digits)
    return digits


get_captcha_code()