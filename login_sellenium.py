from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time

# Create driver
options = webdriver.ChromeOptions()
options.add_argument("--start-maximized")
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

try:
    # 1. Open page
    driver.get("https://login.emaktab.uz/")   # <- change this to your URL

    # 2. Find input elements and send data
    username = driver.find_element(By.NAME, "login")  # or By.CLASS_NAME / By.CSS_SELECTOR
    password = driver.find_element(By.NAME, "password")

    username.send_keys("my_username")
    password.send_keys("my_password")
    password.send_keys(Keys.RETURN)  # submit by pressing Enter

    time.sleep(3)  # wait for page to process
    a = []
    for _ in range(2000):
        # 3. Refresh page
        driver.refresh()
        time.sleep(0.1)
        # 4. Collect all image src attributes
        images = driver.find_elements(By.TAG_NAME, "img")
        for i, img in enumerate(images, start=1):
            print(f"{i}. {img.get_attribute('src')}")
            if img.get_attribute('src').strip()[-3:]!="png":
                a.append(img.get_attribute('src'))
    with open("output.txt", "a", encoding="utf-8") as f:
            for line in a:
                f.write(line.split('/')[-1] + "\n")
    print(a)

finally:
    driver.quit()
