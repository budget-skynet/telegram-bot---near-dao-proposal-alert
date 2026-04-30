# NEAR DAO Proposal Alert Bot

A Telegram bot that delivers real-time alerts and updates for NEAR Protocol DAO proposals. Stay informed about active governance proposals, track voting progress, and engage with the NEAR ecosystem — all without leaving Telegram.

---

## Prerequisites

- Python 3.9+
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- Internet access to query NEAR on-chain data

---

## Installation

git clone https://github.com/your-username/near-dao-alert-bot.git
cd near-dao-alert-bot
pip install -r requirements.txt

---

## Configuration

1. Open Telegram and start a chat with [@BotFather](https://t.me/BotFather)
2. Send `/newbot` and follow the prompts to create your bot
3. Copy the token provided by BotFather
4. Set it as an environment variable:

export BOT_TOKEN=your_telegram_bot_token_here

Or create a `.env` file in the project root:

BOT_TOKEN=your_telegram_bot_token_here

---

## Running

python bot.py

The bot will start polling for messages. You should see a confirmation log line once it is connected and ready.

---

## Available Commands

| Command | Description |
|---|---|
| `/start` | Start the bot and see the welcome message |
| `/help` | Display help and usage information |
| `/proposals` | List all DAO proposals |
| `/active` | Show currently active proposals open for voting |
| `/stats` | Display summary statistics for proposals and DAOs |

---

## Deploy

For a one-command cloud deploy, push to [Railway](https://railway.app) or [Heroku](https://heroku.com) using the included `Procfile`:

worker: python bot.py

railway up
# or
git push heroku main

---

## Project Structure

near-dao-alert-bot/
├── bot.py
├── requirements.txt
├── Procfile
└── .env.example

---

## Contributing

Pull requests are welcome. Open an issue first to discuss any major changes.

---

## License

[MIT](LICENSE)