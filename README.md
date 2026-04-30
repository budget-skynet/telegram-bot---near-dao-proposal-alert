# NEAR DAO Proposal Alert Bot

A Telegram bot that delivers real-time alerts and information about NEAR Protocol DAO proposals. Users can browse active proposals, fetch details by ID, and stay connected with the NEAR governance ecosystem — all from within Telegram.

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
| `/start` | Start the bot and see the welcome message |
| `/help` | Display available commands and usage info |
| `/proposals` | List all DAO proposals |
| `/proposal` | Fetch details for a specific proposal by ID |
| `/active` | Show currently active proposals open for voting |
| `/daoinfo` | Display information about a specific DAO |
| `/latest` | Show the most recently submitted proposals |

---

## Deployment

Deploy instantly to [Railway](https://railway.app) or [Heroku](https://heroku.com) using the included `Procfile`:

worker: python bot.py

Push your code, set the `BOT_TOKEN` environment variable in your platform's dashboard, and the bot will run continuously in the background.

---

## The Viral Loop

User discovers bot → Gets live NEAR governance data → Engages with NEAR ecosystem

---

## License

MIT