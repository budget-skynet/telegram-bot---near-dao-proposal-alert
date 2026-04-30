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

# ── Config ───────────────────────────────────────────────────────────────────
NEAR_RPC = "https://rpc.mainnet.near.org"
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# Known NEAR DAO contract addresses (Sputnik V2 style)
DEFAULT_DAO = "community.sputnik-dao.near"
KNOWN_DAOS = [
    "community.sputnik-dao.near",
    "genesis.sputnik-dao.near",
    "developers.sputnik-dao.near",
    "metapool.sputnik-dao.near",
    "nearweek.sputnik-dao.near",
]

# ── NEAR RPC Helper ───────────────────────────────────────────────────────────
async def _rpc(method: str, params: dict) -> dict:
    """Generic NEAR JSON-RPC helper. Returns the 'result' field or raises."""
    payload = {
        "jsonrpc": "2.0",
        "id": "dao-bot",
        "method": method,
        "params": params,
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(
            NEAR_RPC,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            data = await resp.json()
    if "error" in data:
        raise RuntimeError(data["error"].get("message", "RPC error"))
    return data.get("result", {})


# ── NEAR Helper Functions ─────────────────────────────────────────────────────
async def get_proposals(dao_account: str, from_index: int = 0, limit: int = 10) -> list:
    """
    Fetch proposals from a Sputnik-V2 DAO contract via view call.
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


async def get_proposal_by_id(dao_account: str, proposal_id: int) -> dict:
    """Fetch a single proposal by its numeric ID."""
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
    proposal = json.loads(raw.decode())
    return proposal


async def get_dao_policy(dao_account: str) -> dict:
    """Fetch DAO policy (roles, vote thresholds, etc.)."""
    import json, base64

    args_b64 = base64.b64encode(b"{}").decode()
    result = await _rpc(
        "query",
        {
            "request_type": "call_function",
            "finality": "final",
            "account_id": dao_account,
            "method_name": "get_policy",
            "args_base64": args_b64,
        },
    )
    raw = bytes(result["result"])
    return json.loads(raw.decode())


async def get_account_balance(account_id: str) -> dict:
    """Return NEAR account balance info."""
    result = await _rpc(
        "query",
        {
            "request_type": "view_account",
            "finality": "final",
            "account_id": account_id,
        },
    )
    return result


async def get_last_block_info() -> dict:
    """Return latest block/network status."""
    result = await _rpc("status", {})
    return result


# ── Formatting Helpers ────────────────────────────────────────────────────────
def _yocto_to_near(yocto: str) -> str:
    """Convert yoctoNEAR string to a human-readable NEAR amount."""
    try:
        val = int(yocto) / 10**24
        return f"{val:,.4f} NEAR"
    except Exception:
        return yocto


def _fmt_proposal(p: dict, index: int | None = None) -> str:
    """Format a single proposal dict into a pretty Markdown string."""
    pid = p.get("id", index)
    desc = p.get("description", "—")
    status = p.get("status", "Unknown")
    kind = p.get("kind", {})
    proposer = p.get("proposer", "unknown")
    submission = p.get("submission_time", "")

    # Summarise kind
    if isinstance(kind, dict):
        kind_name = next(iter(kind), "Unknown")
        kind_detail = kind.get(kind_name, {})
        if kind_name == "Transfer":
            amount = _yocto_to_near(str(kind_detail.get("amount", 0)))
            receiver = kind_detail.get("receiver_id", "?")
            kind_str = f"💸 Transfer {amount} → `{receiver}`"
        elif kind_name == "AddMemberToRole":
            member = kind_detail.get("member_id", "?")
            role = kind_detail.get("role", "?")
            kind_str = f"👤 Add `{member}` to role *{role}*"
        elif kind_name == "RemoveMemberFromRole":
            member = kind_detail.get("member_id", "?")
            role = kind_detail.get("role", "?")
            kind_str = f"🚫 Remove `{member}` from role *{role}*"
        elif kind_name == "FunctionCall":
            contract = kind_detail.get("receiver_id", "?")
            kind_str = f"⚙️ FunctionCall on `{contract}`"
        elif kind_name == "ChangePolicy":
            kind_str = "📜 Change Policy"
        elif kind_name == "UpgradeSelf":
            kind_str = "🔧 Upgrade Self"
        elif kind_name == "Vote":
            kind_str = "🗳️ Vote"
        else:
            kind_str = f"🔹 {kind_name}"
    else:
        kind_str = str(kind)

    # Vote counts
    vote_counts = p.get("vote_counts", {})
    votes_str = ""
    for role, counts in vote_counts.items():
        approve = counts[0] if len(counts) > 0 else 0
        reject = counts[1] if len(counts) > 1 else 0
        remove = counts[2] if len(counts) > 2 else 0
        votes_str += f"  • {role}: ✅{approve} ❌{reject} 🗑️{remove}\n"

    status_emoji = {
        "InProgress": "🟡",
        "Approved": "✅",
        "Rejected": "❌",
        "Removed": "🗑️",
        "Expired": "⏰",
        "Moved": "➡️",
        "Failed": "💀",
    }.get(status, "⬜")

    lines = [
        f"*Proposal #{pid}*",
        f"  {kind_str}",
        f"  📝 {desc[:120]}{'…' if len(desc) > 120 else ''}",
        f"  👤 Proposer: `{proposer}`",
        f"  {status_emoji} Status: *{status}*",
    ]
    if votes_str:
        lines.append(f"  🗳️ Votes:\n{votes_str.rstrip()}")
    return "\n".join(lines)


# ── /start and /help ──────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome message."""
    text = (
        "🌐 *NEAR DAO Proposal Alert Bot*\n\n"
        "Stay on top of every proposal across Sputnik-V2 DAOs on NEAR Protocol.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🚀 *Quick Start*\n"
        "  /proposals — Latest proposals from the default DAO\n"
        "  /proposal `<dao>` `<id>` — Single proposal detail\n"
        "  /daos — List tracked DAOs\n"
        "  /policy `<dao>` — DAO voting policy\n"
        "  /network — NEAR network status\n"
        "  /help — Full command reference\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Example:\n"
        "`/proposals community.sputnik-dao.near`\n"
        "`/proposal community.sputnik-dao.near 42`\n\n"
        "_Powered by NEAR RPC • Sputnik V2 DAOs_"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Detailed help."""
    text = (
        "📖 *Command Reference*\n\n"
        "*/proposals* `[dao_account]` `[limit]`\n"
        "  Fetch the latest DAO proposals.\n"
        "  Default DAO: `community.sputnik-dao.near`\n"
        "  Default limit: 5 (max 10)\n\n"
        "*/proposal* `<dao_account>` `<proposal_id>`\n"
        "  Detailed view of a single proposal by numeric ID.\n\n"
        "*/daos*\n"
        "  List all pre-tracked NEAR DAOs.\n\n"
        "*/policy* `<dao_account>`\n"
        "  Show the DAO's voting policy (roles & thresholds).\n\n"
        "*/network*\n"
        "  NEAR network status, latest block & chain ID.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "*Tips*\n"
        "• Any Sputnik-V2 DAO account works — just pass it as the first argument.\n"
        "• Proposal IDs start at 0.\n"
        "• Status legend: 🟡 InProgress ✅ Approved ❌ Rejected ⏰ Expired\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ── Command Handlers ──────────────────────────────────────────────────────────
async def proposals_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /proposals [dao_account] [limit]
    Fetch and display recent proposals from a Sputnik-V2 DAO.
    """
    args = context.args or []
    dao = args[0] if len(args) >= 1 else DEFAULT_DAO
    try:
        limit = max(1, min(int(args[1]), 10)) if len(args) >= 2 else 5
    except ValueError:
        limit = 5

    await update.message.reply_text(
        f"🔍 Fetching last *{limit}* proposals from\n`{dao}`…",
        parse_mode="Markdown",
    )

    try:
        proposals = await get_proposals(dao, from_index=0, limit=limit)
    except Exception as exc:
        logger.exception("proposals_command error")
        await update.message.reply_text(
            f"❌ Could not fetch proposals:\n`{exc}`", parse_mode="Markdown"
        )
        return

    if not proposals:
        await update.message.reply_text("ℹ️ No proposals found for this DAO.")
        return

    # Show newest first
    proposals = list(reversed(proposals))

    header = f"📋 *Latest Proposals — {dao}*\n{'━'*32}\n\n"
    chunks = [header]
    for p in proposals:
        block = _fmt_proposal(p) + "\n\n"
        chunks.append(block)

    # Telegram message limit ~4096 chars; split if needed
    message = "".join(chunks)
    if len(message) <= 4096:
        await update.message.reply_text(message, parse_mode="Markdown")
    else:
        # Send header + one proposal per message
        await update.message.reply_text(header, parse_mode="Markdown")
        for p in proposals:
            try:
                await update.message.reply_text(
                    _fmt_proposal(p), parse_mode="Markdown"
                )
            except Exception:
                pass


async def proposal_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /proposal <dao_account> <proposal_id>
    Show a single proposal in full detail.
    """
    args = context.args or []
    if len(args) < 2:
        await update.message.reply_text(
            "⚠️ Usage: `/proposal <dao_account> <proposal_id>`\n"
            "Example: `/proposal community.sputnik-dao.near 0`",
            parse_mode="Markdown",
        )
        return

    dao = args[0]
    try:
        pid = int(args[1])
    except ValueError:
        await update.message.reply_text("❌ Proposal ID must be a number.")
        return

    await update.message.reply_text(
        f"🔍 Fetching proposal *#{pid}* from `{dao}`…", parse_mode="Markdown"
    )

    try:
        proposal = await get_proposal_by_id(dao, pid)
    except Exception as exc:
        logger.exception("proposal_command error")
        await update.message.reply_text(
            f"❌ Error: `{exc}`", parse_mode="Markdown"
        )
        return

    text = (
        f"📄 *Proposal Detail — {dao}*\n{'━'*32}\n\n"
        + _fmt_proposal(proposal)
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def daos_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /daos
    List all pre-tracked NEAR DAOs with treasury balance.
    """
    await update.message.reply_text(
        "🏛️ Fetching balances for tracked DAOs…", parse_mode="Markdown"
    )

    lines = [f"🏛️ *Tracked NEAR DAOs*\n{'━'*32}\n"]
    for dao in KNOWN_DAOS:
        try:
            info = await get_account_balance(dao)
            balance = _yocto_to_near(info.get("amount", "0"))
            lines.append(f"• `{dao}`\n  💰 Treasury: *{balance}*\n")
        except Exception as exc:
            lines.append(f"• `{dao}`\n  ⚠️ _Unavailable_ (`{exc}`)\n")

    lines.append(
        "\n_Tip: Pass any DAO account to /proposals or /proposal_"
    )
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def policy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /policy <dao_account>
    Display the DAO's voting policy.
    """
    args = context.args or []
    dao = args[0] if args else DEFAULT_DAO

    await update.message.reply_text(
        f"📜 Fetching policy for `{dao}`…", parse_mode="Markdown"
    )

    try:
        policy = await get_dao_policy(dao)
    except Exception as exc:
        logger.exception("policy_command error")
        await update.message.reply_text(
            f"❌ Error: `{exc}`", parse_mode="Markdown"
        )
        return

    roles = policy.get("roles", [])
    default_vote_policy = policy.get("default_vote_policy", {})
    proposal_bond = _yocto_to_near(str(policy.get("proposal_bond", 0)))
    proposal_period = policy.get("proposal_period", "—")
    bounty_bond = _yocto_to_near(str(policy.get("bounty_bond", 0)))

    # Convert nanoseconds to days
    def ns_to_days(ns):
        try:
            return f"{int(ns) / 86_400_000_000_000:.1f} days"
        except Exception:
            return str(ns)

    lines = [
        f"📜 *DAO Policy — {dao}*",
        f"{'━'*32}",
        f"  💎 Proposal Bond: *{proposal_bond}*",
        f"  ⏱️ Proposal Period: *{ns_to_days(proposal_period)}*",
        f"  🏷️ Bounty Bond: *{bounty_bond}*",
        "",
        f"👥 *Roles ({len(roles)})*",
    ]

    for role in roles:
        name = role.get("name", "?")
        kind = role.get("kind", {})
        permissions = role.get("permissions", [])
        vote_policy = role.get("vote_policy", {})

        if isinstance(kind, dict) and "Group" in kind:
            members = kind["Group"]
            kind_str = f"Group ({len(members)} members)"
        elif kind == "Everyone":
            kind_str = "Everyone"
        else:
            kind_str = str(kind)

        lines.append(f"\n  🔹 *{name}* — {kind_str}")
        lines.append(f"    Permissions: {len(permissions)} rule(s)")
        if vote_policy:
            for action, vp in list(vote_policy.items())[:3]:
                weight = vp.get("weight_kind", "")
                threshold = vp.get("threshold", "")
                lines.append(f"    • {action}: {weight} @ {threshold}")

def main() -> None:
    logging.basicConfig(level=logging.INFO)
    token = os.environ.get("BOT_TOKEN", "")
    application = ApplicationBuilder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("proposals", proposals_command))
    application.add_handler(CommandHandler("proposal", proposal_command))
    application.add_handler(CommandHandler("daos", daos_command))
    application.add_handler(CommandHandler("policy", policy_command))
    application.run_polling()

if __name__ == "__main__":
    main()
