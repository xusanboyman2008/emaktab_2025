import requests

def send_stars(username: str, amount: int = 50000):
    token = "ee0ed770-fa59-4506-b0b3-ffa026475a1d"

    headers = {
        "accept": "*/*",
        "authorization": token,
        "content-type": "application/json"
    }

    try:
        # 1️⃣ Get recipient ID
        url_recipient = f"https://api.tgmrkt.io/api/v1/stars-orders/recipient?username={username}"
        r1 = requests.get(url_recipient, headers=headers)
        if r1.status_code == 400:
            return f"{username} topilmadi"
        recipient_data = r1.json()
        print("Recipient info:", recipient_data)

        recipient_id = recipient_data.get("recipient")
        if not recipient_id:
            print(f"❌ No recipient found for username: {username}")
            return

        # 2️⃣ Get displayed price
        url_price = f"https://api.tgmrkt.io/api/v1/stars-orders/price?amount={amount}"
        r2 = requests.get(url_price, headers=headers)
        price_data = r2.json()
        print("Price info:", price_data)

        displayed_price = price_data
        if not displayed_price:
            print("❌ Could not get displayedPrice.")
            return

        # 3️⃣ Create order
        payload = {
            "recipient": recipient_id,
            "amount": amount,
            "displayedPrice": displayed_price
        }

        print("\n📦 Sending payload:", payload)
        url_order = "https://api.tgmrkt.io/api/v1/stars-orders/create"
        r3 = requests.post(url_order, headers=headers, json=payload)
        print("\n🔁 Response status:", r3.status_code)
        print("Response text:", r3.text)

        r3.raise_for_status()
        print("\n✅ Order created successfully:", r3.json())

    except requests.RequestException as e:
        print("❌ Request failed:", e)


# 🧠 Example usage:
print(send_stars("xusanboyman200"))
