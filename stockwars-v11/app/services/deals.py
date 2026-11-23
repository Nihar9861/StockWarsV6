from datetime import datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from ..config import settings
from ..models import Company, ShareOffer, ShareOwnership, Trade
from . import players, trading, wallet
from .company import GameError, _aware, _user

P4 = Decimal("0.0001")


async def create_offer(s: AsyncSession, uid: int, other_ref: str, ticker: str, side: str, qty: int, price: Decimal, takeover: bool = False) -> ShareOffer:
    await _user(s, uid)
    other = await players.find_user(s, str(other_ref))
    if not other or other.status != "ACTIVE" or other.id == uid:
        raise GameError("Player not found or not active")
    c = (await s.execute(select(Company).where(Company.ticker == ticker.upper()))).scalar_one_or_none()
    if not c or c.listing != "LISTED" or c.status in ("SUSPENDED", "BANKRUPT"):
        raise GameError("Stock not tradable")
    price = Decimal(price).quantize(P4)
    n = (await s.execute(select(func.count()).select_from(ShareOffer).where(ShareOffer.proposer_id == uid, ShareOffer.status == "OPEN"))).scalar_one()
    if n >= 5: raise GameError("Max 5 open offers")
    today = (await s.execute(select(func.count()).select_from(ShareOffer).where(ShareOffer.proposer_id == uid, ShareOffer.created_at >= datetime.now(timezone.utc) - timedelta(days=1)))).scalar_one()
    if today >= 15: raise GameError("Daily offer limit reached")
    if takeover:
        if c.owner_id != other.id: raise GameError("Takeover bids go to the company's founder")
        if price < c.price * Decimal("1.1"): raise GameError("Takeover price must be ≥ 10% above market")
        kind, buyer, seller, qty = "TAKEOVER", uid, other.id, 0
    else:
        band = Decimal(str(settings.offer_price_band))
        if not (c.price * (1 - band) <= price <= c.price * (1 + band)):
            raise GameError(f"Price must be within ±{int(band * 100)}% of market ({c.price})")
        if qty <= 0: raise GameError("Quantity must be positive")
        kind = "TRANSFER"
        buyer, seller = (uid, other.id) if side.upper() == "BUY" else (other.id, uid)
        h = (await s.execute(select(ShareOwnership.quantity).where(ShareOwnership.user_id == seller, ShareOwnership.company_id == c.id))).scalar() or 0
        if h < qty: raise GameError("Seller doesn't hold that many shares")
    o = ShareOffer(kind=kind, proposer_id=uid, seller_id=seller, buyer_id=buyer, company_id=c.id, qty=qty, price=price,
                   expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.offer_ttl_minutes))
    s.add(o); await s.flush(); return o


async def accept_offer(s: AsyncSession, uid: int, oid: int) -> dict:
    o = (await s.execute(select(ShareOffer).where(ShareOffer.id == oid).with_for_update())).scalar_one_or_none()
    if not o or o.status != "OPEN": raise GameError("Offer is not open")
    if _aware(o.expires_at) <= datetime.now(timezone.utc): raise GameError("Offer expired")
    if uid == o.proposer_id or uid not in (o.seller_id, o.buyer_id): raise GameError("You can't accept this offer")
    await _user(s, o.seller_id); await _user(s, o.buyer_id)
    pair = (await s.execute(select(func.count()).select_from(ShareOffer).where(
        ShareOffer.status == "ACCEPTED", ShareOffer.resolved_at >= datetime.now(timezone.utc) - timedelta(days=1),
        or_((ShareOffer.seller_id == o.seller_id) & (ShareOffer.buyer_id == o.buyer_id), (ShareOffer.seller_id == o.buyer_id) & (ShareOffer.buyer_id == o.seller_id))))).scalar_one()
    if pair >= 3: raise GameError("Too many trades between these two players today (anti-collusion limit)")
    c = (await s.execute(select(Company).where(Company.id == o.company_id).with_for_update())).scalar_one()
    if c.listing != "LISTED" or c.status in ("SUSPENDED", "BANKRUPT"): raise GameError("Stock not tradable")
    sown = (await s.execute(select(ShareOwnership).where(ShareOwnership.user_id == o.seller_id, ShareOwnership.company_id == c.id).with_for_update())).scalar_one_or_none()
    qty = (sown.quantity if sown else 0) if o.kind == "TAKEOVER" else o.qty
    if o.kind == "TAKEOVER" and c.owner_id != o.seller_id: raise GameError("Seller no longer owns the company")
    if not sown or qty <= 0 or sown.quantity < qty: raise GameError("Seller doesn't have enough shares anymore")
    bown = (await s.execute(select(ShareOwnership).where(ShareOwnership.user_id == o.buyer_id, ShareOwnership.company_id == c.id).with_for_update())).scalar_one_or_none()
    if bown is None:
        bown = ShareOwnership(user_id=o.buyer_id, company_id=c.id, quantity=0, avg_price=0, realized_pnl=0); s.add(bown); await s.flush()
    if o.kind == "TAKEOVER" and (bown.quantity + qty) * 100 < c.total_shares * 51: raise GameError("Bidder must hold ≥ 51% after the takeover")
    value, fee = trading.estimate(o.price, qty)
    k = f"offer{o.id}"
    await wallet.apply(s, o.buyer_id, "STOCK_BUY", -value, f"Deal {qty} {c.ticker} @ {o.price}", key=f"{k}:bv")
    await wallet.apply(s, o.buyer_id, "TRADING_FEE", -fee, f"Fee {c.ticker}", key=f"{k}:bf")
    await wallet.apply(s, o.seller_id, "STOCK_SELL", value, f"Deal {qty} {c.ticker} @ {o.price}", key=f"{k}:sv")
    await wallet.apply(s, o.seller_id, "TRADING_FEE", -fee, f"Fee {c.ticker}", key=f"{k}:sf")
    bown.avg_price = ((bown.avg_price * bown.quantity + o.price * qty) / (bown.quantity + qty)).quantize(P4)
    bown.quantity += qty
    sown.realized_pnl += ((o.price - sown.avg_price) * qty).quantize(Decimal("0.01"))
    sown.quantity -= qty
    s.add(Trade(user_id=o.buyer_id, company_id=c.id, side="BUY", quantity=qty, price=o.price, value=value, fee=fee, idempotency_key=f"{k}:buy"))
    s.add(Trade(user_id=o.seller_id, company_id=c.id, side="SELL", quantity=qty, price=o.price, value=value, fee=fee, idempotency_key=f"{k}:sell"))
    if o.kind == "TAKEOVER": c.owner_id = o.buyer_id
    o.status, o.resolved_at = "ACCEPTED", datetime.now(timezone.utc)
    return dict(ticker=c.ticker, qty=qty, price=o.price, kind=o.kind, seller=o.seller_id, buyer=o.buyer_id)


async def cancel_offer(s: AsyncSession, uid: int, oid: int) -> ShareOffer:
    o = (await s.execute(select(ShareOffer).where(ShareOffer.id == oid).with_for_update())).scalar_one_or_none()
    if not o or o.status != "OPEN" or uid not in (o.seller_id, o.buyer_id): raise GameError("Offer not found")
    o.status, o.resolved_at = "CANCELLED", datetime.now(timezone.utc)
    return o


async def expire_offers(s: AsyncSession):
    await s.execute(update(ShareOffer).where(ShareOffer.status == "OPEN", ShareOffer.expires_at <= datetime.now(timezone.utc)).values(status="EXPIRED"))
