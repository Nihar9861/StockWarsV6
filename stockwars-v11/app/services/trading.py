from decimal import Decimal
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from ..config import settings
from ..models import Company, MarketState, ShareOwnership, Trade, User
from . import wallet

CENT = Decimal("0.01")


class TradeError(Exception): ...


def estimate(price: Decimal, qty: int):
    value = (price * qty).quantize(CENT)
    fee = (value * settings.trading_fee_pct).quantize(CENT)
    return value, fee


async def execute(s: AsyncSession, uid: int, ticker: str, side: str, qty: int, key: str) -> Trade:
    if qty <= 0 or qty > 10_000_000:
        raise TradeError("Invalid quantity")
    if (await s.execute(select(Trade.id).where(Trade.idempotency_key == key))).first():
        raise wallet.DuplicateOperation(key)
    user = await s.get(User, uid)
    if not user or user.status != "ACTIVE":
        raise TradeError("Account not active")
    st = await s.get(MarketState, 1)
    if st.status not in ("OPEN", "RECOVERY"):
        raise TradeError(f"Market is {st.status}")
    c = (await s.execute(select(Company).where(Company.ticker == ticker.upper()).with_for_update())).scalar_one_or_none()
    if not c or c.listing != "LISTED":
        raise TradeError("Stock not listed")
    if c.status in ("SUSPENDED", "BANKRUPT"):
        raise TradeError(f"Trading halted ({c.status})")
    value, fee = estimate(c.price, qty)
    own = (await s.execute(select(ShareOwnership).where(ShareOwnership.user_id == uid, ShareOwnership.company_id == c.id)
                           .with_for_update())).scalar_one_or_none()
    if side == "BUY":
        held = (await s.execute(select(func.coalesce(func.sum(ShareOwnership.quantity), 0))
                                .where(ShareOwnership.company_id == c.id))).scalar_one()
        if held + qty > c.total_shares:
            raise TradeError(f"Only {c.total_shares - held} shares available")
        await wallet.apply(s, uid, "STOCK_BUY", -value, f"Buy {qty} {c.ticker} @ {c.price}", key=f"{key}:v")
        await wallet.apply(s, uid, "TRADING_FEE", -fee, f"Fee {c.ticker}", key=f"{key}:f")
        if own is None:
            own = ShareOwnership(user_id=uid, company_id=c.id, quantity=0, avg_price=0, realized_pnl=0)
            s.add(own)
        total_cost = own.avg_price * own.quantity + c.price * qty
        own.quantity += qty
        own.avg_price = (total_cost / own.quantity).quantize(Decimal("0.0001"))
        c.pressure += qty
    elif side == "SELL":
        if own is None or own.quantity < qty:
            raise TradeError("Not enough shares")
        await wallet.apply(s, uid, "STOCK_SELL", value, f"Sell {qty} {c.ticker} @ {c.price}", key=f"{key}:v")
        await wallet.apply(s, uid, "TRADING_FEE", -fee, f"Fee {c.ticker}", key=f"{key}:f")
        own.realized_pnl += ((c.price - own.avg_price) * qty).quantize(CENT)
        own.quantity -= qty
        c.pressure -= qty
    else:
        raise TradeError("Bad side")
    c.volume += qty
    t = Trade(user_id=uid, company_id=c.id, side=side, quantity=qty, price=c.price, value=value, fee=fee, idempotency_key=key)
    s.add(t)
    await s.flush()
    return t


async def portfolio(s: AsyncSession, uid: int):
    rows = (await s.execute(select(ShareOwnership, Company).join(Company, Company.id == ShareOwnership.company_id)
                            .where(ShareOwnership.user_id == uid, ShareOwnership.quantity > 0))).all()
    from ..models import Wallet
    w = await s.get(Wallet, uid)
    holdings, invested, market_val, realized = [], Decimal(0), Decimal(0), Decimal(0)
    for o, c in rows:
        mv = (c.price * o.quantity).quantize(CENT)
        cost = (o.avg_price * o.quantity).quantize(CENT)
        holdings.append(dict(ticker=c.ticker, qty=o.quantity, avg=o.avg_price, price=c.price, value=mv, pnl=mv - cost,
                             pnl_pct=((c.price / o.avg_price - 1) * 100) if o.avg_price else Decimal(0)))
        invested += cost; market_val += mv; realized += o.realized_pnl
    from ..models import Loan
    debt = (await s.execute(select(func.coalesce(func.sum(Loan.outstanding), 0)).where(Loan.user_id == uid, Loan.status.in_(['ACTIVE', 'DEFAULTED'])))).scalar_one()
    return dict(debt=debt, cash=w.available, reserved=w.reserved, invested=invested, market_value=market_val,
                unrealized=market_val - invested, realized=realized, net_worth=w.available + market_val - debt, holdings=holdings)
