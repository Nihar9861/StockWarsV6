import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from ..config import settings
from ..models import Battle, BattleHolding, BattlePlayer, BattleTrade, Company, MarketState, Sector, User, WalletTransaction
from . import trading, wallet
from .company import GameError, _aware, _user
from .engagement import ist_midnight_utc

C = Decimal("0.01")
FORMATS = {"QUICK": ("Quick Battle", 30, 500_000), "DAILY": ("Daily Battle", 1440, 1_000_000),
           "WEEKLY": ("Weekly Championship", 10080, 5_000_000), "SECTOR": ("Sector Battle", 1440, 1_000_000)}
PRIZES = {1: (500, 50_000), 2: (300, 25_000), 3: (150, 10_000)}  # rank: (xp, virtual cash)
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _now(): return datetime.now(timezone.utc)


async def active_battle(s: AsyncSession, uid: int, lock: bool = False) -> Battle | None:
    q = select(Battle).join(BattlePlayer, BattlePlayer.battle_id == Battle.id).where(BattlePlayer.user_id == uid, Battle.status.in_(["LOBBY", "LIVE"]))
    return (await s.execute(q.with_for_update() if lock else q)).scalars().first()


async def create_battle(s: AsyncSession, uid: int, fmt: str, sectors: list[str] | None = None, chat_id: int | None = None) -> Battle:
    await _user(s, uid)
    fmt = fmt.upper()
    if fmt not in FORMATS: raise GameError("Format: quick, daily, weekly or sector")
    if await active_battle(s, uid): raise GameError("You are already in a battle — /battleleave first (or finish it)")
    names: list[str] = []
    if fmt == "SECTOR":
        have = {x.name.lower(): x.name for x in (await s.execute(select(Sector))).scalars()}
        names = [have[x.strip().lower()] for x in (sectors or []) if x.strip().lower() in have]
        if not names: raise GameError("Pick at least one valid sector, e.g. /battlecreate sector Technology,Banking")
    for _ in range(50):
        code = "".join(random.choice(ALPHABET) for _ in range(6))
        if not (await s.execute(select(Battle.id).where(Battle.code == code))).first():
            break
    label, mins, cash = FORMATS[fmt]
    b = Battle(code=code, host_id=uid, chat_id=chat_id, format=fmt, max_players=settings.battle_max_players, start_cash=Decimal(cash),
               duration_min=mins, sectors=names, lobby_expires_at=_now() + timedelta(minutes=30))
    s.add(b); await s.flush()
    s.add(BattlePlayer(battle_id=b.id, user_id=uid, cash=b.start_cash))
    return b


async def join_battle(s: AsyncSession, uid: int, code: str) -> Battle:
    await _user(s, uid)
    b = (await s.execute(select(Battle).where(Battle.code == code.strip().upper()).with_for_update())).scalar_one_or_none()
    if not b or b.status != "LOBBY": raise GameError("Room not found or already started")
    if await active_battle(s, uid): raise GameError("You are already in a battle")
    n = (await s.execute(select(func.count()).select_from(BattlePlayer).where(BattlePlayer.battle_id == b.id))).scalar_one()
    if n >= b.max_players: raise GameError("Room is full")
    s.add(BattlePlayer(battle_id=b.id, user_id=uid, cash=b.start_cash))
    await s.flush()
    return b


async def leave_battle(s: AsyncSession, uid: int) -> Battle:
    b = await active_battle(s, uid, lock=True)
    if not b or b.status != "LOBBY": raise GameError("You can only leave before the battle starts")
    p = (await s.execute(select(BattlePlayer).where(BattlePlayer.battle_id == b.id, BattlePlayer.user_id == uid))).scalar_one()
    await s.delete(p); await s.flush()
    rest = (await s.execute(select(BattlePlayer).where(BattlePlayer.battle_id == b.id).order_by(BattlePlayer.id))).scalars().all()
    if not rest: b.status = "CANCELLED"
    elif b.host_id == uid: b.host_id = rest[0].user_id
    return b


async def start_battle(s: AsyncSession, uid: int) -> Battle:
    b = await active_battle(s, uid, lock=True)
    if not b or b.status != "LOBBY" or b.host_id != uid: raise GameError("Only the host can start a room that is in the lobby")
    n = (await s.execute(select(func.count()).select_from(BattlePlayer).where(BattlePlayer.battle_id == b.id))).scalar_one()
    if n < settings.battle_min_players: raise GameError(f"Need at least {settings.battle_min_players} players (room has {n})")
    st = await s.get(MarketState, 1)
    if st.status != "OPEN": raise GameError(f"Market is {st.status} — battles can start only while the market is open")
    b.status, b.starts_at = "LIVE", _now()
    b.ends_at = b.starts_at + timedelta(minutes=b.duration_min)
    return b


