from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
import requests
import os
import time
from datetime import datetime, timedelta

# ▼対象日を数字で選択
print("📅 ダウンロード対象日を選んでください:")
print("1: 今日")
print("2: 明日")
choice = input("▶ 数字で入力（1 または 2）: ").strip()

if choice == "2":
    target_date_obj = datetime.now() + timedelta(days=1)
else:
    target_date_obj = datetime.now()

TARGET_DATE = target_date_obj.strftime("%Y-%m-%d")

# ▼設定
CHROMEDRIVER_PATH = "C:/chromedriver/chromedriver.exe"
DOWNLOAD_DIR = "C:/data"
LOGIN_ID = "nakacyo"
PASSWORD = "toshikazuh822"
CSV_FILENAME = f"orders_{TARGET_DATE}.csv"
CSV_URL = f"https://partner.gluseller.com/analysis/order/flat/2/{TARGET_DATE}/download"
REFERER_URL = f"https://partner.gluseller.com/analysis/order/flat/2/{TARGET_DATE}"

# ▼最初に既存の orders_*.csv を削除
for f in os.listdir(DOWNLOAD_DIR):
    if f.startswith("orders_") and f.endswith(".csv"):
        os.remove(os.path.join(DOWNLOAD_DIR, f))
        print(f"🧹 削除: {f}")

# ▼Chromeオプション
options = webdriver.ChromeOptions()
prefs = {
    "download.default_directory": DOWNLOAD_DIR,
    "download.prompt_for_download": False,
    "directory_upgrade": True,
    "safebrowsing.enabled": True
}
options.add_experimental_option("prefs", prefs)

driver = webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=options)

try:
    # ▼ログイン処理
    driver.get("https://partner.gluseller.com/login")
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "login_id"))).send_keys(LOGIN_ID)
    driver.find_element(By.NAME, "password").send_keys(PASSWORD)
    driver.find_element(By.XPATH, '//button[text()="ログイン"]').click()

    # ▼ナビゲーション
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.LINK_TEXT, "現在の受注状況"))).click()
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, '//a[.//p[text()="受注データダウンロード"]]'))).click()
    WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, "バージョン2"))).click()

    # ▼Cookie を使って CSV を requests でダウンロード
    selenium_cookies = driver.get_cookies()
    session = requests.Session()
    for cookie in selenium_cookies:
        session.cookies.set(cookie['name'], cookie['value'])

    headers = {"Referer": REFERER_URL}
    response = session.get(CSV_URL, headers=headers)

    if response.status_code == 200:
        file_path = os.path.join(DOWNLOAD_DIR, CSV_FILENAME)
        with open(file_path, "wb") as f:
            f.write(response.content)
        print(f"✅ CSVダウンロード成功: {file_path}（{os.path.getsize(file_path)} bytes）")
    else:
        print(f"❌ ダウンロード失敗（HTTP {response.status_code}）")

except Exception as e:
    print("❌ 処理中にエラー:", e)

finally:
    driver.quit()
