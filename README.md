# FB Page Creator Telegram Bot

Telegram bot to automatically create Facebook pages using Selenium.

## Architecture

- **Railway** → Telegram Bot (polling, admin panel, user management)
- **VPS** → Selenium Server (Facebook page creation with Chrome)

## Setup

### 1. Telegram Bot (Railway)

1. Fork/clone this repo
2. Set environment variables in Railway:
   - `BOT_TOKEN` - Your Telegram bot token
   - `ADMIN_ID` - Your Telegram user ID
   - `GROUP_ID` - Group chat ID for notifications
   - `VPS_URL` - Your VPS server URL (e.g., `http://YOUR_IP:5000`)
3. Deploy to Railway

### 2. VPS Server

1. SSH into your VPS
2. Clone this repo or upload `vps_server.py`
3. Run: `bash deploy_vps.sh`
4. Test: `curl http://YOUR_IP:5000/health`

### 3. Bot Commands

| Command | Description |
|---------|-------------|
| `/start` | Start the bot |
| `/help` | Show help |
| `/create` | Create a Facebook page |
| `/mydata` | View saved data |
| `/clear` | Clear saved data |
| `/status` | Check access status |

#### Admin Commands

| Command | Description |
|---------|-------------|
| `/allow <id>` | Allow a user |
| `/ban <id>` | Ban a user |
| `/unban <id>` | Unban a user |
| `/users` | List all users |
| `/broadcast` | Broadcast message |
| `/setgroup <id>` | Set notification group |
| `/setvps <url>` | Set VPS URL |

## Files

- `bot.py` - Main Telegram bot
- `vps_server.py` - VPS Selenium server
- `requirements.txt` - Python dependencies
- `Procfile` - Railway deployment
- `Dockerfile` - VPS Docker deployment
- `deploy_vps.sh` - VPS setup script

## How It Works

1. User sends FB credentials + page name to bot
2. Bot sends request to VPS server
3. VPS opens Chrome, logs into Facebook, creates page
4. Result sent back to user via Telegram
