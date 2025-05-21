# test_api.py
import os, requests
from dotenv import load_dotenv

# .env から BRAWL_API_TOKEN を読み込む
load_dotenv()
token = os.getenv("BRAWL_API_TOKEN")
print("DEBUG: token=", token)

headers = {"Authorization": f"Bearer {token}"}
tag = "22PORPR98"   # ここは実際のタグ（# を除いた文字列）を入れてください
url = f"https://api.brawlstars.com/v1/players/%23{tag}"

resp = requests.get(url, headers=headers)
print("DEBUG: status=", resp.status_code)
print("DEBUG: body  =", resp.text)
