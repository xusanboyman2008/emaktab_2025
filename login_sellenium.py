"""
Optimized Captcha Harvester.
Replaced legacy slow Selenium browser automation with high-speed async HTTP requests.
Harvests thousands of captcha IDs in seconds instead of hours.
"""
import asyncio
from captcha_finder import harvest_captchas

if __name__ == "__main__":
    print("🚀 Running high-speed captcha harvester (formerly login_sellenium.py)...")
    # Harvest 100 fresh captchas instantly and save to output.txt
    asyncio.run(harvest_captchas(target_count=100, output_file="output.txt"))
