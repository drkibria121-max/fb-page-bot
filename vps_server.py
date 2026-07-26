import json
import os
import time
import threading
import logging
import traceback
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

def js_scroll_to(driver, element):
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
    time.sleep(0.5)

def js_click(driver, element):
    driver.execute_script("arguments[0].click();", element)

def js_set_value(driver, element, value):
    driver.execute_script("arguments[0].value=''; arguments[0].focus();", element)
    element.clear()
    time.sleep(0.3)
    for char in value:
        element.send_keys(char)
        time.sleep(0.02)

def dismiss_popups(driver, job_id):
    popup_texts = ["OK", "Not now", "Allow", "Accept", "Got it", "Close", "Dismiss",
                    "Turn On", "Skip", "Maybe Later", "Decline", "No Thanks", "Cancel"]
    for text in popup_texts:
        for xpath in [
            f"//span[text()='{text}']",
            f"//div[@role='button']//span[text()='{text}']",
            f"//button[contains(text(),'{text}')]",
            f"//div[@role='dialog']//span[text()='{text}']",
            f"//div[@role='button'][@aria-label='{text}']",
        ]:
            try:
                el = driver.find_element(By.XPATH, xpath)
                if el.is_displayed():
                    js_click(driver, el)
                    logger.info(f"[Job {job_id}] Dismissed popup: {text}")
                    time.sleep(1)
            except:
                pass
    try:
        overlay = driver.find_element(By.CSS_SELECTOR, "div[role='presentation']")
        if overlay.is_displayed():
            actions = __import__('selenium.webdriver.common.action_chains', fromlist=['ActionChains']).ActionChains(driver)
            actions.send_keys(Keys.ESCAPE).perform()
            time.sleep(0.5)
    except:
        pass

