# NEAR DAO Proposal Alert Bot

A Telegram bot that delivers real-time alerts and information about NEAR Protocol DAO proposals. Users can browse active proposals, inspect DAO policies, and stay engaged with the NEAR ecosystem — all without leaving Telegram.

---

## Prerequisites

- Python 3.9+
- A Telegram bot token from [@BotFather](https://t.me/BotFather)

---

## Installation

git clone https://github.com/your-username/near-dao-alert-bot.git
cd near-dao-alert-bot
pip install -r requirements.txt

---

## Configuration

1. Open Telegram and start a chat with [@BotFather](https://t.me/BotFather)
2. Send `/newbot` and follow the prompts to create your bot
3. Copy the token provided and set it as an environment variable:

export BOT_TOKEN=your_telegram_bot_token_here

On Windows:

set BOT_TOKEN=your_telegram_bot_token_here

You can also create a `.env` file in the project root:

BOT_TOKEN=your_telegram_bot_token_here

---

## Running

python bot.py

---

## Available Commands

| Command | Description |
|---|---|
| `/start` | Start the bot and see a welcome message |
| `/help` | Display help information and command list |
| `/proposals` | List all active DAO proposals |
| `/proposal` | Get details about a specific proposal |
| `/daos` | Browse available NEAR DAOs |
| `/policy` | View the governance policy for a DAO |

---

## Deploy

**Railway** (recommended): Push to GitHub, connect the repo in [Railway](https://railway.app), and set the `BOT_TOKEN` environment variable in the project settings.

**Heroku**: Add a `Procfile` containing `worker: python bot.py`, then run:

heroku create
heroku config:set BOT_TOKEN=your_token_here
git push heroku main

---

## Project Structure

near-dao-alert-bot/
├── bot.py
├── requirements.txt
├── Procfile
└── .env.example

---

## License

MIT