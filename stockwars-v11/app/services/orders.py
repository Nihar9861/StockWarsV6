from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from ..config import settings
from ..models import Company, LimitOrder
from . import trading, wallet
from .company import GameError, _aware, _user

P4 = Decimal("0.0001")


async def place_order(s: AsyncSession, uid: int, ticker: str, side: str, qty: int, price: Decimal, days: int = 1) -> LimitOrder:
    await _user(s, uid)
    side = side.upper()
    c = (await s.execute(select(Company).where(Company.ticker == ticker.upper()))).scalar_one_or_none()
    if not c or c.listing != "LISTED" or c.status in ("SUSPENDED", "BANKRUPT"):
        raise GameError("Stock not tradable")
    price = Decimal(price).quantize(P4)
    if side not in ("BUY", "SELL") or not 1 <= qty <= 10_000_000 or price <= 0 or not 1 <= days <= 7:
        raise GameError("Invalid order")
    if side == "BUY" and price >= c.price:
        raise GameError(f"Buy limit must be below the current price ({c.price}). Use a normal buy to buy now.")
    if side == "SELL" and price <= c.price:
        raise GameError(f"Sell limit must be above the current price ({c.price}). Use a normal sell to sell now.")
    n = (await s.execute(select(func.count()).select_from(LimitOrder).where(LimitOrder.user_id == uid, LimitOrder.status == "OPEN"))).scalar_one()
    if n >= settings.max_open_orders:
        raise GameError(f"Max {settings.max_open_orders} open orders")
    o = LimitOrder(user_id=uid, company_id=c.id, side=side, quantity=qty, limit_price=price, expires_at=datetime.now(timezone.utc) + timedelta(days=days))
    s.add(o)
    await s.flush()
    return o


async def cancel_order(s: AsyncSession, uid: int, oid: int):
    o = (await s.execute(select(LimitOrder).where(LimitOrder.id == oid).with_for_update())).scalar_one_or_none()
    if not o or o.user_id != uid or o.status != "OPEN":
        raise GameError("Order not found")
    o.status = "CANCELLED"


async def list_orders(s: AsyncSession, uid: int):
    rows = (await s.execute(select(LimitOrder, Company).join(Company, Company.id == LimitOrder.company_id)
                            .where(LimitOrder.user_id == uid).order_by(LimitOrder.id.desc()).limit(40))).all()
    return [dict(id=o.id, ticker=c.ticker, side=o.side, qty=o.quantity, limit=str(o.limit_price), price=str(c.price), status=o.status,
                 reason=o.reason, fill=str(o.fill_price) if o.fill_price else None, expires_at=o.expires_at.isoformat()) for o, c in rows]


async def process_orders(s: AsyncSession) -> list[dict]:
    """Run after each market cycle: fill triggered limit orders at the current price, expire old ones."""
    out, now_ = [], datetime.now(timezone.utc)
    rows = (await s.execute(select(LimitOrder, Company).join(Company, Company.id == LimitOrder.company_id)
                            .where(LimitOrder.status == "OPEN").order_by(LimitOrder.id))).all()
    for o, c in rows:
        if _aware(o.expires_at) <= now_:
            o.status = "EXPIRED"
            out.append(dict(user=o.user_id, ticker=c.ticker, side=o.side, qty=o.quantity, status="EXPIRED", price=None, reason=""))
            continue
        hit = (o.side == "BUY" and c.price <= o.limit_price) or (o.side == "SELL" and c.price >= o.limit_price)
        if not hit:
            continue
        try:
            async with s.begin_nested():
                t = await trading.execute(s, o.user_id, c.ticker, o.side, o.quantity, f"lo:{o.id}")
            o.status, o.fill_price, o.filled_at = "FILLED", t.price, now_
            out.append(dict(user=o.user_id, ticker=c.ticker, side=o.side, qty=o.quantity, status="FILLED", price=t.price, reason=""))
        except wallet.DuplicateOperation:
            o.status = "FILLED"
        except (trading.TradeError, wallet.WalletError) as ex:
            o.status, o.reason = "FAILED", str(ex)[:150]
            out.append(dict(user=o.user_id, ticker=c.ticker, side=o.side, qty=o.quantity, status="FAILED", price=None, reason=str(ex)))
    return out