def find_and_interact(driver, selectors, job_id, field_name, value=None, click_only=False):
    for by, selector in selectors:
        try:
            el = WebDriverWait(driver, 8).until(
                EC.presence_of_element_located((by, selector))
            )
            if not el.is_displayed():
                driver.execute_script("arguments[0].style.display='block'; arguments[0].style.visibility='visible';", el)
                time.sleep(0.5)
            js_scroll_to(driver, el)
            time.sleep(0.5)
            js_click(driver, el)
            time.sleep(0.5)
            if not click_only and value:
                el.clear()
                time.sleep(0.3)
                js_set_value(driver, el, value)
                time.sleep(0.5)
            logger.info(f"[Job {job_id}] Found {field_name} with: {selector}")
            return el
        except Exception as e:
            continue
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
        options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-infobars")
        options.add_argument("--start-maximized")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        service = Service(chromedriver_path)
        driver = webdriver.Chrome(service=service, options=options)
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })
        wait = WebDriverWait(driver, 20)

        logger.info(f"[Job {job_id}] Browser started, navigating to Facebook login...")
        driver.get("https://www.facebook.com/login")
        time.sleep(5)
        dismiss_popups(driver, job_id)

        logger.info(f"[Job {job_id}] Filling login form...")
        email = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[name='email']")))
        js_scroll_to(driver, email)
        js_click(driver, email)
        time.sleep(0.3)
        email.send_keys(fb_number)
        time.sleep(0.5)
        pwd = driver.find_element(By.CSS_SELECTOR, "input[name='pass']")
        js_scroll_to(driver, pwd)
        js_click(driver, pwd)
        time.sleep(0.3)
        pwd.send_keys(fb_password)
        time.sleep(0.5)

        submit = driver.find_element(By.CSS_SELECTOR, "button[type='submit'], input[type='submit']")
        js_scroll_to(driver, submit)
        js_click(driver, submit)
        logger.info(f"[Job {job_id}] Login submitted, waiting...")
        time.sleep(12)
        dismiss_popups(driver, job_id)
        time.sleep(3)
        dismiss_popups(driver, job_id)

        current_url = driver.current_url
        logger.info(f"[Job {job_id}] Current URL after login: {current_url}")
        if "login" in current_url.lower() or "checkpoint" in current_url.lower():
            page_source_snippet = driver.page_source[:2000]
            RESULTS[job_id] = {"status": "error", "message": f"Login failed. Possible checkpoint or wrong credentials. URL: {current_url}"}
            driver.quit()
            return

        logger.info(f"[Job {job_id}] Navigating to page creation...")
        driver.get("https://www.facebook.com/pages/create")
        time.sleep(10)
        dismiss_popups(driver, job_id)
        time.sleep(2)

        logger.info(f"[Job {job_id}] Filling page name...")
        page_name_selectors = [
            (By.XPATH, "//input[@placeholder='Page name']"),
            (By.XPATH, "//input[contains(@aria-label,'Page name')]"),
            (By.XPATH, "//input[contains(@aria-label,'page name')]"),
            (By.XPATH, "//input[contains(@aria-label,'Page Name')]"),
            (By.XPATH, "//label[contains(text(),'Page name')]/following::input[1]"),
            (By.XPATH, "//label[contains(.,'Page name')]//input"),
            (By.XPATH, "//*[contains(text(),'Page name')]/ancestor::div[1]//input"),
            (By.XPATH, "//div[contains(@data-testid,'page_name')]//input"),
            (By.CSS_SELECTOR, "input[placeholder*='Page' i]"),
            (By.CSS_SELECTOR, "input[aria-label*='Page' i]"),
            (By.CSS_SELECTOR, "input[aria-label*='name' i]"),
            (By.XPATH, "//form//input[@type='text'][1]"),
            (By.XPATH, "//div[contains(@role,'main')]//input[@type='text']"),
        ]
        page_name_input = find_and_interact(driver, page_name_selectors, job_id, "Page Name", page_name)

        if not page_name_input:
            screenshot_path = f"/tmp/debug_{job_id}.png"
            try:
                driver.save_screenshot(screenshot_path)
            except:
                pass
            RESULTS[job_id] = {"status": "error", "message": "Could not find page name input. Facebook layout may have changed."}
            driver.quit()
            return

        logger.info(f"[Job {job_id}] Filling category...")
        category_selectors = [
            (By.CSS_SELECTOR, "input[aria-label='Category (required)']"),
            (By.CSS_SELECTOR, "input[aria-label*='Category']"),
            (By.CSS_SELECTOR, "input[aria-label*='category']"),
            (By.CSS_SELECTOR, "input[placeholder*='category' i]"),
            (By.CSS_SELECTOR, "input[placeholder*='Category' i]"),
            (By.XPATH, "//input[contains(@aria-label,'ategor')]"),
            (By.XPATH, "//label[contains(text(),'Category')]/following::input[1]"),
            (By.XPATH, "//label[contains(.,'Category')]//input"),
        ]
        category_input = find_and_interact(driver, category_selectors, job_id, "Category", "Travel")

        if not category_input:
            RESULTS[job_id] = {"status": "error", "message": "Could not find category input field."}
            driver.quit()
            return

        time.sleep(3)
        dismiss_popups(driver, job_id)

        logger.info(f"[Job {job_id}] Selecting Travel category suggestion...")
        try:
            suggestion = WebDriverWait(driver, 8).until(
                EC.element_to_be_clickable((By.XPATH,
                    "//li[contains(.,'Travel')] | "
                    "//div[@role='option'][contains(.,'Travel')] | "
                    "//span[contains(text(),'Travel')]/ancestor::li | "
                    "//span[contains(text(),'Travel')]/ancestor::div[@role='option']"))
            )
            js_scroll_to(driver, suggestion)
            js_click(driver, suggestion)
        except:
            try:
                options_list = driver.find_elements(By.XPATH,
                    "//ul[@role='listbox']//li | //div[@role='listbox']//div[@role='option'] | //div[@role='option'] | //div[@role='listbox']//div")
                for opt in options_list:
                    if "travel" in opt.text.lower():
                        js_scroll_to(driver, opt)
                        js_click(driver, opt)
                        break
                else:
                    category_input.send_keys(Keys.ARROW_DOWN)
                    time.sleep(0.5)
                    category_input.send_keys(Keys.ENTER)
            except:
                category_input.send_keys(Keys.ARROW_DOWN)
                time.sleep(0.5)
                category_input.send_keys(Keys.ENTER)
        time.sleep(3)

        logger.info(f"[Job {job_id}] Clicking Create Page button...")
        create_btn_selectors = [
            (By.XPATH, "//div[@role='button']//span[text()='Create Page']"),
            (By.XPATH, "//span[text()='Create Page']"),
            (By.XPATH, "//button[contains(.,'Create Page')]"),
            (By.XPATH, "//div[@role='button'][contains(.,'Create Page')]"),
            (By.XPATH, "//span[text()='Create']"),
            (By.XPATH, "//div[@role='button'][contains(.,'Create')]"),
            (By.XPATH, "//button[contains(.,'Create')]"),
        ]
        create_btn = None
        for by, selector in create_btn_selectors:
            try:
                create_btn = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((by, selector))
                )
                js_scroll_to(driver, create_btn)
                time.sleep(0.5)
                break
            except:
                continue

        if not create_btn:
            RESULTS[job_id] = {"status": "error", "message": "Could not find Create Page button."}
            driver.quit()
            return

        js_click(driver, create_btn)
        logger.info(f"[Job {job_id}] Create Page clicked, waiting...")
        time.sleep(10)
        dismiss_popups(driver, job_id)

        logger.info(f"[Job {job_id}] Skipping setup steps...")
        for step in range(15):
            time.sleep(2)
            dismiss_popups(driver, job_id)

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
        logger.error(f"[Job {job_id}] Error: {e}\n{traceback.format_exc()}")
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
