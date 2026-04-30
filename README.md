# NEAR DAO Proposal Alert Bot

A Telegram bot that delivers real-time alerts and information about NEAR DAO proposals directly to your chat. Stay informed about governance activity, treasury updates, and policy changes without leaving Telegram. It bridges the NEAR ecosystem and everyday users to drive deeper engagement with on-chain governance.

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
3. Copy the token BotFather provides
4. Set it as an environment variable:

export BOT_TOKEN=your_telegram_bot_token_here

Or create a `.env` file in the project root:

BOT_TOKEN=your_telegram_bot_token_here

---

## Running

python bot.py

---

## Available Commands

| Command | Description |
|---|---|
| `/start` | Start the bot and receive a welcome message |
| `/help` | Display help information and usage guide |
| `/proposals` | List all active DAO proposals |
| `/proposal` | Get details about a specific proposal |
| `/policy` | View current DAO governance policy |
| `/treasury` | Check DAO treasury balance and activity |
| `/latest` | Fetch the most recent proposal updates |

---

## Deployment

Deploy instantly to [Railway](https://railway.app) or [Heroku](https://heroku.com) using the included `Procfile`:

worker: python bot.py

Push your code, set the `BOT_TOKEN` environment variable in your platform's dashboard, and the bot will run continuously in the background.

---

## Project Structure

near-dao-alert-bot/
├── bot.py
├── requirements.txt
├── Procfile
└── .env.example

---

## Success Metric

Target: **100+ active users** engaging with the NEAR governance ecosystem through this bot.

---

## License

MIT