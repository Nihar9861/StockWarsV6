from datetime import datetime, timedelta, timezone
from decimal import Decimal
from math import ceil
from sqlalchemy import func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession
from ..config import settings
from ..models import (Achievement, Company, DailyClaim, DividendPayment, Loan, MissionClaim, PortfolioSnapshot, PriceAlert,
                      ShareOwnership, Trade, User, Wallet, Watchlist)
from . import wallet
from .company import GameError

C = Decimal("0.01")
IST = timedelta(hours=5, minutes=30)
TIERS = [(0, "Beginner"), (1_200_000, "Trader"), (1_500_000, "Investor"), (2_000_000, "Broker"), (3_000_000, "Entrepreneur"),
         (5_000_000, "Millionaire"), (10_000_000, "Tycoon"), (100_000_000, "Billionaire"), (1_000_000_000, "Market Legend")]


def ist_now(): return datetime.now(timezone.utc) + IST
def ist_day(): return ist_now().date().isoformat()
def ist_midnight_utc():
    n = ist_now()
    return datetime(n.year, n.month, n.day, tzinfo=timezone.utc) - IST


def tier_for(nw) -> str:
    name = "Beginner"
    for thr, t in TIERS:
        if nw >= thr: name = t
    return name


# ---------- portfolio snapshots + rank tiers ----------
async def snapshot_all(s: AsyncSession) -> int:
    sv = (select(ShareOwnership.user_id.label("uid"), func.sum(ShareOwnership.quantity * Company.price).label("v"))
          .join(Company, Company.id == ShareOwnership.company_id).group_by(ShareOwnership.user_id).subquery())
    dv = (select(Loan.user_id.label("uid"), func.sum(Loan.outstanding).label("d")).where(Loan.status.in_(["ACTIVE", "DEFAULTED"]))
          .group_by(Loan.user_id).subquery())
    rows = (await s.execute(select(Wallet.user_id, (Wallet.available + func.coalesce(sv.c.v, 0) - func.coalesce(dv.c.d, 0)).label("nw"))
                            .join(User, User.id == Wallet.user_id).outerjoin(sv, sv.c.uid == Wallet.user_id)
                            .outerjoin(dv, dv.c.uid == Wallet.user_id).where(User.status == "ACTIVE"))).all()
    if not rows:
        return 0
    now_ = datetime.now(timezone.utc)
    await s.execute(insert(PortfolioSnapshot), [dict(user_id=u, net_worth=Decimal(nw).quantize(C), created_at=now_) for u, nw in rows])
    nws = dict(rows)
    for u in (await s.execute(select(User).where(User.status == "ACTIVE"))).scalars():
        if u.id in nws and u.role != "OWNER_HIDDEN":
            t = tier_for(nws[u.id])
            if u.rank != t:
                u.rank = t
    return len(rows)


async def performance(s: AsyncSession, uid: int, rng: str) -> list[dict]:
    now_ = datetime.now(timezone.utc)
    since = {"today": ist_midnight_utc(), "7d": now_ - timedelta(days=7), "30d": now_ - timedelta(days=30)}.get(rng)
    q = select(PortfolioSnapshot.created_at, PortfolioSnapshot.net_worth).where(PortfolioSnapshot.user_id == uid).order_by(PortfolioSnapshot.created_at)
    if since:
        q = q.where(PortfolioSnapshot.created_at >= since)
    rows = (await s.execute(q)).all()
    step = max(1, ceil(len(rows) / 150))
    pts = rows[::step] + ([rows[-1]] if rows and (len(rows) - 1) % step else [])
    return [dict(t=t.isoformat(), v=str(v)) for t, v in pts]


# ---------- watchlist + alerts ----------
async def _company(s, ticker) -> Company:
    c = (await s.execute(select(Company).where(Company.ticker == ticker.upper()))).scalar_one_or_none()
    if not c: raise GameError("Unknown ticker")
    return c


