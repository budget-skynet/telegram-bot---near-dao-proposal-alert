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

# Well-known DAO contracts on NEAR mainnet
KNOWN_DAOS = {
    "sputnik-dao": "sputnikv2.testnet",
    "ref-finance": "ref-finance.sputnik-dao.near",
    "aurora": "aurora.sputnik-dao.near",
    "meta-pool": "meta-pool-dao.sputnik-dao.near",
    "near-foundation": "nearfoundation.sputnik-dao.near",
}

DEFAULT_DAO = "ref-finance.sputnik-dao.near"

# Proposal kind labels
PROPOSAL_KIND_LABELS = {
    "Transfer": "💸 Transfer",
    "AddMemberToRole": "➕ Add Member",
    "RemoveMemberFromRole": "➖ Remove Member",
    "FunctionCall": "⚙️ Function Call",
    "UpgradeSelf": "🔧 Upgrade Self",
    "UpgradeRemote": "🔧 Upgrade Remote",
    "SetStakingContract": "📌 Set Staking Contract",
    "AddBounty": "🏆 Add Bounty",
    "BountyDone": "✅ Bounty Done",
    "Vote": "🗳️ Vote",
    "ChangePolicy": "📜 Change Policy",
    "ChangeConfig": "⚙️ Change Config",
}

STATUS_EMOJI = {
    "InProgress": "🟡",
    "Approved": "✅",
    "Rejected": "❌",
    "Removed": "🗑️",
    "Expired": "⏰",
    "Moved": "➡️",
    "Failed": "💥",
}

# ── NEAR RPC Helper ───────────────────────────────────────────────────────────