async def trade(s: AsyncSession, uid: int, ticker: str, side: str, qty: int, key: str) -> dict:
    side = side.upper()
    b = await active_battle(s, uid)
    if not b or b.status != "LIVE" or _aware(b.ends_at) <= _now(): raise GameError("No live battle")
    if (await s.get(MarketState, 1)).status != "OPEN": raise GameError("Market is closed")
    if not 1 <= qty <= 10_000_000 or side not in ("BUY", "SELL"): raise GameError("Invalid order")
    if (await s.execute(select(BattleTrade.id).where(BattleTrade.idempotency_key == key))).first(): raise wallet.DuplicateOperation(key)
    c = (await s.execute(select(Company).where(Company.ticker == ticker.upper()))).scalar_one_or_none()
    if not c or c.listing != "LISTED" or c.status in ("SUSPENDED", "BANKRUPT"): raise GameError("Stock not tradable")
    if b.format == "SECTOR" and (await s.get(Sector, c.sector_id)).name not in b.sectors:
        raise GameError("This sector is not allowed in this battle")
    p = (await s.execute(select(BattlePlayer).where(BattlePlayer.battle_id == b.id, BattlePlayer.user_id == uid).with_for_update())).scalar_one()
    h = (await s.execute(select(BattleHolding).where(BattleHolding.battle_id == b.id, BattleHolding.user_id == uid, BattleHolding.company_id == c.id).with_for_update())).scalar_one_or_none()
    value, fee = trading.estimate(c.price, qty)
    if side == "BUY":
        if p.cash < value + fee: raise GameError(f"Not enough battle cash ({p.cash})")
        p.cash -= value + fee
        if h is None:
            h = BattleHolding(battle_id=b.id, user_id=uid, company_id=c.id, quantity=0, avg_price=0); s.add(h)
        h.avg_price = ((h.avg_price * h.quantity + c.price * qty) / (h.quantity + qty)).quantize(Decimal("0.0001"))
        h.quantity += qty
    else:
        if h is None or h.quantity < qty: raise GameError("Not enough shares")
        p.cash += value - fee
        h.quantity -= qty
    s.add(BattleTrade(battle_id=b.id, user_id=uid, company_id=c.id, side=side, quantity=qty, price=c.price, fee=fee, idempotency_key=key))
    await s.flush()
    return dict(ticker=c.ticker, side=side, qty=qty, price=c.price, fee=fee, cash=p.cash)


async def standings(s: AsyncSession, b: Battle) -> list[dict]:
    players = (await s.execute(select(BattlePlayer, User).join(User, User.id == BattlePlayer.user_id).where(BattlePlayer.battle_id == b.id).order_by(BattlePlayer.id))).all()
    hold = (await s.execute(select(BattleHolding, Company).join(Company, Company.id == BattleHolding.company_id)
                            .where(BattleHolding.battle_id == b.id, BattleHolding.quantity > 0))).all()
    by: dict[int, list] = {}
    for h, c in hold:
        by.setdefault(h.user_id, []).append(dict(ticker=c.ticker, qty=h.quantity, avg=str(h.avg_price), price=str(c.price), value=str((c.price * h.quantity).quantize(C))))
    out = []
    for p, u in players:
        hv = sum((Decimal(x["value"]) for x in by.get(p.user_id, [])), Decimal(0))
        live = p.cash + hv
        v = p.final_value if p.final_value is not None else live
        out.append(dict(user_id=p.user_id, name=(u.username and "@" + u.username) or u.first_name, value=v, cash=p.cash, holdings=by.get(p.user_id, []),
                        pct=((v / b.start_cash - 1) * 100) if b.start_cash else Decimal(0), rank=p.rank, prize=p.prize, xp=p.xp))
    out.sort(key=lambda x: (-x["value"], x["user_id"]))
    for i, x in enumerate(out, 1):
        x["pos"] = x["rank"] or i
    return out


async def detail(s: AsyncSession, uid: int, bid: int) -> dict:
    b = await s.get(Battle, bid)
    if not b: raise GameError("Battle not found")
    st = await standings(s, b)
    if not any(x["user_id"] == uid for x in st) and b.status != "FINISHED": raise GameError("Not your battle")
    fin = b.status == "FINISHED"
    return dict(id=b.id, code=b.code, format=b.format, name=FORMATS[b.format][0], status=b.status, host_id=b.host_id, start_cash=str(b.start_cash),
                duration_min=b.duration_min, sectors=b.sectors, starts_at=b.starts_at and b.starts_at.isoformat(), ends_at=b.ends_at and b.ends_at.isoformat(),
                max_players=b.max_players, min_players=settings.battle_min_players,
                players=[dict(user_id=x["user_id"], name=x["name"], value=str(x["value"]), pct=float(x["pct"]), pos=x["pos"], me=x["user_id"] == uid,
                              prize=str(x["prize"]), xp=x["xp"], holdings=x["holdings"] if fin else None) for x in st],
                me=next(({"cash": str(x["cash"]), "holdings": x["holdings"]} for x in st if x["user_id"] == uid), None))  # others' holdings stay hidden until the end


