import json
import os
import sys
import time
import signal
import threading
import logging
import traceback
import shutil
import requests
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)
from telegram.error import NetworkError, TimedOut, Forbidden, BadRequest

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("fb_bot.log", mode='a', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.ERROR)
logging.getLogger("httpcore").setLevel(logging.ERROR)
logging.getLogger("telegram").setLevel(logging.WARNING)

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_config.json")
USER_DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "user_data.json")
PAGE_LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "page_log.json")

FB_NUMBER, FB_PASSWORD, PAGE_NAME, BROADCAST_MSG, CHANGE_FIELD = range(5)
DATA_EXPIRY_HOURS = 24

BOT_TOKEN_GLOBAL = None
BOT_INSTANCE = None

def get_bot():
    global BOT_INSTANCE, BOT_TOKEN_GLOBAL
    config = load_config()
    token = config.get("bot_token")
    if BOT_INSTANCE is None or token != BOT_TOKEN_GLOBAL:
        BOT_TOKEN_GLOBAL = token
        BOT_INSTANCE = Bot(token=token)
    return BOT_INSTANCE

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            config = json.load(f)
    else:
        config = {}

    if os.environ.get("BOT_TOKEN"):
        config["bot_token"] = os.environ["BOT_TOKEN"]
    if os.environ.get("ADMIN_ID"):
        config["admin_id"] = int(os.environ["ADMIN_ID"])
    if os.environ.get("GROUP_ID"):
        config["group_id"] = int(os.environ["GROUP_ID"])
    if os.environ.get("VPS_URL") and not config.get("vps_url"):
        config["vps_url"] = os.environ["VPS_URL"]

    if not config.get("bot_token"):
        raise ValueError("No BOT_TOKEN found! Set it in bot_config.json or env variable.")

    if "allowed_users" not in config:
        config["allowed_users"] = {}
    if "banned_users" not in config:
        config["banned_users"] = []

    return config

def save_config(config):
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=4)

def load_user_data():
    if not os.path.exists(USER_DATA_PATH):
        return {}
    with open(USER_DATA_PATH, "r") as f:
        return json.load(f)

def save_user_data(data):
    with open(USER_DATA_PATH, "w") as f:
        json.dump(data, f, indent=4)

def get_user_data(user_id):
    data = load_user_data()
    uid = str(user_id)
    if uid in data:
        saved = data[uid]
        saved_time = datetime.fromisoformat(saved.get("saved_at", "2000-01-01T00:00:00"))
        if datetime.now() - saved_time > timedelta(hours=DATA_EXPIRY_HOURS):
            del data[uid]
            save_user_data(data)
            return None
        return saved
    return None

def set_user_data(user_id, fb_password, page_name):
    data = load_user_data()
    data[str(user_id)] = {
        "fb_password": fb_password,
        "page_name": page_name,
        "saved_at": datetime.now().isoformat()
    }
    save_user_data(data)

def clear_user_data(user_id):
    data = load_user_data()
    data.pop(str(user_id), None)
    save_user_data(data)

def clear_expired_data():
    data = load_user_data()
    now = datetime.now()
    expired = []
    for uid, saved in list(data.items()):
        saved_time = datetime.fromisoformat(saved.get("saved_at", "2000-01-01T00:00:00"))
        if now - saved_time > timedelta(hours=DATA_EXPIRY_HOURS):
            expired.append(uid)
    for uid in expired:
        del data[uid]
    if expired:
        save_user_data(data)
    return len(expired)

def load_page_log():
    if not os.path.exists(PAGE_LOG_PATH):
        return {}
    with open(PAGE_LOG_PATH, "r") as f:
        return json.load(f)

def save_page_log(data):
    with open(PAGE_LOG_PATH, "w") as f:
        json.dump(data, f, indent=4)

def log_page_creation(user_id, username, page_name):
    data = load_page_log()
    today = datetime.now().strftime("%Y-%m-%d")
    uid = str(user_id)
    if today not in data:
        data[today] = {}
    if uid not in data[today]:
        data[today][uid] = {"username": username, "pages": []}
    data[today][uid]["pages"].append({
        "page_name": page_name,
        "time": datetime.now().strftime("%H:%M:%S")
    })
    save_page_log(data)
    return len(data[today][uid]["pages"])

