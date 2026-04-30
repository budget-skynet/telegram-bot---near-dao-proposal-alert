# NEAR DAO Proposal Alert Bot

A Telegram bot that delivers real-time alerts and information about NEAR Protocol DAO proposals. Users can browse active proposals, check DAO details, and stay engaged with the NEAR ecosystem — all without leaving Telegram.

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
| `/start` | Start the bot and see the welcome message |
| `/help` | Display help and usage information |
| `/proposals` | List all DAO proposals |
| `/active` | Show currently active proposals |
| `/proposal` | Get details on a specific proposal |
| `/daoinfo` | View information about a specific DAO |

---

## Deployment

Deploy instantly to [Railway](https://railway.app) or [Heroku](https://heroku.com) using the included `Procfile`:

worker: python bot.py

Push to your platform of choice and set `BOT_TOKEN` in the environment variables dashboard. The bot will start automatically.

---

## How It Works

Users interact with the bot → receive live NEAR DAO proposal data → stay informed and engaged with the NEAR ecosystem. The bot polls the NEAR blockchain for proposal updates and formats results clearly for a smooth Telegram experience.

---

## License

MIT