async def _prize_budget_left(s: AsyncSession) -> Decimal:
    used = (await s.execute(select(func.coalesce(func.sum(WalletTransaction.amount), 0)).where(
        WalletTransaction.category == "EVENT_REWARD", WalletTransaction.reason.like("Battle prize%"), WalletTransaction.created_at >= ist_midnight_utc()))).scalar_one()
    return max(settings.battle_daily_reward_budget - Decimal(used), Decimal(0))


async def finish_due(s: AsyncSession) -> list[dict]:
    out = []
    for bid in (await s.execute(select(Battle.id).where(Battle.status == "LIVE", Battle.ends_at <= _now()))).scalars().all():
        b = (await s.execute(select(Battle).where(Battle.id == bid).with_for_update())).scalar_one()
        if b.status != "LIVE": continue
        st = await standings(s, b)
        n = len(st)
        left = await _prize_budget_left(s)
        for i, x in enumerate(st, 1):
            p = (await s.execute(select(BattlePlayer).where(BattlePlayer.battle_id == b.id, BattlePlayer.user_id == x["user_id"]))).scalar_one()
            traded = (await s.execute(select(func.count()).select_from(BattleTrade).where(BattleTrade.battle_id == b.id, BattleTrade.user_id == p.user_id))).scalar_one() > 0
            xp, cash = PRIZES.get(i, (50, 0))
            if not traded: xp, cash = 0, 0  # idle players earn nothing
            if n < settings.battle_prize_min_players: cash = 0  # no cash prizes in tiny rooms (anti alt-farming)
            cash = min(Decimal(cash), left).quantize(C, ROUND_DOWN)
            p.final_value, p.rank, p.prize, p.xp = x["value"].quantize(C), i, cash, xp
            (await s.get(User, p.user_id)).xp += xp
            if cash > 0:
                left -= cash
                await wallet.apply(s, p.user_id, "EVENT_REWARD", cash, f"Battle prize #{i} ({b.code})", key=f"battle{b.id}:prize:{p.user_id}")
            x.update(pos=i, prize=cash, xp=xp, value=p.final_value)
        b.status = "FINISHED"
        out.append(dict(battle=b, results=st))
    return out


async def cancel_stale(s: AsyncSession) -> list[Battle]:
    bs = (await s.execute(select(Battle).where(Battle.status == "LOBBY", Battle.lobby_expires_at <= _now()))).scalars().all()
    for b in bs: b.status = "CANCELLED"
    return bs


async def player_ids(s: AsyncSession, bid: int) -> list[int]:
    return list((await s.execute(select(BattlePlayer.user_id).where(BattlePlayer.battle_id == bid))).scalars())


async def arena(s: AsyncSession, uid: int) -> dict:
    rows = (await s.execute(select(BattlePlayer, Battle).join(Battle, Battle.id == BattlePlayer.battle_id)
                            .where(BattlePlayer.user_id == uid, Battle.status == "FINISHED").order_by(Battle.id.desc()))).all()
    wins = sum(1 for p, _ in rows if p.rank == 1)
    best = max(((p.final_value - b.start_cash) for p, b in rows if p.final_value is not None), default=Decimal(0))
    cur = await active_battle(s, uid)
    lob = (await s.execute(select(Battle, User, func.count(BattlePlayer.id)).join(User, User.id == Battle.host_id).join(BattlePlayer, BattlePlayer.battle_id == Battle.id)
                           .where(Battle.status == "LOBBY").group_by(Battle.id, User.id).order_by(Battle.id.desc()).limit(15))).all()
    u = await s.get(User, uid)
    return dict(stats=dict(played=len(rows), wins=wins, win_rate=round(wins / len(rows) * 100) if rows else 0, best_profit=str(best), trophies=wins, xp=u.xp),
                active=cur.id if cur else None,
                lobbies=[dict(id=b.id, code=b.code, name=FORMATS[b.format][0], host=(h.username and "@" + h.username) or h.first_name, players=n, max=b.max_players,
                              sectors=b.sectors, start_cash=str(b.start_cash), duration_min=b.duration_min) for b, h, n in lob],
                history=[dict(id=b.id, name=FORMATS[b.format][0], code=b.code, rank=p.rank, value=str(p.final_value), pct=float((p.final_value / b.start_cash - 1) * 100),
                              prize=str(p.prize), xp=p.xp) for p, b in rows[:15]])
