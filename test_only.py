import requests

url = "https://clicker-api.joincommunity.xyz/clicker/core/click"
headers = {
    "Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VySWQiOjE5Mzg2MTAyLCJleHBpcmUiOjE3Njk3MDE5NjA2MDksImlhdCI6MTc2MTkyNTk2MCwiZXhwIjoxNzY5NzAxOTYwfQ.epjBcxcyi8GVVHWDhGiJfNFEQUOhPb77kPMjqyFPH3E",
    "Content-Type": "application/json"
}
data = {
    "count": 7013813123
}

response = requests.post(url, headers=headers, json=data)

print("Status Code:", response.status_code)
print("Response:", response.text)