async def _rpc(method: str, params: dict) -> dict:
    """Low-level async NEAR JSON-RPC call."""
    payload = {
        "jsonrpc": "2.0",
        "id": "dontcare",
        "method": method,
        "params": params,
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(
            NEAR_RPC,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            if "error" in data:
                raise ValueError(f"RPC error: {data['error']}")
            return data.get("result", {})


# ── NEAR Helper Functions ─────────────────────────────────────────────────────

async def _view_call(contract_id: str, method_name: str, args: dict) -> any:
    """Call a view method on a NEAR smart contract."""
    import json, base64

    args_base64 = base64.b64encode(json.dumps(args).encode()).decode()
    result = await _rpc(
        "query",
        {
            "request_type": "call_function",
            "finality": "final",
            "account_id": contract_id,
            "method_name": method_name,
            "args_base64": args_base64,
        },
    )
    raw = bytes(result["result"])
    return json.loads(raw.decode())


async def get_proposals(dao_contract: str, from_index: int = 0, limit: int = 10) -> list:
    """
    Fetch proposals from a Sputnik DAO contract.
    Returns a list of proposal objects.
    """
    proposals = await _view_call(
        dao_contract,
        "get_proposals",
        {"from_index": from_index, "limit": limit},
    )
    return proposals if isinstance(proposals, list) else []


async def get_proposal_count(dao_contract: str) -> int:
    """Return the total number of proposals in the DAO."""
    count = await _view_call(dao_contract, "get_proposal_count", {})
    return int(count)


async def get_dao_policy(dao_contract: str) -> dict:
    """Return the DAO policy (roles, quorum, vote period, etc.)."""
    policy = await _view_call(dao_contract, "get_policy", {})
    return policy if isinstance(policy, dict) else {}


async def get_active_proposals(dao_contract: str, max_fetch: int = 50) -> list:
    """
    Return only proposals with status 'InProgress' from the most recent batch.
    Fetches up to max_fetch proposals from the end of the list.
    """
    total = await get_proposal_count(dao_contract)
    if total == 0:
        return []
    from_index = max(0, total - max_fetch)
    limit = total - from_index
    proposals = await get_proposals(dao_contract, from_index=from_index, limit=limit)
    active = [p for p in proposals if p.get("status") == "InProgress"]
    return active


async def get_recent_proposals(dao_contract: str, limit: int = 5) -> list:
    """Return the most recent N proposals regardless of status."""
    total = await get_proposal_count(dao_contract)
    if total == 0:
        return []
    from_index = max(0, total - limit)
    actual_limit = total - from_index
    proposals = await get_proposals(dao_contract, from_index=from_index, limit=actual_limit)
    return list(reversed(proposals))  # newest first


# ── Formatting Helpers ────────────────────────────────────────────────────────

def _format_yocto(yocto_str: str) -> str:
    """Convert yoctoNEAR string to a human-readable NEAR amount."""
    try:
        yocto = int(yocto_str)
        near = yocto / 1e24
        return f"{near:,.4f} NEAR"
    except Exception:
        return yocto_str


def _short(text: str, max_len: int = 80) -> str:
    return text if len(text) <= max_len else text[:max_len] + "…"


def _kind_label(kind) -> str:
    if isinstance(kind, str):
        return PROPOSAL_KIND_LABELS.get(kind, kind)
    if isinstance(kind, dict):
        k = list(kind.keys())[0]
        label = PROPOSAL_KIND_LABELS.get(k, k)
        details = kind[k]
        if k == "Transfer" and isinstance(details, dict):
            receiver = details.get("receiver_id", "?")
            amount = _format_yocto(str(details.get("amount", 0)))
            token = details.get("token_id") or "NEAR"
            return f"{label} → {receiver}\n      Amount: {amount} ({token})"
        if k == "FunctionCall" and isinstance(details, dict):
            receiver = details.get("receiver_id", "?")
            actions = details.get("actions", [])
            methods = ", ".join(a.get("method_name", "?") for a in actions)
            return f"{label} on {receiver}\n      Methods: {methods}"
        return label
    return str(kind)


def _format_proposal(proposal: dict, index: int = None) -> str:
    """Format a single proposal into a nice Telegram message block."""
    pid = proposal.get("id", "?")
    proposer = proposal.get("proposer", "unknown")
    description = _short(proposal.get("description", "No description"), 120)
    status = proposal.get("status", "Unknown")
    status_icon = STATUS_EMOJI.get(status, "⚪")
    kind = proposal.get("kind", "Unknown")
    kind_str = _kind_label(kind)

    votes = proposal.get("votes", {})
    vote_counts = proposal.get("vote_counts", {})

    # Vote summary
    approve = votes.get("Approve", 0) if isinstance(votes, dict) else 0
    reject = votes.get("Reject", 0) if isinstance(votes, dict) else 0
    remove = votes.get("Remove", 0) if isinstance(votes, dict) else 0

    lines = [
        f"{'─'*36}",
        f"📋 *Proposal #{pid}*",
        f"👤 *Proposer:* `{proposer}`",
        f"📝 *Description:* {description}",
        f"🔖 *Kind:* {kind_str}",
        f"{status_icon} *Status:* {status}",
        f"🗳️ *Votes:* ✅ {approve}  ❌ {reject}  🗑️ {remove}",
    ]
    return "\n".join(lines)


def _resolve_dao(args: list) -> str:
    """Resolve DAO contract from user args or use default."""
    if args:
        candidate = args[0].lower()
        if candidate in KNOWN_DAOS:
            return KNOWN_DAOS[candidate]
        if ".near" in candidate or ".testnet" in candidate:
            return candidate
    return DEFAULT_DAO


# ── /start and /help ──────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome message with bot overview."""
    text = (
        "🌐 *NEAR DAO Proposal Alert Bot* 🚀\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Stay on top of every vote and proposal across NEAR DAOs!\n\n"
        "⚡ *Quick Commands:*\n"
        "  /proposals — Latest proposals (any DAO)\n"
        "  /active — Active (in-progress) proposals\n"
        "  /stats — DAO statistics & policy info\n"
        "  /daos — List known DAOs\n"
        "  /help — Full help & usage guide\n\n"
        "📌 *Default DAO:* `ref-finance.sputnik-dao.near`\n\n"
        "💡 Tip: Pass a DAO name or contract after any command:\n"
        "  `/proposals aurora` or\n"
        "  `/proposals aurora.sputnik-dao.near`\n\n"
        "🔗 Join the NEAR ecosystem → https://near.org"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Detailed help message."""
    text = (
        "📖 *NEAR DAO Proposal Alert Bot — Help*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "*Commands:*\n\n"
        "🔹 /start — Welcome & quick intro\n\n"
        "🔹 /proposals `[dao]` `[limit]`\n"
        "   Show the most recent proposals.\n"
        "   Example: `/proposals aurora 10`\n\n"
        "🔹 /active `[dao]`\n"
        "   Show only InProgress proposals.\n"
        "   Example: `/active meta-pool`\n\n"
        "🔹 /stats `[dao]`\n"
        "   DAO statistics: total proposals,\n"
        "   vote period, roles, bond required.\n"
        "   Example: `/stats ref-finance`\n\n"
        "🔹 /daos\n"
        "   List all known DAO shortcuts.\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "*Known DAO shortcuts:*\n"
        "  `sputnik-dao`, `ref-finance`,\n"
        "  `aurora`, `meta-pool`, `near-foundation`\n\n"
        "You can also pass any full `.sputnik-dao.near`\n"
        "contract address directly.\n\n"
        "🌐 Learn more: https://near.org/dao"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ── Command Handlers ──────────────────────────────────────────────────────────

async def proposals_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /proposals [dao] [limit]
    Show the most recent proposals from a DAO.
    """
    args = context.args or []

    # Parse optional limit (last arg if numeric)
    limit = 5
    if args and args[-1].isdigit():
        limit = min(int(args[-1]), 10)
        args = args[:-1]

    dao_contract = _resolve_dao(args)

    await update.message.reply_text(
        f"🔍 Fetching last *{limit}* proposals from\n`{dao_contract}` …",
        parse_mode="Markdown",
    )

    try:
        proposals = await get_recent_proposals(dao_contract, limit=limit)
        if not proposals:
            await update.message.reply_text(
                "📭 No proposals found for this DAO.", parse_mode="Markdown"
            )
            return

        header = (
            f"📋 *Recent Proposals*\n"
            f"🏛️ DAO: `{dao_contract}`\n"
            f"Total shown: *{len(proposals)}*\n"
        )
        await update.message.reply_text(header, parse_mode="Markdown")

        for proposal in proposals:
            msg = _format_proposal(proposal)
            await update.message.reply_text(msg, parse_mode="Markdown")

    except Exception as exc:
        logger.exception("proposals_command failed")
        await update.message.reply_text(
            f"❌ Error fetching proposals:\n`{exc}`\n\n"
            "Make sure the DAO contract is correct.",
            parse_mode="Markdown",
        )


async def active_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /active [dao]
    Show only proposals currently in-progress (open for voting).
    """
    args = context.args or []
    dao_contract = _resolve_dao(args)

    await update.message.reply_text(
        f"🟡 Fetching *active* proposals from\n`{dao_contract}` …",
        parse_mode="Markdown",
    )

    try:
        active = await get_active_proposals(dao_contract, max_fetch=50)

        if not active:
            await update.message.reply_text(
                f"✅ No active proposals found in `{dao_contract}`.\n"
                "All caught up!",
                parse_mode="Markdown",
            )
            return

        header = (
            f"🟡 *Active Proposals (Open for Voting)*\n"
            f"🏛️ DAO: `{dao_contract}`\n"
            f"Found: *{len(active)}* open proposals\n"
        )
        await update.message.reply_text(header, parse_mode="Markdown")

        for proposal in active[:8]:  # cap display at 8
            msg = _format_proposal(proposal)
            await update.message.reply_text(msg, parse_mode="Markdown")

        if len(active) > 8:
            await update.message.reply_text(
                f"⚠️ Showing first 8 of {len(active)} active proposals.\n"
                "Use `/proposals` for paginated access.",
                parse_mode="Markdown",
            )

    except Exception as exc:
        logger.exception("active_command failed")
        await update.message.reply_text(
            f"❌ Error fetching active proposals:\n`{exc}`",
            parse_mode="Markdown",
        )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /stats [dao]
    Show DAO statistics: proposal count, policy, roles.
    """
    args = context.args or []
    dao_contract = _resolve_dao(args)

    await update.message.reply_text(
        f"📊 Loading stats for\n`{dao_contract}` …",
        parse_mode="Markdown",
    )

    try:
        total, policy = await _gather_stats(dao_contract)

        # Vote period (nanoseconds → human)
        vote_period_ns = int(policy.get("proposal_period", 0))
        vote_period_days = vote_period_ns / 1e9 / 86400
        bond_str = _format_yocto(str(policy.get("proposal_bond", 0)))

        # Roles summary
        roles = policy.get("roles", [])
        role_lines = []
        for role in roles[:6]:
            name = role.get("name", "?")
            kind = role.get("kind", {})
            if isinstance(kind, dict) and "Group" in kind:
                members = kind["Group"]
                role_lines.append(f"  • *{name}* — {len(members)} member(s)")
            elif kind == "Everyone" or (isinstance(kind, str) and kind == "Everyone"):
                role_lines.append(f"  • *{name}* — Everyone")
            else:
                role_lines.append(f"  • *{name}* — {kind}")

        roles_text = "\n".join(role_lines) if role_lines else "  No roles found"

        # Default vote policy
        dvp = policy.get("default_vote_policy", {})
        threshold = dvp.get("threshold", "?")
        weight_kind = dvp.get("weight_kind", "?")

        text = (
            f"📊 *DAO Statistics*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏛️ *Contract:* `{dao_contract}`\n\n"
            f"📋 *Total Proposals:* {total}\n"
            f"⏳ *Vote Period:* {vote_period_days:.1f} days\n"
            f"💰 *Proposal Bond:* {bond_str}\n\n"
            f"🗳️ *Default Vote Policy:*\n"
            f"  Threshold: `{threshold}`\n"
            f"  Weight Kind: `{weight_kind}`\n\n"
            f"👥 *Roles ({len(roles)}):*\n{roles_text}\n\n"
            f"🔗 Explorer: https://explorer.near.org/accounts/{dao

def main() -> None:
    logging.basicConfig(level=logging.INFO)
    token = os.environ.get("BOT_TOKEN", "")
    application = ApplicationBuilder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("proposals", proposals_command))
    application.add_handler(CommandHandler("active", active_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.run_polling()

if __name__ == "__main__":
    main()
