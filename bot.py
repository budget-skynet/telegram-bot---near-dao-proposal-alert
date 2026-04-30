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
ASTRO_DAO_FACTORY = "sputnik-dao.near"
DEFAULT_DAO = "community.sputnik-dao.near"

# ── RPC Helper ────────────────────────────────────────────────────────────────
async def _rpc(method: str, params: dict) -> dict:
    """Generic NEAR RPC call. Returns the 'result' field or raises."""
    payload = {
        "jsonrpc": "2.0",
        "id": "dontcare",
        "method": method,
        "params": params,
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(NEAR_RPC, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            resp.raise_for_status()
            data = await resp.json()
            if "error" in data:
                raise ValueError(data["error"].get("message", "RPC error"))
            return data.get("result", {})


# ── NEAR Helper Functions ─────────────────────────────────────────────────────
async def get_proposals(dao_account: str, from_index: int = 0, limit: int = 10) -> list:
    """
    Fetch proposals from an AstroDAO (Sputnik v2) contract.
    Uses the `get_proposals` view method.
    """
    import json, base64

    args = {"from_index": from_index, "limit": limit}
    args_base64 = base64.b64encode(json.dumps(args).encode()).decode()

    result = await _rpc(
        "query",
        {
            "request_type": "call_function",
            "finality": "final",
            "account_id": dao_account,
            "method_name": "get_proposals",
            "args_base64": args_base64,
        },
    )
    raw = bytes(result["result"])
    return json.loads(raw.decode())


async def get_proposal(dao_account: str, proposal_id: int) -> dict:
    """Fetch a single proposal by ID from an AstroDAO contract."""
    import json, base64

    args = {"id": proposal_id}
    args_base64 = base64.b64encode(json.dumps(args).encode()).decode()

    result = await _rpc(
        "query",
        {
            "request_type": "call_function",
            "finality": "final",
            "account_id": dao_account,
            "method_name": "get_proposal",
            "args_base64": args_base64,
        },
    )
    raw = bytes(result["result"])
    return json.loads(raw.decode())


async def get_dao_policy(dao_account: str) -> dict:
    """Fetch the DAO policy (roles, quorum, thresholds)."""
    import json, base64

    args_base64 = base64.b64encode(b"{}").decode()
    result = await _rpc(
        "query",
        {
            "request_type": "call_function",
            "finality": "final",
            "account_id": dao_account,
            "method_name": "get_policy",
            "args_base64": args_base64,
        },
    )
    raw = bytes(result["result"])
    return json.loads(raw.decode())


async def get_last_proposal_id(dao_account: str) -> int:
    """Return the total number of proposals (== last proposal id)."""
    import json, base64

    args_base64 = base64.b64encode(b"{}").decode()
    result = await _rpc(
        "query",
        {
            "request_type": "call_function",
            "finality": "final",
            "account_id": dao_account,
            "method_name": "get_last_proposal_id",
            "args_base64": args_base64,
        },
    )
    raw = bytes(result["result"])
    return json.loads(raw.decode())


async def get_account_balance(account_id: str) -> dict:
    """Return the NEAR account balance (useful for DAO treasury checks)."""
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
def _format_proposal(p: dict, idx: int | None = None) -> str:
    """Return a nicely formatted proposal block (Markdown)."""
    pid = p.get("id", idx or "?")
    desc = p.get("description", "*(no description)*")
    kind = p.get("kind", {})
    kind_name = list(kind.keys())[0] if isinstance(kind, dict) and kind else str(kind)
    status = p.get("status", "Unknown")
    proposer = p.get("proposer", "Unknown")
    vote_counts = p.get("vote_counts", {})

    status_emoji = {
        "InProgress": "🟡",
        "Approved": "✅",
        "Rejected": "❌",
        "Removed": "🗑️",
        "Expired": "⏰",
        "Moved": "📦",
        "Failed": "💥",
    }.get(status, "❓")

    votes_line = ""
    if vote_counts:
        parts = []
        for role, counts in vote_counts.items():
            yes = counts[0] if len(counts) > 0 else 0
            no = counts[1] if len(counts) > 1 else 0
            abstain = counts[2] if len(counts) > 2 else 0
            parts.append(f"`{role}` ✅{yes} ❌{no} ➖{abstain}")
        votes_line = "\n🗳 *Votes:* " + " | ".join(parts)

    # Truncate long descriptions
    if len(desc) > 200:
        desc = desc[:197] + "…"

    return (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📋 *Proposal #{pid}*\n"
        f"📝 {desc}\n"
        f"🔖 *Type:* `{kind_name}`\n"
        f"👤 *Proposer:* `{proposer}`\n"
        f"{status_emoji} *Status:* `{status}`"
        f"{votes_line}\n"
    )


def _yocto_to_near(yocto: str) -> str:
    """Convert yoctoNEAR string to a human-readable NEAR amount."""
    try:
        val = int(yocto) / 1e24
        return f"{val:,.4f} NEAR"
    except Exception:
        return yocto


# ── /start and /help ──────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome message."""
    text = (
        "👋 *Welcome to the NEAR DAO Proposal Alert Bot!*\n\n"
        "Stay informed about governance proposals across NEAR AstroDAO DAOs.\n\n"
        "📡 *Available Commands:*\n"
        "▸ /proposals `[dao]` — List latest 5 proposals\n"
        "▸ /proposal `[dao]` `[id]` — View a specific proposal\n"
        "▸ /policy `[dao]` — View DAO voting policy\n"
        "▸ /treasury `[dao]` — Check DAO treasury balance\n"
        "▸ /latest `[dao]` — Get the latest proposal only\n"
        "▸ /help — Show this help message\n\n"
        "💡 *Default DAO:* `community.sputnik-dao.near`\n"
        "You can pass any Sputnik v2 DAO account as an argument.\n\n"
        "🌐 Powered by [NEAR Protocol](https://near.org)"
    )
    await update.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=True)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Help message — same as start."""
    await start(update, context)


# ── Command Handlers ──────────────────────────────────────────────────────────
async def proposals(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /proposals [dao_account]
    Lists the 5 most recent proposals of the given (or default) DAO.
    """
    dao = context.args[0] if context.args else DEFAULT_DAO
    await update.message.reply_text(f"🔍 Fetching proposals from `{dao}` …", parse_mode="Markdown")

    try:
        last_id = await get_last_proposal_id(dao)
        from_index = max(0, last_id - 5)
        props = await get_proposals(dao, from_index=from_index, limit=5)
    except Exception as exc:
        logger.exception("proposals error")
        await update.message.reply_text(f"❌ Error fetching proposals:\n`{exc}`", parse_mode="Markdown")
        return

    if not props:
        await update.message.reply_text("ℹ️ No proposals found for this DAO.")
        return

    header = f"📊 *Latest Proposals — `{dao}`*\nTotal proposals: *{last_id}*\n\n"
    body = "\n".join(_format_proposal(p) for p in reversed(props))
    full = header + body

    # Telegram max message length is 4096
    for chunk_start in range(0, len(full), 4000):
        await update.message.reply_text(full[chunk_start:chunk_start + 4000], parse_mode="Markdown")


async def proposal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /proposal [dao_account] [proposal_id]
    Shows details of a single proposal.
    """
    if len(context.args) < 2:
        await update.message.reply_text(
            "⚠️ Usage: `/proposal <dao_account> <proposal_id>`\n"
            "Example: `/proposal community.sputnik-dao.near 42`",
            parse_mode="Markdown",
        )
        return

    dao = context.args[0]
    try:
        pid = int(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Proposal ID must be a number.", parse_mode="Markdown")
        return

    await update.message.reply_text(f"🔍 Fetching proposal #{pid} from `{dao}` …", parse_mode="Markdown")

    try:
        p = await get_proposal(dao, pid)
    except Exception as exc:
        logger.exception("proposal error")
        await update.message.reply_text(f"❌ Error: `{exc}`", parse_mode="Markdown")
        return

    text = f"📊 *Proposal Details — `{dao}`*\n\n" + _format_proposal(p)

    # Show extra kind details
    kind = p.get("kind", {})
    if isinstance(kind, dict):
        kind_key = list(kind.keys())[0] if kind else None
        if kind_key == "Transfer":
            t = kind["Transfer"]
            token = t.get("token_id") or "NEAR"
            amount = _yocto_to_near(t.get("amount", "0")) if token == "NEAR" else t.get("amount", "0")
            receiver = t.get("receiver_id", "?")
            text += f"\n💸 *Transfer:* {amount} → `{receiver}`\n"
        elif kind_key == "AddMemberToRole":
            m = kind["AddMemberToRole"]
            text += f"\n👥 *Add Member:* `{m.get('member_id')}` → role `{m.get('role')}`\n"
        elif kind_key == "RemoveMemberFromRole":
            m = kind["RemoveMemberFromRole"]
            text += f"\n🚫 *Remove Member:* `{m.get('member_id')}` from role `{m.get('role')}`\n"

    submission_time_ns = p.get("submission_time")
    if submission_time_ns:
        try:
            import datetime
            ts = int(submission_time_ns) / 1e9
            dt = datetime.datetime.utcfromtimestamp(ts).strftime("%Y-%m-%d %H:%M UTC")
            text += f"🕐 *Submitted:* {dt}\n"
        except Exception:
            pass

    await update.message.reply_text(text, parse_mode="Markdown")


async def policy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /policy [dao_account]
    Shows the DAO voting policy and roles.
    """
    dao = context.args[0] if context.args else DEFAULT_DAO
    await update.message.reply_text(f"🔍 Fetching policy for `{dao}` …", parse_mode="Markdown")

    try:
        pol = await get_dao_policy(dao)
    except Exception as exc:
        logger.exception("policy error")
        await update.message.reply_text(f"❌ Error: `{exc}`", parse_mode="Markdown")
        return

    roles = pol.get("roles", [])
    proposal_bond = _yocto_to_near(pol.get("proposal_bond", "0"))
    proposal_period_ns = pol.get("proposal_period", "0")

    try:
        days = int(proposal_period_ns) / (1e9 * 86400)
        period_str = f"{days:.1f} days"
    except Exception:
        period_str = str(proposal_period_ns)

    lines = [
        f"🏛 *DAO Policy — `{dao}`*\n",
        f"💰 *Proposal Bond:* {proposal_bond}",
        f"⏳ *Proposal Period:* {period_str}",
        f"👥 *Roles ({len(roles)}):*",
    ]

    for role in roles:
        name = role.get("name", "?")
        kind = role.get("kind", {})
        if "Everyone" in kind:
            members_info = "Everyone"
        elif "Member" in kind:
            members_info = f"{len(kind['Member'])} members"
        else:
            members_info = str(kind)

        permissions = role.get("vote_policy", {})
        perm_count = len(permissions)
        lines.append(f"  • `{name}` — {members_info} | {perm_count} vote policies")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def treasury(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /treasury [dao_account]
    Shows the DAO account's NEAR balance (treasury).
    """
    dao = context.args[0] if context.args else DEFAULT_DAO
    await update.message.reply_text(f"🔍 Checking treasury for `{dao}` …", parse_mode="Markdown")

    try:
        acct = await get_account_balance(dao)
    except Exception as exc:
        logger.exception("treasury error")
        await update.message.reply_text(f"❌ Error: `{exc}`", parse_mode="Markdown")
        return

    total = _yocto_to_near(acct.get("amount", "0"))
    locked = _yocto_to_near(acct.get("locked", "0"))
    storage_bytes = acct.get("storage_usage", 0)

    text = (
        f"💎 *Treasury — `{dao}`*\n\n"
        f"💰 *Total Balance:* {total}\n"
        f"🔒 *Locked (staked):* {locked}\n"
        f"💾 *Storage Used:* {storage_bytes:,} bytes\n\n"
        f"🔗 [View on NEAR Explorer](https://explorer.near.org/accounts/{dao})"
    )
    await update.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=True)


async def latest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /latest [dao_account]
    Shows only the single most recent proposal.
    """
    dao = context.args[0] if context.args else DEFAULT_DAO
    await update.message.reply_text(f"🔍 Fetching latest proposal from `{dao}` …", parse_mode="Markdown")

    try:
        last_id = await get_last_proposal_id(dao)
        if last_id == 0:
            await update.message.reply_text("ℹ️ This DAO has no proposals yet.")
            return
        p = await get_proposal(dao, last_id - 1)
    except Exception as exc:
        logger.exception("latest error")
        await update.message.reply_text(f"❌ Error: `{exc}`", parse_mode="Markdown")
        return

    text = (
        f"🆕 *Latest Proposal — `{dao}`*\n"
        f"📊 Total proposals in DAO: *{last_id}*\n\n"
        + _format_proposal(p)
        + f"\n🔗 [View on AstroDAO](https://app.astrodao.com/dao/{dao}/proposals/{p.get('id', last_id - 1)})"
    )
    await update.message.reply_text(text, parse_mode="Markdown", disable_web_page_preview=True)


# ── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not TOKEN:
        raise RuntimeError("Set the TELEGRAM_BOT_TOKEN environment variable.")

    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("proposals", proposals))
    app.add_handler(CommandHandler("proposal", proposal))
    app.add_handler(CommandHandler("policy", policy))
    app.add_handler(CommandHandler("treasury", treasury))
    app.add_handler(

def main() -> None:
    logging.basicConfig(level=logging.INFO)
    token = os.environ.get("BOT_TOKEN", "")
    application = ApplicationBuilder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("proposals", proposals))
    application.add_handler(CommandHandler("proposal", proposal))
    application.add_handler(CommandHandler("policy", policy))
    application.add_handler(CommandHandler("treasury", treasury))
    application.add_handler(CommandHandler("latest", latest))
    application.run_polling()

if __name__ == "__main__":
    main()
