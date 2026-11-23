import random, re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_FLOOR
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from ..config import settings
from ..models import Company, CompanyUpgrade, Ipo, IpoSubscription, Sector, ShareOwnership, User
from . import wallet

P4 = Decimal("0.0001")
C2 = Decimal("0.01")


class GameError(Exception): ...


def _aware(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


# key: (name, cost, cooldown_hours, reputation gain, growth gain, failure risk)
UPGRADES = {
    "RND": ("Research & Development", 150_000, 6, 4, 0.6, 0.15),
    "MARKETING": ("Marketing Campaign", 80_000, 4, 3, 0.4, 0.10),
    "PRODUCT": ("Product Innovation", 200_000, 8, 5, 0.8, 0.20),
    "HIRING": ("Employee Hiring", 60_000, 3, 2, 0.3, 0.05),
    "INFRA": ("Infrastructure Upgrade", 120_000, 6, 3, 0.5, 0.10),
    "PRODUCTION": ("Production Expansion", 180_000, 8, 3, 0.7, 0.15),
    "BRANCH": ("New Branch", 250_000, 12, 4, 0.9, 0.20),
    "TECH": ("Technology Upgrade", 160_000, 8, 4, 0.6, 0.15),
    "BRAND": ("Brand Development", 100_000, 6, 5, 0.3, 0.10),
}


async def _user(s, uid):
    u = await s.get(User, uid)
    if not u or u.status != "ACTIVE":
        raise GameError("Account not active")
    return u


async def create_company(s: AsyncSession, uid: int, name: str, ticker: str, sector_id: int, description: str,
                         capital: Decimal, total_shares: int, key: str) -> Company:
    await _user(s, uid)
    name, ticker = name.strip(), ticker.strip().upper()
    if not 3 <= len(name) <= 40 or not re.fullmatch(r"[A-Z]{3,5}", ticker):
        raise GameError("Name 3-40 chars, ticker 3-5 letters")
    if capital < settings.min_capital:
        raise GameError(f"Minimum capital {settings.min_capital}")
    if not 10_000 <= total_shares <= 10_000_000:
        raise GameError("Total shares must be 10,000 – 10,000,000")
    price = (capital / total_shares).quantize(P4)
    if price < 1:
        raise GameError("Initial share price would be below ₹1 — reduce share count")
    if not await s.get(Sector, sector_id):
        raise GameError("Unknown sector")
    n = (await s.execute(select(func.count()).select_from(Company).where(Company.owner_id == uid))).scalar_one()
    if n >= settings.max_companies_per_player:
        raise GameError(f"Max {settings.max_companies_per_player} companies per player")
    dup = (await s.execute(select(Company.id).where((func.lower(Company.name) == name.lower()) | (Company.ticker == ticker)))).first()
    if dup:
        raise GameError("Name or ticker already taken")
    await wallet.apply(s, uid, "COMPANY_CREATION", -settings.company_fee, f"Creation fee {ticker}", key=f"{key}:fee")
    await wallet.apply(s, uid, "COMPANY_CREATION", -capital, f"Initial capital {ticker}", key=f"{key}:cap")
    c = Company(name=name, ticker=ticker, sector_id=sector_id, description=description[:500], ceo="Founder", owner_id=uid,
                total_shares=total_shares, price=price, prev_close=price, cash=capital, revenue=(capital * Decimal("0.10")).quantize(C2), reputation=40, growth_rate=2.0,
                volatility=0.012, listing="PRIVATE")
    s.add(c)
    await s.flush()
    s.add(ShareOwnership(user_id=uid, company_id=c.id, quantity=total_shares, avg_price=price))
    return c


async def _own_company(s, uid, cid) -> Company:
    c = (await s.execute(select(Company).where(Company.id == cid).with_for_update())).scalar_one_or_none()
    if not c or c.owner_id != uid:
        raise GameError("Not your company")
    return c


async def upgrade_company(s: AsyncSession, uid: int, cid: int, kind: str, key: str) -> dict:
    await _user(s, uid)
    if kind not in UPGRADES:
        raise GameError("Unknown upgrade")
    c = await _own_company(s, uid, cid)
    if c.status in ("SUSPENDED", "BANKRUPT"):
        raise GameError(f"Company is {c.status}")
    name, cost, cd, rep, growth, risk = UPGRADES[kind]
    last = (await s.execute(select(CompanyUpgrade).where(CompanyUpgrade.company_id == cid, CompanyUpgrade.kind == kind)
                            .order_by(CompanyUpgrade.id.desc()).limit(1))).scalar_one_or_none()
    if last and datetime.now(timezone.utc) < _aware(last.created_at) + timedelta(hours=cd):
        raise GameError(f"{name} on cooldown ({cd}h)")
    cnt = (await s.execute(select(func.count()).select_from(CompanyUpgrade).where(CompanyUpgrade.company_id == cid))).scalar_one()
    await wallet.apply(s, uid, "COMPANY_UPGRADE", -Decimal(cost), f"{name} {c.ticker}", key=f"{key}:up")
    ok = random.Random(f"{settings.seed}:{cid}:{kind}:{cnt}").random() >= risk
    eff = max(0.1, 1.2 - c.reputation / 100) * (1 if ok else 0.25)  # diminishing returns, failures give little
    c.reputation = min(100, c.reputation + max(0, round(rep * eff)))
    c.growth_rate = min(15.0, c.growth_rate + growth * eff)
    c.price = (c.price * Decimal(str(1 + growth * eff / 100))).quantize(P4)  # private valuation creeps up slowly
    c.revenue += Decimal(cost) * Decimal("0.3") * Decimal(str(eff))
    s.add(CompanyUpgrade(company_id=cid, kind=kind, cost=Decimal(cost), success=ok))
    return {"success": ok, "reputation": c.reputation, "growth": round(c.growth_rate, 2), "price": str(c.price)}


async def launch_ipo(s: AsyncSession, uid: int, cid: int, public_shares: int, price: Decimal, duration_hours: int,
                     min_sub: int, max_sub: int | None, key: str) -> Ipo:
    await _user(s, uid)
    c = await _own_company(s, uid, cid)
    if c.listing != "PRIVATE" or c.status != "ACTIVE":
        raise GameError("Company not eligible (already listed or not active)")
    if (await s.execute(select(Ipo.id).where(Ipo.company_id == cid, Ipo.status.in_(["PENDING", "OPEN"])))).first():
        raise GameError("An IPO is already running")
    age = datetime.now(timezone.utc) - _aware(c.created_at)
    if age < timedelta(hours=settings.ipo_min_age_hours):
        raise GameError(f"Company must be {settings.ipo_min_age_hours}h old")
    if c.reputation < settings.ipo_min_reputation:
        raise GameError(f"Reputation must be ≥ {settings.ipo_min_reputation} (now {c.reputation})")
    price = Decimal(price).quantize(P4)
    if not (c.price * Decimal("0.5") <= price <= c.price * 3):
        raise GameError(f"IPO price must be within 0.5x–3x of {c.price}")
    if price * c.total_shares < settings.ipo_min_valuation:
        raise GameError(f"Valuation at IPO price must be ≥ {settings.ipo_min_valuation}")
    if not 1 <= duration_hours <= 168:
        raise GameError("Duration 1–168 hours")
    if not 1 <= public_shares <= int(c.total_shares * settings.ipo_max_public_pct):
        raise GameError(f"Public shares max {int(settings.ipo_max_public_pct * 100)}% of supply")
    max_sub = max_sub or max(1, public_shares // 5)
    if not 1 <= min_sub <= max_sub <= public_shares:
        raise GameError("Invalid min/max subscription")
    await wallet.apply(s, uid, "TRADING_FEE", -settings.ipo_fee, f"IPO security fee {c.ticker}", key=f"{key}:ipofee")
    pending = bool(settings.ipo_requires_approval)
    now_ = datetime.now(timezone.utc)
    ipo = Ipo(company_id=cid, price=price, public_shares=public_shares, min_sub=min_sub, max_sub=max_sub,
              duration_hours=duration_hours, status="PENDING" if pending else "OPEN",
              opens_at=None if pending else now_, closes_at=None if pending else now_ + timedelta(hours=duration_hours))
    s.add(ipo)
    await s.flush()
    return ipo


async def decide_ipo(s: AsyncSession, ipo_id: int, approve: bool) -> Ipo:
    ipo = (await s.execute(select(Ipo).where(Ipo.id == ipo_id).with_for_update())).scalar_one_or_none()
    if not ipo or ipo.status != "PENDING":
        raise GameError("IPO not pending")
    c = await s.get(Company, ipo.company_id)
    if approve:
        ipo.status, ipo.opens_at = "OPEN", datetime.now(timezone.utc)
        ipo.closes_at = ipo.opens_at + timedelta(hours=ipo.duration_hours)
    else:
        ipo.status = "REJECTED"
        await wallet.apply(s, c.owner_id, "TRADING_FEE", settings.ipo_fee, f"IPO fee refund {c.ticker}", key=f"ipo{ipo.id}:feerefund")
    return ipo


async def subscribe(s: AsyncSession, uid: int, ipo_id: int, shares: int, key: str) -> IpoSubscription:
    await _user(s, uid)
    ipo = (await s.execute(select(Ipo).where(Ipo.id == ipo_id).with_for_update())).scalar_one_or_none()
    if not ipo or ipo.status != "OPEN" or _aware(ipo.closes_at) <= datetime.now(timezone.utc):
        raise GameError("IPO is not open")
    c = await s.get(Company, ipo.company_id)
    if c.owner_id == uid:
        raise GameError("Founders cannot subscribe to their own IPO")
    if not ipo.min_sub <= shares <= ipo.max_sub:
        raise GameError(f"Subscribe between {ipo.min_sub} and {ipo.max_sub} shares")
    if (await s.execute(select(IpoSubscription.id).where(IpoSubscription.ipo_id == ipo_id, IpoSubscription.user_id == uid))).first():
        raise GameError("You already subscribed")
    cost = (ipo.price * shares).quantize(Decimal("0.01"))
    await wallet.apply(s, uid, "IPO_PURCHASE", -cost, f"IPO {c.ticker} x{shares}", key=f"{key}:sub")
    sub = IpoSubscription(ipo_id=ipo_id, user_id=uid, shares=shares, paid=cost)
    s.add(sub)
    await s.flush()
    return sub


async def close_ipo(s: AsyncSession, ipo_id: int) -> dict | None:
    """Idempotent: status flips OPEN->CLOSED/FAILED exactly once under a row lock; refunds use unique keys."""
    ipo = (await s.execute(select(Ipo).where(Ipo.id == ipo_id).with_for_update())).scalar_one_or_none()
    if not ipo or ipo.status != "OPEN":
        return None
    c = (await s.execute(select(Company).where(Company.id == ipo.company_id).with_for_update())).scalar_one()
    subs = (await s.execute(select(IpoSubscription).where(IpoSubscription.ipo_id == ipo_id).order_by(IpoSubscription.id))).scalars().all()
    total_req = sum(x.shares for x in subs)
    if total_req == 0:
        ipo.status = "FAILED"
        return {"ipo": ipo, "company": c, "allocated": 0, "raised": Decimal(0), "subs": 0}
    if total_req <= ipo.public_shares:
        for x in subs: x.allocated = x.shares
    else:  # oversubscribed: pro-rata, remainder to earliest subscribers
        for x in subs:
            x.allocated = int((Decimal(x.shares) * ipo.public_shares / total_req).to_integral_value(ROUND_FLOOR))
        left = ipo.public_shares - sum(x.allocated for x in subs)
        for x in subs:
            if left <= 0: break
            if x.allocated < x.shares:
                x.allocated += 1; left -= 1
    allocated = sum(x.allocated for x in subs)
    founder = (await s.execute(select(ShareOwnership).where(ShareOwnership.user_id == c.owner_id, ShareOwnership.company_id == c.id)
                               .with_for_update())).scalar_one()
    if founder.quantity < allocated:
        raise GameError("Supply invariant violated")  # never create shares from thin air
    founder.quantity -= allocated
    for x in subs:
        refund = ((x.shares - x.allocated) * ipo.price).quantize(Decimal("0.01"))
        if refund > 0:
            await wallet.apply(s, x.user_id, "IPO_PURCHASE", refund, f"IPO refund {c.ticker}", key=f"ipo{ipo_id}:refund:{x.user_id}")
        if x.allocated:
            own = (await s.execute(select(ShareOwnership).where(ShareOwnership.user_id == x.user_id, ShareOwnership.company_id == c.id)
                                   .with_for_update())).scalar_one_or_none()
            if own is None:
                s.add(ShareOwnership(user_id=x.user_id, company_id=c.id, quantity=x.allocated, avg_price=ipo.price))
            else:
                own.avg_price = ((own.avg_price * own.quantity + ipo.price * x.allocated) / (own.quantity + x.allocated)).quantize(P4)
                own.quantity += x.allocated
    raised = (ipo.price * allocated).quantize(Decimal("0.01"))
    c.cash += raised
    c.listing, c.price, c.prev_close = "LISTED", ipo.price, ipo.price
    ipo.status, ipo.total_allocated = "CLOSED", allocated
    return {"ipo": ipo, "company": c, "allocated": allocated, "raised": raised, "subs": len(subs)}


async def due_ipo_ids(s: AsyncSession) -> list[int]:
    return list((await s.execute(select(Ipo.id).where(Ipo.status == "OPEN", Ipo.closes_at <= datetime.now(timezone.utc)))).scalars())