def get_today_count(user_id):
    data = load_page_log()
    today = datetime.now().strftime("%Y-%m-%d")
    uid = str(user_id)
    if today in data and uid in data[today]:
        return len(data[today][uid]["pages"])
    return 0

def is_admin(user_id):
    config = load_config()
    return user_id == config["admin_id"]

def is_allowed(user_id):
    config = load_config()
    if user_id == config["admin_id"]:
        return True
    if user_id in config.get("banned_users", []):
        return False
    return str(user_id) in config.get("allowed_users", {})

def is_banned(user_id):
    config = load_config()
    return user_id in config.get("banned_users", [])

def sync_send_message(chat_id, text):
    try:
        config = load_config()
        url = f"https://api.telegram.org/bot{config['bot_token']}/sendMessage"
        payload = {"chat_id": chat_id, "text": text[:4000]}
        requests.post(url, json=payload, timeout=10)
        logger.info(f"Message sent to {chat_id}")
    except Exception as e:
        logger.error(f"sync_send_message failed: {e}")

def send_vps_request(user_id, username, fb_number, fb_password, page_name):
    config = load_config()
    vps_url = config.get("vps_url")

    if not vps_url:
        sync_send_message(user_id, "Error: VPS URL not configured. Contact admin.")
        return

    try:
        resp = requests.post(f"{vps_url}/create_page", json={
            "user_id": user_id,
            "username": username,
            "fb_number": fb_number,
            "fb_password": fb_password,
            "page_name": page_name
        }, timeout=10)

        if resp.status_code == 200:
            result = resp.json()
            if result.get("status") == "queued":
                sync_send_message(user_id, "Processing Ongoing... Please wait.\nYour request has been sent to the VPS.")
            else:
                sync_send_message(user_id, f"VPS Response: {result}")
        else:
            sync_send_message(user_id, f"VPS Error: HTTP {resp.status_code}")
    except requests.exceptions.ConnectionError:
        sync_send_message(user_id, "Error: Cannot connect to VPS. Make sure VPS server is running.")
    except Exception as e:
        sync_send_message(user_id, f"Error connecting to VPS: {str(e)}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "N/A"

    if is_banned(user_id):
        await update.message.reply_text("You are BANNED from using this bot.")
        return

    if not is_allowed(user_id):
        await update.message.reply_text(
            f"Access Denied!\n\n"
            f"Your ID: {user_id}\n"
            f"Username: @{username}\n\n"
            f"Send your ID to admin to get access."
        )
        return

    keyboard = []
    if is_admin(user_id):
        keyboard.append([InlineKeyboardButton("Admin Panel", callback_data="admin_panel")])
    keyboard.append([InlineKeyboardButton("Create Page", callback_data="create_page")])
    keyboard.append([InlineKeyboardButton("My Data", callback_data="my_data")])
    keyboard.append([InlineKeyboardButton("My Status", callback_data="my_status")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"Welcome {update.effective_user.first_name}!\n\n"
        f"I can create Facebook Pages automatically.\n"
        f"Your data is saved for {DATA_EXPIRY_HOURS} hours.\n\n"
        f"Click below to get started.",
        reply_markup=reply_markup
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        await update.message.reply_text("Access Denied!")
        return

    text = (
        "Available Commands:\n\n"
        "/start - Start the bot\n"
        "/help - Show this help\n"
        "/create - Create a new Facebook Page\n"
        "/mydata - View saved data\n"
        "/clear - Clear all saved data\n"
        "/change - Change saved data\n"
        "/status - Check your access status\n"
    )
    if is_admin(user_id):
        text += (
            "\nAdmin Commands:\n"
            "/allow <user_id> - Allow a user\n"
            "/ban <user_id> - Ban a user\n"
            "/unban <user_id> - Unban a user\n"
            "/users - List all users\n"
            "/broadcast - Broadcast message\n"
            "/setgroup <chat_id> - Set notification group\n"
            "/setvps <url> - Set VPS URL\n"
        )
    await update.message.reply_text(text)

async def mydata_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        await update.message.reply_text("Access Denied!")
        return

    saved = get_user_data(user_id)
    if saved:
        saved_time = datetime.fromisoformat(saved["saved_at"])
        expires = saved_time + timedelta(hours=DATA_EXPIRY_HOURS)
        remaining = expires - datetime.now()
        hours = int(remaining.total_seconds() // 3600)
        mins = int((remaining.total_seconds() % 3600) // 60)

        await update.message.reply_text(
            f"Saved Data:\n\n"
            f"FB Password: {saved['fb_password']}\n"
            f"Page Name: {saved['page_name']}\n\n"
            f"Expires in: {hours}h {mins}m\n"
            f"Saved at: {saved_time.strftime('%Y-%m-%d %H:%M')}"
        )
    else:
        await update.message.reply_text("No saved data found! Data may have expired (24hr).")

async def clear_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        await update.message.reply_text("Access Denied!")
        return
    clear_user_data(user_id)
    await update.message.reply_text("All your saved data has been cleared!")

async def change_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_allowed(user_id):
        await update.message.reply_text("Access Denied!")
        return
    keyboard = [
        [InlineKeyboardButton("Change FB Password", callback_data="change_fb_password")],
        [InlineKeyboardButton("Change Page Name", callback_data="change_page_name")],
        [InlineKeyboardButton("Change All", callback_data="change_all")],
        [InlineKeyboardButton("Back", callback_data="back_start")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("What do you want to change?", reply_markup=reply_markup)

async def my_data_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    saved = get_user_data(user_id)
    if saved:
        saved_time = datetime.fromisoformat(saved["saved_at"])
        expires = saved_time + timedelta(hours=DATA_EXPIRY_HOURS)
        remaining = expires - datetime.now()
        hours = int(remaining.total_seconds() // 3600)
        mins = int((remaining.total_seconds() % 3600) // 60)

        keyboard = [
            [InlineKeyboardButton("Create Page", callback_data="create_page")],
            [InlineKeyboardButton("Clear Data", callback_data="clear_data_confirm")],
            [InlineKeyboardButton("Change Data", callback_data="change_data_menu")],
            [InlineKeyboardButton("Back", callback_data="back_start")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"Saved Data:\n\n"
            f"FB Password: {saved['fb_password']}\n"
            f"Page Name: {saved['page_name']}\n\n"
            f"Expires in: {hours}h {mins}m",
            reply_markup=reply_markup
        )
    else:
        keyboard = [
            [InlineKeyboardButton("Create Page", callback_data="create_page")],
            [InlineKeyboardButton("Back", callback_data="back_start")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "No saved data found!\nData may have expired (24hr).",
            reply_markup=reply_markup
        )

async def clear_data_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    clear_user_data(query.from_user.id)
    await query.edit_message_text("All your saved data has been cleared!")

async def change_data_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("Change FB Password", callback_data="change_fb_password")],
        [InlineKeyboardButton("Change Page Name", callback_data="change_page_name")],
        [InlineKeyboardButton("Change All", callback_data="change_all")],
        [InlineKeyboardButton("Back", callback_data="my_data")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("What do you want to change?", reply_markup=reply_markup)

async def change_field_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    field = query.data.replace("change_", "")
    context.user_data["change_field"] = field

    prompts = {
        "fb_password": "Send new Facebook password:",
        "page_name": "Send new Page name:",
        "all": "Send new data in this format:\nFB_Password | Page_Name\n\nExample:\nmypass | My Page",
    }
    await query.edit_message_text(prompts.get(field, "Send new value:"))
    return CHANGE_FIELD

async def change_field_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    field = context.user_data.get("change_field", "")
    new_value = update.message.text

    saved = get_user_data(user_id) or {"fb_password": "", "page_name": ""}

    if field == "all":
        parts = new_value.split("|")
        if len(parts) == 2:
            saved["fb_password"] = parts[0].strip()
            saved["page_name"] = parts[1].strip()
        else:
            await update.message.reply_text("Invalid format! Use: FB_Password | Page_Name")
            return CHANGE_FIELD
    elif field == "fb_password":
        saved["fb_password"] = new_value
    elif field == "page_name":
        saved["page_name"] = new_value

    set_user_data(user_id, saved["fb_password"], saved["page_name"])
    await update.message.reply_text(f"Data updated!\n\nPage: {saved['page_name']}")
    return ConversationHandler.END

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Access Denied!")
        return

    config = load_config()
    allowed = config.get("allowed_users", {})
    banned = config.get("banned_users", [])
    group_id = config.get("group_id", "Not set")
    vps_url = config.get("vps_url", "Not set")

    keyboard = [
        [InlineKeyboardButton("Allow User", callback_data="admin_allow")],
        [InlineKeyboardButton("Ban User", callback_data="admin_ban")],
        [InlineKeyboardButton("Unban User", callback_data="admin_unban")],
        [InlineKeyboardButton("List Users", callback_data="admin_list")],
        [InlineKeyboardButton("Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton("Set Group", callback_data="admin_set_group")],
        [InlineKeyboardButton("Set VPS URL", callback_data="admin_set_vps")],
        [InlineKeyboardButton("Today's Log", callback_data="admin_today_log")],
        [InlineKeyboardButton("All User Data", callback_data="admin_all_data")],
        [InlineKeyboardButton("Clear User Data", callback_data="admin_clear_user")],
        [InlineKeyboardButton("Back", callback_data="back_start")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = (
        "Admin Panel\n\n"
        f"Allowed Users: {len(allowed)}\n"
        f"Banned Users: {len(banned)}\n"
        f"Group ID: {group_id}\n"
        f"VPS URL: {vps_url}\n\n"
        "Select an option:"
    )
    await query.edit_message_text(text, reply_markup=reply_markup)

async def admin_set_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    await query.edit_message_text(
        "Send the group chat ID:\n\n"
        "Format: /setgroup <chat_id>\n"
        "Example: /setgroup -1001234567890"
    )

async def setgroup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("Admin only!")
        return
    if not context.args:
        await update.message.reply_text("Usage: /setgroup <chat_id>")
        return

    try:
        group_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid group ID!")
        return

    config = load_config()
    config["group_id"] = group_id
    save_config(config)
    await update.message.reply_text(f"Notification group set to: {group_id}")

async def admin_set_vps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    await query.edit_message_text(
        "Send the VPS URL:\n\n"
        "Format: /setvps <url>\n"
        "Example: /setvps http://123.45.67.89:5000"
    )

async def setvps_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("Admin only!")
        return
    if not context.args:
        await update.message.reply_text("Usage: /setvps <url>\nExample: /setvps https://example.com")
        return

    vps_url = context.args[0].rstrip("/")
    try:
        config = load_config()
        config["vps_url"] = vps_url
        save_config(config)
    except Exception as e:
        logger.error(f"Failed to save VPS URL to config: {e}")
    await update.message.reply_text(f"VPS URL set to: {vps_url}\n\n⚠️ Note: On Railway, this resets on restart.\nSet VPS_URL env var in Railway dashboard for permanent fix.")

async def admin_today_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    log = load_page_log()
    today = datetime.now().strftime("%Y-%m-%d")
    today_log = log.get(today, {})

    text = f"Today's Page Creation Log ({today}):\n\n"
    total = 0
    for uid, info in today_log.items():
        count = len(info["pages"])
        total += count
        text += f"{info['username']} (ID: {uid})\n"
        for p in info["pages"]:
            text += f"   {p['page_name']} at {p['time']}\n"
        text += "\n"

    text += f"Total Pages Today: {total}"
    if not today_log:
        text += "No pages created today."

    await query.edit_message_text(text)

async def admin_allow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    await query.edit_message_text(
        "Send the user ID to allow:\n\n"
        "Format: /allow <user_id>\n"
        "Example: /allow 123456789"
    )

async def admin_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    await query.edit_message_text(
        "Send the user ID to ban:\n\n"
        "Format: /ban <user_id>\n"
        "Example: /ban 123456789"
    )

async def admin_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    await query.edit_message_text(
        "Send the user ID to unban:\n\n"
        "Format: /unban <user_id>\n"
        "Example: /unban 123456789"
    )

async def admin_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    config = load_config()
    allowed = config.get("allowed_users", {})
    banned = config.get("banned_users", [])

    text = "Allowed Users:\n\n"
    for uid, info in allowed.items():
        text += f"ID: {uid} | Name: {info.get('name', 'N/A')} | @{info.get('username', 'N/A')}\n"

    text += f"\nBanned Users:\n\n"
    for uid in banned:
        text += f"ID: {uid}\n"

    if not allowed:
        text += "No users allowed yet.\n"
    if not banned:
        text += "No users banned.\n"

    await query.edit_message_text(text)

async def admin_all_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    data = load_user_data()
    if not data:
        await query.edit_message_text("No user data saved.")
        return

    text = "All Saved User Data:\n\n"
    for uid, info in data.items():
        saved_time = datetime.fromisoformat(info.get("saved_at", "2000-01-01T00:00:00"))
        expires = saved_time + timedelta(hours=DATA_EXPIRY_HOURS)
        remaining = expires - datetime.now()
        hours = int(remaining.total_seconds() // 3600)
        mins = int((remaining.total_seconds() % 3600) // 60)

        text += f"ID: {uid}\n"
        text += f"Pass: {info['fb_password']}\n"
        text += f"Page: {info['page_name']}\n"
        text += f"Expires: {hours}h {mins}m\n\n"

    await query.edit_message_text(text[:4000])

async def admin_clear_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    await query.edit_message_text(
        "Send user ID to clear their data:\n\n"
        "Format: /cleardata <user_id>\n"
        "Example: /cleardata 123456789"
    )

async def cleardata_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("Admin only!")
        return
    if not context.args:
        await update.message.reply_text("Usage: /cleardata <user_id>")
        return
    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid user ID!")
        return

    clear_user_data(target_id)
    await update.message.reply_text(f"User {target_id} data cleared!")

async def viewedata_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("Admin only!")
        return
    if not context.args:
        await update.message.reply_text("Usage: /viewdata <user_id>")
        return
    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid user ID!")
        return

    saved = get_user_data(target_id)
    if saved:
        await update.message.reply_text(
            f"User {target_id} Data:\n\n"
            f"Password: {saved['fb_password']}\n"
            f"Page: {saved['page_name']}\n"
            f"Saved: {saved['saved_at']}"
        )
    else:
        await update.message.reply_text(f"No saved data for user {target_id}")

async def allow_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("Admin only!")
        return
    if not context.args:
        await update.message.reply_text("Usage: /allow <user_id>")
        return
    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid user ID!")
        return

    config = load_config()
    if "allowed_users" not in config:
        config["allowed_users"] = {}
    config["allowed_users"][str(target_id)] = {
        "name": "N/A",
        "username": "N/A",
        "added_by": user_id
    }
    if target_id in config.get("banned_users", []):
        config["banned_users"].remove(target_id)
    save_config(config)
    await update.message.reply_text(f"User {target_id} has been ALLOWED!")

async def ban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("Admin only!")
        return
    if not context.args:
        await update.message.reply_text("Usage: /ban <user_id>")
        return
    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid user ID!")
        return

    config = load_config()
    if target_id == config["admin_id"]:
        await update.message.reply_text("Cannot ban the admin!")
        return
    if "banned_users" not in config:
        config["banned_users"] = []
    if target_id not in config["banned_users"]:
        config["banned_users"].append(target_id)
    config.get("allowed_users", {}).pop(str(target_id), None)
    save_config(config)
    await update.message.reply_text(f"User {target_id} has been BANNED!")

async def unban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("Admin only!")
        return
    if not context.args:
        await update.message.reply_text("Usage: /unban <user_id>")
        return
    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid user ID!")
        return
    config = load_config()
    if target_id in config.get("banned_users", []):
        config["banned_users"].remove(target_id)
    save_config(config)
    await update.message.reply_text(f"User {target_id} has been UNBANNED!")

async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("Admin only!")
        return
    config = load_config()
    allowed = config.get("allowed_users", {})
    banned = config.get("banned_users", [])
    text = "Allowed Users:\n\n"
    for uid, info in allowed.items():
        text += f"ID: {uid} | Name: {info.get('name', 'N/A')}\n"
    text += f"\nBanned Users:\n\n"
    for uid in banned:
        text += f"ID: {uid}\n"
    if not allowed:
        text += "No users allowed yet.\n"
    if not banned:
        text += "No users banned.\n"
    await update.message.reply_text(text)

async def my_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_banned(user_id):
        status = "BANNED"
    elif is_admin(user_id):
        status = "ADMIN"
    elif is_allowed(user_id):
        status = "ALLOWED"
    else:
        status = "NOT ALLOWED"
    today_count = get_today_count(user_id)
    await update.message.reply_text(
        f"Your ID: {user_id}\n"
        f"Status: {status}\n"
        f"Pages today: {today_count}"
    )

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await my_status(update, context)

async def create_page_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_allowed(query.from_user.id):
        await query.edit_message_text("Access Denied!")
        return ConversationHandler.END

    context.user_data.clear()

    saved = get_user_data(query.from_user.id)
    if saved:
        keyboard = [
            [InlineKeyboardButton("Use Saved Data", callback_data="use_saved_data")],
            [InlineKeyboardButton("Enter New Data", callback_data="enter_new_data")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"Saved data found:\n\n"
            f"Password: {saved['fb_password']}\n"
            f"Page: {saved['page_name']}\n\n"
            f"Use saved or enter new?",
            reply_markup=reply_markup
        )
        return ConversationHandler.END
    else:
        await query.edit_message_text("Step 1/3: Send your Facebook email or phone number:")
        return FB_NUMBER

async def use_saved_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    saved = get_user_data(query.from_user.id)
    if not saved:
        await query.edit_message_text("No saved data found!")
        return ConversationHandler.END

    context.user_data.clear()
    context.user_data["fb_number_mode"] = "use_saved"

    await query.edit_message_text(
        f"Using saved data:\n"
        f"Password: {saved['fb_password']}\n"
        f"Page: {saved['page_name']}\n\n"
        f"Step 1/3: Send your Facebook email or phone number:"
    )
    return FB_NUMBER

async def enter_new_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.edit_message_text("Step 1/3: Send your Facebook email or phone number:")
    return FB_NUMBER

async def fb_number_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["fb_number"] = update.message.text

    if context.user_data.get("fb_number_mode") == "use_saved":
        saved = get_user_data(update.effective_user.id)
        if saved:
            user_id = update.effective_user.id
            user_name = update.effective_user.first_name or "Unknown"
            fb_number = context.user_data["fb_number"]
            fb_password = saved["fb_password"]
            page_name = saved["page_name"]

            set_user_data(user_id, fb_password, page_name)
            await update.message.reply_text(
                f"Using saved data:\n"
                f"Password: {fb_password}\n"
                f"Page: {page_name}\n\n"
                f"Processing Ongoing... Please wait."
            )

            thread = threading.Thread(
                target=send_vps_request,
                args=(user_id, user_name, fb_number, fb_password, page_name),
                daemon=True
            )
            thread.start()
            context.user_data.clear()
            return ConversationHandler.END

    await update.message.reply_text("Step 2/3: Send your Facebook password:")
    return FB_PASSWORD

async def fb_password_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["fb_password"] = update.message.text
    await update.message.reply_text("Step 3/3: Send the Page name you want to create:")
    return PAGE_NAME

async def page_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["page_name"] = update.message.text

    user_id = update.effective_user.id
    user_name = update.effective_user.first_name or "Unknown"
    fb_number = context.user_data["fb_number"]
    fb_password = context.user_data["fb_password"]
    page_name = context.user_data["page_name"]

    set_user_data(user_id, fb_password, page_name)

    await update.message.reply_text("Processing Ongoing... Please wait.")

    thread = threading.Thread(
        target=send_vps_request,
        args=(user_id, user_name, fb_number, fb_password, page_name),
        daemon=True
    )
    thread.start()
    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled!")
    return ConversationHandler.END

async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Access Denied!")
        return
    await query.edit_message_text("Send the broadcast message to all users:")
    return BROADCAST_MSG

async def broadcast_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("Admin only!")
        return ConversationHandler.END

    msg = update.message.text
    config = load_config()
    allowed = config.get("allowed_users", {})
    admin_id = config["admin_id"]
    sent = 0
    failed = 0

    await update.message.reply_text(f"Broadcasting to {len(allowed) + 1} users...")

    for uid in list(allowed.keys()) + [str(admin_id)]:
        try:
            await context.bot.send_message(chat_id=int(uid), text=f"Broadcast:\n\n{msg}")
            sent += 1
        except:
            failed += 1

    await update.message.reply_text(f"Broadcast done!\nSent: {sent}\nFailed: {failed}")
    return ConversationHandler.END

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("Admin only!")
        return
    await update.message.reply_text("Send the broadcast message to all users:")

async def back_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    keyboard = []
    if is_admin(user_id):
        keyboard.append([InlineKeyboardButton("Admin Panel", callback_data="admin_panel")])
    keyboard.append([InlineKeyboardButton("Create Page", callback_data="create_page")])
    keyboard.append([InlineKeyboardButton("My Data", callback_data="my_data")])
    keyboard.append([InlineKeyboardButton("My Status", callback_data="my_status")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        f"Welcome {query.from_user.first_name}!\n\n"
        f"I can create Facebook Pages automatically.\n"
        f"Your data is saved for {DATA_EXPIRY_HOURS} hours.\n\n"
        f"Click below to get started.",
        reply_markup=reply_markup
    )

async def error_handler(update, context):
    logger.error(f"Exception while handling an update: {context.error}", exc_info=context.error)

async def post_init(app):
    logger.warning("Bot connected to Telegram successfully!")

async def post_shutdown(app):
    logger.warning("Bot shutting down...")

async def post_stop(app):
    logger.warning("Bot stopped.")

def build_app():
    config = load_config()
    app = (
        Application.builder()
        .token(config["bot_token"])
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    app.add_error_handler(error_handler)

    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(create_page_start, pattern="^create_page$"),
            CallbackQueryHandler(use_saved_data, pattern="^use_saved_data$"),
            CallbackQueryHandler(enter_new_data, pattern="^enter_new_data$"),
            CallbackQueryHandler(admin_broadcast, pattern="^admin_broadcast$"),
            CallbackQueryHandler(change_field_start, pattern="^change_(fb_password|page_name|all)$"),
            CommandHandler("broadcast", broadcast_cmd),
            CommandHandler("change", change_cmd),
        ],
        states={
            FB_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, fb_number_received)],
            FB_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, fb_password_received)],
            PAGE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, page_name_received)],
            BROADCAST_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_received)],
            CHANGE_FIELD: [MessageHandler(filters.TEXT & ~filters.COMMAND, change_field_received)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("allow", allow_cmd))
    app.add_handler(CommandHandler("ban", ban_cmd))
    app.add_handler(CommandHandler("unban", unban_cmd))
    app.add_handler(CommandHandler("users", users_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("my_status", my_status))
    app.add_handler(CommandHandler("mydata", mydata_cmd))
    app.add_handler(CommandHandler("clear", clear_cmd))
    app.add_handler(CommandHandler("setgroup", setgroup_cmd))
    app.add_handler(CommandHandler("setvps", setvps_cmd))
    app.add_handler(CommandHandler("cleardata", cleardata_cmd))
    app.add_handler(CommandHandler("viewdata", viewedata_cmd))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(admin_panel, pattern="^admin_panel$"))
    app.add_handler(CallbackQueryHandler(admin_allow, pattern="^admin_allow$"))
    app.add_handler(CallbackQueryHandler(admin_ban, pattern="^admin_ban$"))
    app.add_handler(CallbackQueryHandler(admin_unban, pattern="^admin_unban$"))
    app.add_handler(CallbackQueryHandler(admin_list, pattern="^admin_list$"))
    app.add_handler(CallbackQueryHandler(admin_set_group, pattern="^admin_set_group$"))
    app.add_handler(CallbackQueryHandler(admin_set_vps, pattern="^admin_set_vps$"))
    app.add_handler(CallbackQueryHandler(admin_today_log, pattern="^admin_today_log$"))
    app.add_handler(CallbackQueryHandler(admin_all_data, pattern="^admin_all_data$"))
    app.add_handler(CallbackQueryHandler(admin_clear_user, pattern="^admin_clear_user$"))
    app.add_handler(CallbackQueryHandler(back_start, pattern="^back_start$"))
    app.add_handler(CallbackQueryHandler(my_status, pattern="^my_status$"))
    app.add_handler(CallbackQueryHandler(my_data_callback, pattern="^my_data$"))
    app.add_handler(CallbackQueryHandler(clear_data_confirm, pattern="^clear_data_confirm$"))
    app.add_handler(CallbackQueryHandler(change_data_menu, pattern="^change_data_menu$"))
    return app

def main():
    clear_expired_data()
    try:
        logger.warning("Starting bot...")
        app = build_app()
        app.run_polling(
            drop_pending_updates=True,
            poll_interval=2.0,
            allowed_updates=Update.ALL_TYPES,
        )
    except (NetworkError, TimedOut) as e:
        logger.error(f"Network error: {e}")
    except Forbidden as e:
        logger.error(f"Forbidden error (check bot token): {e}")
    except BadRequest as e:
        logger.error(f"Bad request error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}\n{traceback.format_exc()}")

if __name__ == "__main__":
    main()
