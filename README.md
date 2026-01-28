# Shuttle Bot

A Telegram bot for checking campus shuttle bus schedules.

## Features
- Check next shuttle at any stop
- View full daily schedules
- Natural language queries
- Inline keyboard buttons for easy navigation

## Local Setup
```bash
pip install -r requirements.txt
python telegram_bot.py
```

## Environment Variables
- `TELEGRAM_BOT_TOKEN` - Your Telegram bot token from @BotFather

## Deployment
This bot is configured for deployment on Railway or Render.

### Deploy to Railway
1. Push to GitHub
2. Connect to Railway
3. Add environment variable: `TELEGRAM_BOT_TOKEN`

### Deploy to Render
1. Push to GitHub
2. Create new Background Worker on Render
3. Add environment variable: `TELEGRAM_BOT_TOKEN`
