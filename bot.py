import os
import logging
import aiohttp
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────
NEAR_RPC = "https://rpc.mainnet.near.org"
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# Known DAO factory contracts on NEAR mainnet
DAO_FACTORY = "sputnik-dao.near"
ASTRO_FACTORY = "astrodao.near"

# ── RPC Helper ────────────────────────────────────────────────────────────────
async def _rpc(method: str, params: dict) -> dict:
    """
    Generic async NEAR JSON-RPC helper.
    Returns the 'result' field of the response, or raises on error.
    """
    payload = {
        "jsonrpc": "2.0",
        "id": "daobot",
        "method": method,
        "params": params,
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(NEAR_RPC, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            data = await resp.json()
            if "error" in data:
                raise RuntimeError(f"RPC error: {data['error']}")
            return data.get("result", {})


# ── NEAR Helper Functions ─────────────────────────────────────────────────────

async def get_proposals(dao_account: str, from_index: int = 0, limit: int = 10) -> list:
    """
    Fetch proposals from a Sputnik v2 DAO contract using view_call.
    Returns a list of proposal dicts.
    """
    import json, base64

    args = json.dumps({"from_index": from_index, "limit": limit})
    args_b64 = base64.b64encode(args.encode()).decode()

    result = await _rpc(
        "query",
        {
            "request_type": "call_function",
            "finality": "final",
            "account_id": dao_account,
            "method_name": "get_proposals",
            "args_base64": args_b64,
        },
    )

    raw = bytes(result["result"])
    proposals = json.loads(raw.decode())
    return proposals


async def get_proposal(dao_account: str, proposal_id: int) -> dict:
    """
    Fetch a single proposal by ID from a Sputnik v2 DAO.
    """
    import json, base64

    args = json.dumps({"id": proposal_id})
    args_b64 = base64.b64encode(args.encode()).decode()

    result = await _rpc(
        "query",
        {
            "request_type": "call_function",
            "finality": "final",
            "account_id": dao_account,
            "method_name": "get_proposal",
            "args_base64": args_b64,
        },
    )

    raw = bytes(result["result"])
    return json.loads(raw.decode())


async def get_dao_info(dao_account: str) -> dict:
    """
    Fetch DAO policy / config — returns the last proposal count and basic info.
    We use get_last_proposal_id to gauge activity.
    """
    import json, base64

    args_b64 = base64.b64encode(b"{}").decode()

    result = await _rpc(
        "query",
        {
            "request_type": "call_function",
            "finality": "final",
            "account_id": dao_account,
            "method_name": "get_last_proposal_id",
            "args_base64": args_b64,
        },
    )

    raw = bytes(result["result"])
    last_id = json.loads(raw.decode())
    return {"dao": dao_account, "last_proposal_id": last_id}


async def get_active_proposals(dao_account: str, max_scan: int = 20) -> list:
    """
    Return proposals whose status is 'InProgress' (i.e. still open for voting).
    Scans the last `max_scan` proposals.
    """
    info = await get_dao_info(dao_account)
    last_id: int = info["last_proposal_id"]

    from_index = max(0, last_id - max_scan + 1)
    limit = last_id - from_index + 1
    if limit <= 0:
        return []

    proposals = await get_proposals(dao_account, from_index=from_index, limit=limit)
    active = [p for p in proposals if p.get("status") == "InProgress"]
    return active


async def get_account_balance(account_id: str) -> dict:
    """
    Fetch NEAR account balance (useful for showing DAO treasury info).
    """
    result = await _rpc(
        "query",
        {
            "request_type": "view_account",
            "finality": "final",
            "account_id": account_id,
        },
    )
    return result


# ── Formatting Helpers ────────────────────────────────────────────────────────

def _yocto_to_near(yocto: str) -> str:
    """Convert yoctoNEAR string to a readable NEAR string."""
    try:
        value = int(yocto) / 10**24
        return f"{value:,.4f} NEAR"
    except Exception:
        return yocto


def _format_proposal(p: dict, idx: int | None = None) -> str:
    """Return a nicely formatted string for a single proposal."""
    pid = p.get("id", idx)
    kind = p.get("kind", {})
    kind_name = list(kind.keys())[0] if isinstance(kind, dict) and kind else str(kind)
    description = p.get("description", "No description")[:200]
    proposer = p.get("proposer", "unknown")
    status = p.get("status", "Unknown")
    votes = p.get("vote_counts", {})

    status_emoji = {
        "InProgress": "🟡",
        "Approved": "✅",
        "Rejected": "❌",
        "Removed": "🗑️",
        "Expired": "⏰",
        "Moved": "➡️",
        "Failed": "💥",
    }.get(status, "❓")

    lines = [
        f"━━━━━━━━━━━━━━━━━━━━━━",
        f"📋 *Proposal #{pid}*",
        f"{status_emoji} Status: *{status}*",
        f"🔧 Kind: `{kind_name}`",
        f"👤 Proposer: `{proposer}`",
        f"📝 Description:\n_{description}_",
    ]

    if votes:
        yes = votes.get("Yes", [0])[0] if isinstance(votes.get("Yes"), list) else votes.get("Yes", 0)
        no = votes.get("No", [0])[0] if isinstance(votes.get("No"), list) else votes.get("No", 0)
        lines.append(f"🗳️ Votes — ✅ Yes: {yes}  ❌ No: {no}")

    return "\n".join(lines)


# ── /start and /help ──────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome message and quick-start guide."""
    text = (
        "👋 *Welcome to NEAR DAO Proposal Alert Bot!*\n\n"
        "Stay on top of every proposal across NEAR DAO communities — "
        "get real-time updates, browse active votes, and never miss a decision.\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🚀 *Quick Start*\n\n"
        "1️⃣ `/proposals <dao.near>` — latest proposals\n"
        "2️⃣ `/active <dao.near>` — open / in-progress proposals\n"
        "3️⃣ `/proposal <dao.near> <id>` — single proposal detail\n"
        "4️⃣ `/daoinfo <dao.near>` — DAO summary & treasury\n"
        "5️⃣ `/help` — full command list\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 *Example DAO accounts:*\n"
        "`community.sputnik-dao.near`\n"
        "`marketing.sputnik-dao.near`\n\n"
        "Built with ❤️ on NEAR 🌈"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Detailed help message."""
    text = (
        "📖 *NEAR DAO Proposal Alert — Command Reference*\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "*/start*\n"
        "  Show welcome message & quick guide.\n\n"
        "*/proposals <dao\\_account> [limit]*\n"
        "  Show the latest proposals from a DAO.\n"
        "  `limit` defaults to 5 (max 10).\n"
        "  Example: `/proposals community.sputnik-dao.near 5`\n\n"
        "*/active <dao\\_account>*\n"
        "  Show only *InProgress* (open) proposals.\n"
        "  Example: `/active community.sputnik-dao.near`\n\n"
        "*/proposal <dao\\_account> <id>*\n"
        "  Fetch a single proposal by numeric ID.\n"
        "  Example: `/proposal community.sputnik-dao.near 42`\n\n"
        "*/daoinfo <dao\\_account>*\n"
        "  Show DAO summary: last proposal ID, treasury balance.\n"
        "  Example: `/daoinfo community.sputnik-dao.near`\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🌐 Data sourced from NEAR mainnet RPC.\n"
        "📡 https://rpc.mainnet.near.org"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ── Command Handlers ──────────────────────────────────────────────────────────

async def proposals_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /proposals <dao_account> [limit]
    Fetch and display the latest N proposals from a DAO.
    """
    args = context.args
    if not args:
        await update.message.reply_text(
            "⚠️ Usage: `/proposals <dao_account> [limit]`\n"
            "Example: `/proposals community.sputnik-dao.near 5`",
            parse_mode="Markdown",
        )
        return

    dao_account = args[0].strip()
    try:
        limit = min(int(args[1]), 10) if len(args) > 1 else 5
    except ValueError:
        limit = 5

    await update.message.reply_text(f"🔍 Fetching latest {limit} proposals from `{dao_account}`…", parse_mode="Markdown")

    try:
        info = await get_dao_info(dao_account)
        last_id: int = info["last_proposal_id"]

        from_index = max(0, last_id - limit + 1)
        actual_limit = last_id - from_index + 1

        proposals = await get_proposals(dao_account, from_index=from_index, limit=actual_limit)

        if not proposals:
            await update.message.reply_text("ℹ️ No proposals found for this DAO.")
            return

        header = (
            f"📜 *Latest Proposals — {dao_account}*\n"
            f"Total proposals so far: *{last_id + 1}*\n"
        )
        await update.message.reply_text(header, parse_mode="Markdown")

        for p in reversed(proposals[-limit:]):
            msg = _format_proposal(p)
            await update.message.reply_text(msg, parse_mode="Markdown")

    except Exception as e:
        logger.exception("proposals_command error")
        await update.message.reply_text(
            f"❌ Error fetching proposals:\n`{e}`\n\n"
            "Make sure the DAO account is a valid Sputnik v2 DAO on NEAR mainnet.",
            parse_mode="Markdown",
        )


async def active_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /active <dao_account>
    Show only proposals with status InProgress (open for voting).
    """
    args = context.args
    if not args:
        await update.message.reply_text(
            "⚠️ Usage: `/active <dao_account>`\n"
            "Example: `/active community.sputnik-dao.near`",
            parse_mode="Markdown",
        )
        return

    dao_account = args[0].strip()
    await update.message.reply_text(f"🟡 Scanning for active proposals in `{dao_account}`…", parse_mode="Markdown")

    try:
        active = await get_active_proposals(dao_account, max_scan=30)

        if not active:
            await update.message.reply_text(
                f"✅ No active (InProgress) proposals found in the last 30 for `{dao_account}`.",
                parse_mode="Markdown",
            )
            return

        header = (
            f"🗳️ *Active Proposals — {dao_account}*\n"
            f"Found *{len(active)}* open proposal(s) — vote now!\n"
        )
        await update.message.reply_text(header, parse_mode="Markdown")

        for p in active:
            msg = _format_proposal(p)
            await update.message.reply_text(msg, parse_mode="Markdown")

    except Exception as e:
        logger.exception("active_command error")
        await update.message.reply_text(
            f"❌ Error: `{e}`",
            parse_mode="Markdown",
        )


async def proposal_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /proposal <dao_account> <proposal_id>
    Fetch a single proposal by its numeric ID.
    """
    args = context.args
    if len(args) < 2:
        await update.message.reply_text(
            "⚠️ Usage: `/proposal <dao_account> <id>`\n"
            "Example: `/proposal community.sputnik-dao.near 42`",
            parse_mode="Markdown",
        )
        return

    dao_account = args[0].strip()
    try:
        proposal_id = int(args[1])
    except ValueError:
        await update.message.reply_text("❌ Proposal ID must be a number.", parse_mode="Markdown")
        return

    await update.message.reply_text(
        f"🔎 Fetching proposal #{proposal_id} from `{dao_account}`…",
        parse_mode="Markdown",
    )

    try:
        p = await get_proposal(dao_account, proposal_id)
        msg = _format_proposal(p)
        await update.message.reply_text(msg, parse_mode="Markdown")

    except Exception as e:
        logger.exception("proposal_command error")
        await update.message.reply_text(
            f"❌ Error: `{e}`\n\nCheck the DAO account and proposal ID.",
            parse_mode="Markdown",
        )


async def daoinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /daoinfo <dao_account>
    Show a summary: last proposal count + treasury balance.
    """
    args = context.args
    if not args:
        await update.message.reply_text(
            "⚠️ Usage: `/daoinfo <dao_account>`\n"
            "Example: `/daoinfo community.sputnik-dao.near`",
            parse_mode="Markdown",
        )
        return

    dao_account = args[0].strip()
    await update.message.reply_text(f"📊 Loading DAO info for `{dao_account}`…", parse_mode="Markdown")

    try:
        info = await get_dao_info(dao_account)
        balance_data = await get_account_balance(dao_account)

        amount = balance_data.get("amount", "0")
        locked = balance_data.get("locked", "0")
        storage_bytes = balance_data.get("storage_usage", 0)

        last_id: int = info["last_proposal_id"]
        total = last_id + 1

        text = (
            f"🏛️ *DAO Info — {dao_account}*\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📋 Total Proposals: *{total}*\n"
            f"🆔 Last Proposal ID: *{last_id}*\n\n"
            f"💰 Treasury Balance:\n"
            f"   Available: `{_yocto_to_near(amount)}`\n"
            f"   Locked:    `{_yocto_to_near(locked)}`\n\n"
            f"💾 Storage Used: `{storage_bytes:,} bytes`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔗 [View on NEAR Explorer](https://explorer.near.org/accounts/{dao_account})"
        )
        await update.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=True)

    except Exception as e:
        logger.exception("daoinfo_command error")
        await update.message.reply_text(
            f"❌ Error: `{e}`\n\nMake sure the account exists on NEAR mainnet.",
            parse_mode="Markdown",
        )


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(

def main() -> None:
    logging.basicConfig(level=logging.INFO)
    token = os.environ.get("BOT_TOKEN", "")
    application = ApplicationBuilder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("proposals", proposals_command))
    application.add_handler(CommandHandler("active", active_command))
    application.add_handler(CommandHandler("proposal", proposal_command))
    application.add_handler(CommandHandler("daoinfo", daoinfo_command))
    application.run_polling()

if __name__ == "__main__":
    main()