async def toggle_watch(s, uid, ticker) -> bool:
    c = await _company(s, ticker)
    w = (await s.execute(select(Watchlist).where(Watchlist.user_id == uid, Watchlist.company_id == c.id))).scalar_one_or_none()
    if w:
        await s.delete(w); return False
    n = (await s.execute(select(func.count()).select_from(Watchlist).where(Watchlist.user_id == uid))).scalar_one()
    if n >= 30: raise GameError("Watchlist is full (30)")
    s.add(Watchlist(user_id=uid, company_id=c.id)); return True


async def watchlist(s, uid) -> list[str]:
    return list((await s.execute(select(Company.ticker).join(Watchlist, Watchlist.company_id == Company.id).where(Watchlist.user_id == uid))).scalars())


async def create_alert(s, uid, ticker, target: Decimal) -> PriceAlert:
    c = await _company(s, ticker)
    target = Decimal(target).quantize(Decimal("0.0001"))
    if target <= 0 or target == c.price: raise GameError("Invalid target price")
    n = (await s.execute(select(func.count()).select_from(PriceAlert).where(PriceAlert.user_id == uid, PriceAlert.triggered == False))).scalar_one()  # noqa: E712
    if n >= 10: raise GameError("Max 10 active alerts")
    a = PriceAlert(user_id=uid, company_id=c.id, target=target, direction="ABOVE" if target > c.price else "BELOW")
    s.add(a); await s.flush(); return a


async def list_alerts(s, uid):
    rows = (await s.execute(select(PriceAlert, Company).join(Company, Company.id == PriceAlert.company_id)
                            .where(PriceAlert.user_id == uid, PriceAlert.triggered == False).order_by(PriceAlert.id.desc()))).all()  # noqa: E712
    return [dict(id=a.id, ticker=c.ticker, target=str(a.target), direction=a.direction, price=str(c.price)) for a, c in rows]


async def delete_alert(s, uid, aid):
    a = await s.get(PriceAlert, aid)
    if a and a.user_id == uid: await s.delete(a)


async def check_alerts(s) -> list[dict]:
    rows = (await s.execute(select(PriceAlert, Company).join(Company, Company.id == PriceAlert.company_id)
                            .where(PriceAlert.triggered == False))).all()  # noqa: E712
    out = []
    for a, c in rows:
        if (a.direction == "ABOVE" and c.price >= a.target) or (a.direction == "BELOW" and c.price <= a.target):
            a.triggered = True
            out.append(dict(user=a.user_id, ticker=c.ticker, target=a.target, price=c.price, direction=a.direction))
    return out


# ---------- daily reward, missions, badges ----------
MISSIONS = {"trades3": ("Make 3 trades today", 3, 20_000), "hold3": ("Hold 3 different stocks", 3, 15_000), "sectors2": ("Own stocks in 2 sectors", 2, 15_000)}
BADGES = {"FIRST_TRADE": "First trade", "TRADER_10": "10 trades", "TRADER_100": "100 trades", "DIVERSIFIED": "5 stocks held", "FOUNDER": "Company founder",
          "LISTED": "IPO completed", "DIVIDEND": "Dividend earner", "DEBT_FREE": "Loan repaid", "PROFIT_1L": "₹1L realized profit"}


async def _stats(s, uid) -> dict:
    t0 = ist_midnight_utc()
    cnt = lambda *w: select(func.count()).select_from(Trade).where(Trade.user_id == uid, *w)
    held = (await s.execute(select(Company.sector_id).join(ShareOwnership, ShareOwnership.company_id == Company.id)
                            .where(ShareOwnership.user_id == uid, ShareOwnership.quantity > 0))).scalars().all()
    return dict(trades_today=(await s.execute(cnt(Trade.created_at >= t0))).scalar_one(), trades_all=(await s.execute(cnt())).scalar_one(),
                stocks=len(held), sectors=len(set(held)))


