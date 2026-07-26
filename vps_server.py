import json
import os
import time
import threading
import logging
from datetime import datetime
from flask import Flask, request, jsonify

IS_TERMUX = os.path.exists("/data/data/com.termux")

app = Flask(__name__)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

RESULTS = {}

def find_chrome_binary():
    if IS_TERMUX:
        for p in ["/data/data/com.termux/files/usr/bin/chromium-browser",
                   "/data/data/com.termux/files/usr/bin/chromium"]:
            if os.path.exists(p):
                return p
    candidates = [
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/local/bin/chromium-browser",
        "/usr/local/bin/chromium",
        "/snap/bin/chromium",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None

def find_chromedriver():
    if IS_TERMUX:
        for p in ["/data/data/com.termux/files/usr/bin/chromedriver",
                   "/data/data/com.termux/files/usr/bin/chromedriver-149"]:
            if os.path.exists(p):
                return p
    candidates = [
        "/usr/bin/chromedriver",
        "/usr/local/bin/chromedriver",
        "/usr/lib/chromium/chromedriver",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    try:
        import chromedriver_autoinstaller
        path = chromedriver_autoinstaller.install()
        if path:
            return path
    except:
        pass
    return None

def run_page_creation_task(job_id, user_id, username, fb_number, fb_password, page_name):
    logger.info(f"[Job {job_id}] Starting page creation for user {user_id}: {page_name}")
    RESULTS[job_id] = {"status": "processing", "started_at": datetime.now().isoformat()}

    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.common.keys import Keys
    except ImportError:
        RESULTS[job_id] = {"status": "error", "message": "Selenium not installed!"}
        return

    chrome_binary = find_chrome_binary()
    chromedriver_path = find_chromedriver()

    if not chrome_binary:
        RESULTS[job_id] = {"status": "error", "message": "Chrome/Chromium not found!"}
        return
    if not chromedriver_path:
        RESULTS[job_id] = {"status": "error", "message": "Chromedriver not found!"}
        return

    logger.info(f"[Job {job_id}] Chrome: {chrome_binary}, Driver: {chromedriver_path}")

    driver = None
    try:
        options = Options()
        options.binary_location = chrome_binary
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])

        service = Service(chromedriver_path)
        driver = webdriver.Chrome(service=service, options=options)
        wait = WebDriverWait(driver, 15)

        logger.info(f"[Job {job_id}] Browser started, navigating to Facebook login...")
        driver.get("https://www.facebook.com/login")
        time.sleep(3)

        email = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='email']")))
        email.send_keys(fb_number)
        pwd = driver.find_element(By.CSS_SELECTOR, "input[name='pass']")
        pwd.send_keys(fb_password)

        driver.execute_script("arguments[0].click();", driver.find_element(By.CSS_SELECTOR, "input[type='submit']"))
        time.sleep(10)

        logger.info(f"[Job {job_id}] Login submitted, checking for popups...")
        try:
            driver.execute_script("arguments[0].click();", driver.find_element(By.XPATH, "//span[text()='OK']"))
            time.sleep(2)
        except:
            pass
        try:
            driver.execute_script("arguments[0].click();", driver.find_element(By.XPATH, "//span[text()='Not now']"))
            time.sleep(2)
        except:
            pass

        logger.info(f"[Job {job_id}] Navigating to page creation...")
        driver.get("https://www.facebook.com/pages/create")
        time.sleep(8)

        try:
            driver.execute_script("arguments[0].click();", driver.find_element(By.XPATH, "//button[contains(text(),'Allow')]"))
            time.sleep(2)
        except:
            pass

        logger.info(f"[Job {job_id}] Filling page name and category...")
        page_name_selectors = [
            (By.XPATH, "//label[contains(text(),'Page name')]/input"),
            (By.XPATH, "//label[contains(.,'Page name')]//input[@type='text']"),
            (By.XPATH, "//input[@placeholder='Page name']"),
            (By.XPATH, "//input[contains(@aria-label,'Page name')]"),
            (By.XPATH, "//input[contains(@aria-label,'page name')]"),
            (By.XPATH, "//*[contains(text(),'Page name')]/ancestor::div[1]//input"),
            (By.XPATH, "//div[contains(@data-testid,'page_name')]//input"),
            (By.CSS_SELECTOR, "input[placeholder*='page' i]"),
            (By.CSS_SELECTOR, "input[aria-label*='page' i]"),
        ]

        page_name_input = None
        for by, selector in page_name_selectors:
            try:
                page_name_input = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((by, selector))
                )
                break
            except:
                continue

        if not page_name_input:
            RESULTS[job_id] = {"status": "error", "message": "Could not find page name input field."}
            driver.quit()
            return

        page_name_input.clear()
        page_name_input.send_keys(page_name)
        time.sleep(1)

        category_selectors = [
            (By.CSS_SELECTOR, "input[aria-label='Category (required)']"),
            (By.CSS_SELECTOR, "input[aria-label*='Category']"),
            (By.CSS_SELECTOR, "input[aria-label*='category']"),
            (By.CSS_SELECTOR, "input[placeholder*='category' i]"),
            (By.XPATH, "//input[contains(@aria-label,'ategor')]"),
        ]

        category_input = None
        for by, selector in category_selectors:
            try:
                category_input = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((by, selector))
                )
                break
            except:
                continue

        if not category_input:
            RESULTS[job_id] = {"status": "error", "message": "Could not find category input field."}
            driver.quit()
            return

        category_input.clear()
        category_input.send_keys("Travel")
        time.sleep(3)

        try:
            suggestion = wait.until(
                EC.element_to_be_clickable((By.XPATH,
                    "//span[contains(text(),'Travel')]//ancestor::li | "
                    "//div[@role='option']//span[contains(text(),'Travel')] | "
                    "//li[contains(.,'Travel')]"))
            )
            suggestion.click()
        except:
            try:
                options_list = driver.find_elements(By.XPATH,
                    "//ul[@role='listbox']//li | //div[@role='listbox']//div[@role='option'] | //div[@role='option']")
                for opt in options_list:
                    if "travel" in opt.text.lower():
                        driver.execute_script("arguments[0].click();", opt)
                        break
            except:
                category_input.send_keys(Keys.ARROW_DOWN)
                category_input.send_keys(Keys.ENTER)
        time.sleep(2)

        logger.info(f"[Job {job_id}] Clicking Create Page button...")
        create_btn_selectors = [
            (By.XPATH, "//span[text()='Create Page']"),
            (By.XPATH, "//div[@role='button']//span[text()='Create Page']"),
            (By.XPATH, "//button[contains(.,'Create Page')]"),
            (By.XPATH, "//div[@role='button'][contains(.,'Create')]"),
            (By.XPATH, "//span[text()='Create']"),
        ]

        create_btn = None
        for by, selector in create_btn_selectors:
            try:
                create_btn = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((by, selector))
                )
                break
            except:
                continue

        if not create_btn:
            RESULTS[job_id] = {"status": "error", "message": "Could not find Create Page button."}
            driver.quit()
            return

        driver.execute_script("arguments[0].click();", create_btn)
        time.sleep(8)

        logger.info(f"[Job {job_id}] Skipping setup steps...")
        for step in range(10):
            time.sleep(3)
            try:
                skip_selectors = [
                    "//span[text()='Skip']",
                    "//span[text()='Next']",
                    "//span[text()='Not now']",
                    "//span[text()='Done']",
                    "//span[text()='Leave']",
                    "//span[text()='Finish']",
                    "//div[@role='button']//span[text()='Skip']",
                    "//div[@role='button']//span[text()='Next']",
                    "//div[@role='button']//span[text()='Done']",
                ]
                for sel in skip_selectors:
                    try:
                        skip_btn = driver.find_element(By.XPATH, sel)
                        driver.execute_script("arguments[0].click();", skip_btn)
                        break
                    except:
                        continue
            except:
                continue

        time.sleep(3)

        cookies = driver.get_cookies()
        cookie_str = '; '.join([c['name'] + '=' + c['value'] for c in cookies])

        logger.info(f"[Job {job_id}] Page created successfully: {page_name}")
        RESULTS[job_id] = {
            "status": "success",
            "page_name": page_name,
            "fb_number": fb_number,
            "cookies": cookie_str,
            "completed_at": datetime.now().isoformat()
        }

        driver.quit()
        logger.info(f"[Job {job_id}] Done!")

    except Exception as e:
        logger.error(f"[Job {job_id}] Error: {e}")
        RESULTS[job_id] = {"status": "error", "message": str(e)}
        if driver:
            try:
                driver.quit()
            except:
                pass

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})

@app.route('/create_page', methods=['POST'])
def create_page():
    data = request.json
    if not data:
        return jsonify({"error": "No data provided"}), 400

    required = ["user_id", "username", "fb_number", "fb_password", "page_name"]
    for field in required:
        if field not in data:
            return jsonify({"error": f"Missing field: {field}"}), 400

    job_id = f"{data['user_id']}_{int(time.time())}"

    thread = threading.Thread(
        target=run_page_creation_task,
        args=(job_id, data['user_id'], data['username'], data['fb_number'], data['fb_password'], data['page_name']),
        daemon=True
    )
    thread.start()

    return jsonify({"status": "queued", "job_id": job_id})

@app.route('/job_status/<job_id>', methods=['GET'])
def job_status(job_id):
    if job_id in RESULTS:
        return jsonify(RESULTS[job_id])
    return jsonify({"status": "not_found"}), 404

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"VPS Server starting on port {port}")
    app.run(host='0.0.0.0', port=port)
