import os
import logging
import aiohttp
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

NEAR_RPC = 'https://rpc.mainnet.near.org'

# ─────────────────────────────────────────────
# 1. NEAR RPC helper
# ─────────────────────────────────────────────

async def _rpc(method: str, params: dict) -> dict:
    """Generic async NEAR RPC call."""
    payload = {
        "jsonrpc": "2.0",
        "id":      "dontcare",
        "method":  method,
        "params":  params,
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(
            NEAR_RPC,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            data = await resp.json()
            if "error" in data:
                raise ValueError(f"RPC error: {data['error']}")
            return data.get("result", {})


# ─────────────────────────────────────────────
# 2. NEAR helper functions
# ─────────────────────────────────────────────

async def get_proposals(dao_account: str) -> list:
    """
    Fetch all proposals from a Sputnik-v2 DAO contract.
    Returns a list of proposal dicts.
    """
    import base64, json

    args = json.dumps({"from_index": 0, "limit": 50})
    args_b64 = base64.b64encode(args.encode()).decode()

    result = await _rpc("query", {
        "request_type": "call_function",
        "finality":     "final",
        "account_id":   dao_account,
        "method_name":  "get_proposals",
        "args_base64":  args_b64,
    })

    raw = bytes(result["result"])
    proposals = json.loads(raw.decode())
    return proposals


async def get_proposal_by_id(dao_account: str, proposal_id: int) -> dict:
    """Fetch a single proposal by its ID."""
    import base64, json

    args = json.dumps({"id": proposal_id})
    args_b64 = base64.b64encode(args.encode()).decode()

    result = await _rpc("query", {
        "request_type": "call_function",
        "finality":     "final",
        "account_id":   dao_account,
        "method_name":  "get_proposal",
        "args_base64":  args_b64,
    })

    raw = bytes(result["result"])
    return json.loads(raw.decode())


async def get_dao_policy(dao_account: str) -> dict:
    """Fetch the DAO's policy (roles, quorum, etc.)."""
    import base64, json

    args_b64 = base64.b64encode(b"{}").decode()
    result = await _rpc("query", {
        "request_type": "call_function",
        "finality":     "final",
        "account_id":   dao_account,
        "method_name":  "get_policy",
        "args_base64":  args_b64,
    })

    raw = bytes(result["result"])
    return json.loads(raw.decode())


async def get_dao_config(dao_account: str) -> dict:
    """Fetch the DAO's on-chain config (name, purpose, metadata)."""
    import base64, json

    args_b64 = base64.b64encode(b"{}").decode()
    result = await _rpc("query", {
        "request_type": "call_function",
        "finality":     "final",
        "account_id":   dao_account,
        "method_name":  "get_config",
        "args_base64":  args_b64,
    })

    raw = bytes(result["result"])
    return json.loads(raw.decode())


async def get_last_proposal_id(dao_account: str) -> int:
    """Return the ID of the last proposal (= total proposals - 1)."""
    import base64, json

    args_b64 = base64.b64encode(b"{}").decode()
    result = await _rpc("query", {
        "request_type": "call_function",
        "finality":     "final",
        "account_id":   dao_account,
        "method_name":  "get_last_proposal_id",
        "args_base64":  args_b64,
    })

    raw = bytes(result["result"])
    return json.loads(raw.decode())


# ─────────────────────────────────────────────
# 3. Formatting helpers
# ─────────────────────────────────────────────

def _status_emoji(status: str) -> str:
    mapping = {
        "InProgress": "🟡",
        "Approved":   "✅",
        "Rejected":   "❌",
        "Removed":    "🗑️",
        "Expired":    "⏰",
        "Moved":      "➡️",
        "Failed":     "💥",
    }
    return mapping.get(status, "❓")


def _format_proposal(p: dict, index: int | None = None) -> str:
    pid        = p.get("id", index)
    kind       = p.get("kind", {})
    kind_name  = list(kind.keys())[0] if isinstance(kind, dict) else str(kind)
    status     = p.get("status", "Unknown")
    proposer   = p.get("proposer", "unknown")
    description= (p.get("description") or "")[:200]
    votes      = p.get("vote_counts", {})

    vote_str = ""
    for role, counts in votes.items():
        approve, reject, remove = counts[0], counts[1], counts[2]
        vote_str += f"\n    • {role}: ✅{approve} ❌{reject} 🗑️{remove}"

    return (
        f"📋 *Proposal #{pid}*\n"
        f"{_status_emoji(status)} Status: `{status}`\n"
        f"🔧 Kind: `{kind_name}`\n"
        f"👤 Proposer: `{proposer}`\n"
        f"📝 Description: {description or '_No description_'}\n"
        f"🗳️ Votes:{vote_str if vote_str else ' _none yet_'}"
    )


# ─────────────────────────────────────────────
# 4. /start and /help
# ─────────────────────────────────────────────

DEFAULT_DAO = "nearweek-news-contribution.sputnik-dao.near"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "👋 *Welcome to the NEAR DAO Proposal Alert Bot!*\n\n"
        "Stay up-to-date with on-chain governance proposals from any "
        "Sputnik-v2 DAO on NEAR Protocol.\n\n"
        "🚀 *Quick start:*\n"
        f"  Default DAO: `{DEFAULT_DAO}`\n\n"
        "Type /help to see all available commands."
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "📚 *NEAR DAO Proposal Alert Bot — Commands*\n\n"
        "*/proposals* `[dao]`\n"
        "  List the 10 most recent proposals.\n\n"
        "*/proposal* `<id>` `[dao]`\n"
        "  Show full details for a single proposal.\n\n"
        "*/active* `[dao]`\n"
        "  List only proposals that are currently _InProgress_.\n\n"
        "*/daoinfo* `[dao]`\n"
        "  Show DAO name, purpose & policy summary.\n\n"
        "*/latest* `[dao]`\n"
        "  Show the single most-recent proposal.\n\n"
        "💡 *Default DAO:* `nearweek-news-contribution.sputnik-dao.near`\n"
        "   Pass any Sputnik-v2 account as the optional `[dao]` argument."
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ─────────────────────────────────────────────
# 5. Command handlers
# ─────────────────────────────────────────────

async def proposals_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /proposals [dao_account]
    List the 10 most recent proposals.
    """
    dao = context.args[0] if context.args else DEFAULT_DAO
    await update.message.reply_text(
        f"⏳ Fetching proposals from `{dao}` …", parse_mode="Markdown"
    )

    try:
        proposals = await get_proposals(dao)
    except Exception as exc:
        await update.message.reply_text(f"❗ Error: {exc}")
        return

    if not proposals:
        await update.message.reply_text("No proposals found for this DAO.")
        return

    recent = proposals[-10:][::-1]          # newest first
    header = (
        f"🏛️ *DAO:* `{dao}`\n"
        f"📊 Total proposals: *{len(proposals)}*\n"
        f"Showing last {len(recent)}:\n"
        f"{'─'*35}"
    )
    await update.message.reply_text(header, parse_mode="Markdown")

    for p in recent:
        msg = _format_proposal(p)
        try:
            await update.message.reply_text(msg, parse_mode="Markdown")
        except Exception:
            await update.message.reply_text(msg)          # fallback plain


async def proposal_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /proposal <id> [dao_account]
    Show details for a specific proposal ID.
    """
    if not context.args:
        await update.message.reply_text("Usage: /proposal <id> [dao_account]")
        return

    try:
        proposal_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❗ Proposal ID must be a number.")
        return

    dao = context.args[1] if len(context.args) > 1 else DEFAULT_DAO
    await update.message.reply_text(
        f"⏳ Fetching proposal #{proposal_id} from `{dao}` …",
        parse_mode="Markdown",
    )

    try:
        p = await get_proposal_by_id(dao, proposal_id)
    except Exception as exc:
        await update.message.reply_text(f"❗ Error: {exc}")
        return

    # Full detail view
    kind      = p.get("kind", {})
    kind_name = list(kind.keys())[0] if isinstance(kind, dict) else str(kind)
    kind_body = kind.get(kind_name, {}) if isinstance(kind, dict) else {}
    status    = p.get("status", "Unknown")
    proposer  = p.get("proposer", "unknown")
    desc      = p.get("description") or "_No description provided_"
    submission= p.get("submission_time", "")

    vote_lines = ""
    for role, counts in (p.get("vote_counts") or {}).items():
        vote_lines += f"\n    • {role}: ✅{counts[0]} ❌{counts[1]} 🗑️{counts[2]}"

    votes_detail = ""
    for voter, vote in (p.get("votes") or {}).items():
        emoji = {"Approve": "✅", "Reject": "❌", "Remove": "🗑️"}.get(vote, "❓")
        votes_detail += f"\n    {emoji} `{voter}`"

    msg = (
        f"📋 *Proposal #{proposal_id} — Full Detail*\n"
        f"🏛️ DAO: `{dao}`\n"
        f"{_status_emoji(status)} Status: `{status}`\n"
        f"🔧 Kind: `{kind_name}`\n"
        f"👤 Proposer: `{proposer}`\n"
        f"🕒 Submitted: `{submission}`\n\n"
        f"📝 *Description:*\n{desc}\n\n"
        f"⚙️ *Kind details:*\n`{str(kind_body)[:300]}`\n\n"
        f"🗳️ *Vote counts:*{vote_lines if vote_lines else ' _none_'}\n\n"
        f"👥 *Individual votes:*{votes_detail if votes_detail else ' _none_'}"
    )
    try:
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception:
        await update.message.reply_text(msg)


async def active_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /active [dao_account]
    List proposals currently InProgress.
    """
    dao = context.args[0] if context.args else DEFAULT_DAO
    await update.message.reply_text(
        f"⏳ Fetching active proposals from `{dao}` …", parse_mode="Markdown"
    )

    try:
        proposals = await get_proposals(dao)
    except Exception as exc:
        await update.message.reply_text(f"❗ Error: {exc}")
        return

    active = [p for p in proposals if p.get("status") == "InProgress"]

    if not active:
        await update.message.reply_text(
            f"✅ No active proposals found in `{dao}`.", parse_mode="Markdown"
        )
        return

    header = (
        f"🟡 *Active Proposals in* `{dao}`\n"
        f"Found *{len(active)}* proposal(s) awaiting votes:\n"
        f"{'─'*35}"
    )
    await update.message.reply_text(header, parse_mode="Markdown")

    for p in active[-10:][::-1]:
        msg = _format_proposal(p)
        try:
            await update.message.reply_text(msg, parse_mode="Markdown")
        except Exception:
            await update.message.reply_text(msg)


async def daoinfo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /daoinfo [dao_account]
    Show DAO config and policy summary.
    """
    dao = context.args[0] if context.args else DEFAULT_DAO
    await update.message.reply_text(
        f"⏳ Fetching DAO info for `{dao}` …", parse_mode="Markdown"
    )

    try:
        config = await get_dao_config(dao)
        policy = await get_dao_policy(dao)
        last_id = await get_last_proposal_id(dao)
    except Exception as exc:
        await update.message.reply_text(f"❗ Error: {exc}")
        return

    name    = config.get("name", "N/A")
    purpose = (config.get("purpose") or "N/A")[:300]

    roles   = policy.get("roles", [])
    role_lines = ""
    for r in roles:
        rname  = r.get("name", "?")
        rperms = len(r.get("permissions", []))
        role_lines += f"\n    • `{rname}` — {rperms} permission(s)"

    bond         = policy.get("proposal_bond", "0")
    bond_near    = int(bond) / 1e24 if str(bond).isdigit() else bond
    period       = policy.get("proposal_period", "")
    vote_policy  = policy.get("default_vote_policy", {})
    threshold    = vote_policy.get("threshold", "N/A")

    msg = (
        f"🏛️ *DAO Info*\n"
        f"📛 Account: `{dao}`\n"
        f"🔤 Name: *{name}*\n"
        f"🎯 Purpose: {purpose}\n\n"
        f"📊 *Stats*\n"
        f"  📋 Total proposals: *{last_id + 1}*\n\n"
        f"📜 *Policy*\n"
        f"  💰 Proposal bond: `{bond_near:.2f} NEAR`\n"
        f"  ⏱️ Proposal period: `{period}`\n"
        f"  🗳️ Default threshold: `{threshold}`\n\n"
        f"👥 *Roles:*{role_lines if role_lines else ' _none_'}"
    )
    try:
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception:
        await update.message.reply_text(msg)


async def latest_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /latest [dao_account]
    Show the single most-recent proposal.
    """
    dao = context.args[0] if context.args else DEFAULT_DAO
    await update.message.reply_text(
        f"⏳ Fetching latest proposal from `{dao}` …", parse_mode="Markdown"
    )

    try:
        last_id = await get_last_proposal_id(dao)
        if last_id < 0:
            await update.message.reply_text("No proposals found.")
            return
        p = await get_proposal_by_id(dao, last_id)
    except Exception as exc:
        await update.message.reply_text(f"❗ Error: {exc}")
        return

    header = (
        f"🆕 *Latest proposal in* `{dao}`\n"
        f"{'─'*35}"
    )
    await update.message.reply_text(header, parse_mode="Markdown")

    msg = _format_proposal(p)
    try:
        await update.message.reply_text(msg, parse_mode="Markdown")
    except Exception:
        await update.message.reply_text(msg)

def main() -> None:
    logging.basicConfig(level=logging.INFO)
    token = os.environ.get("BOT_TOKEN", "")
    application = ApplicationBuilder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("proposals", proposals_command))
    application.add_handler(CommandHandler("proposal", proposal_command))
    application.add_handler(CommandHandler("active", active_command))
    application.add_handler(CommandHandler("daoinfo", daoinfo_command))
    application.add_handler(CommandHandler("latest", latest_command))
    application.run_polling()

if __name__ == "__main__":
    main()