async def award_badges(s, uid) -> list[str]:
    st = await _stats(s, uid)
    owned = list((await s.execute(select(Company.listing).where(Company.owner_id == uid))).scalars())
    realized = (await s.execute(select(func.coalesce(func.sum(ShareOwnership.realized_pnl), 0)).where(ShareOwnership.user_id == uid))).scalar_one()
    div = (await s.execute(select(DividendPayment.id).where(DividendPayment.user_id == uid, DividendPayment.paid == True).limit(1))).first()  # noqa: E712
    repaid = (await s.execute(select(Loan.id).where(Loan.user_id == uid, Loan.status == "REPAID").limit(1))).first()
    cond = {"FIRST_TRADE": st["trades_all"] >= 1, "TRADER_10": st["trades_all"] >= 10, "TRADER_100": st["trades_all"] >= 100,
            "DIVERSIFIED": st["stocks"] >= 5, "FOUNDER": bool(owned), "LISTED": "LISTED" in owned, "DIVIDEND": bool(div),
            "DEBT_FREE": bool(repaid), "PROFIT_1L": realized >= 100_000}
    have = set((await s.execute(select(Achievement.key).where(Achievement.user_id == uid))).scalars())
    new = [k for k, ok in cond.items() if ok and k not in have]
    for k in new: s.add(Achievement(user_id=uid, key=k))
    return new


async def rewards(s, uid) -> dict:
    day = ist_day(); yday = (ist_now() - timedelta(days=1)).date().isoformat()
    last = (await s.execute(select(DailyClaim).where(DailyClaim.user_id == uid).order_by(DailyClaim.id.desc()).limit(1))).scalar_one_or_none()
    claimed = bool(last and last.day == day)
    streak = last.streak if claimed else ((last.streak + 1) if last and last.day == yday else 1)
    amount = settings.daily_reward * min(streak, 7)
    st = await _stats(s, uid)
    prog = {"trades3": st["trades_today"], "hold3": st["stocks"], "sectors2": st["sectors"]}
    done_today = set((await s.execute(select(MissionClaim.mission).where(MissionClaim.user_id == uid, MissionClaim.day == day))).scalars())
    await award_badges(s, uid)
    earned = set((await s.execute(select(Achievement.key).where(Achievement.user_id == uid))).scalars())
    u = await s.get(User, uid)
    return dict(rank=u.rank, daily=dict(claimable=not claimed, streak=streak, amount=str(amount)),
                missions=[dict(key=k, title=v[0], target=v[1], reward=v[2], progress=min(prog[k], v[1]), done=prog[k] >= v[1], claimed=k in done_today) for k, v in MISSIONS.items()],
                badges=[dict(key=k, title=t, earned=k in earned) for k, t in BADGES.items()])


async def claim_daily(s, uid) -> Decimal:
    r = await rewards(s, uid)
    if not r["daily"]["claimable"]: raise GameError("Already claimed today")
    day, amt = ist_day(), Decimal(r["daily"]["amount"])
    s.add(DailyClaim(user_id=uid, day=day, streak=r["daily"]["streak"], amount=amt))
    await s.flush()
    await wallet.apply(s, uid, "EVENT_REWARD", amt, f"Daily reward day {r['daily']['streak']}", key=f"daily:{uid}:{day}")
    return amt


async def claim_mission(s, uid, key) -> Decimal:
    if key not in MISSIONS: raise GameError("Unknown mission")
    r = await rewards(s, uid)
    m = next(x for x in r["missions"] if x["key"] == key)
    if m["claimed"]: raise GameError("Already claimed")
    if not m["done"]: raise GameError("Mission not complete yet")
    day = ist_day()
    s.add(MissionClaim(user_id=uid, mission=key, day=day))
    await s.flush()
    await wallet.apply(s, uid, "EVENT_REWARD", Decimal(m["reward"]), f"Mission {key}", key=f"mission:{uid}:{key}:{day}")
    return Decimal(m["reward"])
