from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..config import settings
from ..models import User, Wallet, AuditLog
from . import wallet

ADMIN_ROLES = {"MODERATOR": 1, "ADMIN": 2, "SUPER_ADMIN": 3, "OWNER": 4}


async def get_or_create(s: AsyncSession, tg_user) -> User:
    u = await s.get(User, tg_user.id)
    if not u:
        u = User(id=tg_user.id, username=tg_user.username, first_name=tg_user.first_name or "")
        if tg_user.id in settings.owners:
            u.role, u.status = "OWNER", "ACTIVE"
        s.add(u)
        await s.flush()
        if u.status == "ACTIVE":
            await ensure_wallet(s, u)
    else:
        u.username = tg_user.username
        if tg_user.id in settings.owners and (u.role != "OWNER" or u.status != "ACTIVE"):
            u.role, u.status = "OWNER", "ACTIVE"  # OWNER_IDS always wins, even for accounts created earlier
            await ensure_wallet(s, u)
    return u


async def ensure_wallet(s: AsyncSession, u: User):
    if await s.get(Wallet, u.id) is None:
        s.add(Wallet(user_id=u.id, available=0))
        await s.flush()
    # idempotency key guarantees a single starting-balance credit ever
    try:
        async with s.begin_nested():
            await wallet.apply(s, u.id, "STARTING_BALANCE", settings.start_cash, "Welcome bonus", key=f"start:{u.id}")
    except wallet.DuplicateOperation:
        pass
    u.approved_at = u.approved_at or datetime.now(timezone.utc)


def has_role(u: User | None, minimum: str) -> bool:
    return bool(u) and ADMIN_ROLES.get(u.role, 0) >= ADMIN_ROLES[minimum]


async def audit(s: AsyncSession, admin_id: int, action: str, target: str = "", **details):
    s.add(AuditLog(admin_id=admin_id, action=action, target=target, details=details))


async def find_user(s: AsyncSession, ref: str) -> User | None:
    ref = ref.lstrip("@")
    if ref.isdigit():
        return await s.get(User, int(ref))
    return (await s.execute(select(User).where(User.username.ilike(ref)))).scalar_one_or_none()
