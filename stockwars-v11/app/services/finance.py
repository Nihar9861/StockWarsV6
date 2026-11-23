from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from ..config import settings
from ..models import Company, Dividend, DividendPayment, Loan, ShareOwnership, Wallet
from . import wallet
from .company import GameError, _aware, _own_company, _user

C = Decimal("0.01")


def _now():
    return datetime.now(timezone.utc)


# ---------------- dividends ----------------
async def announce_dividend(s: AsyncSession, uid: int, cid: int, per_share: Decimal) -> Dividend:
    await _user(s, uid)
    c = await _own_company(s, uid, cid)
    if c.listing != "LISTED" or c.status != "ACTIVE":
        raise GameError("Only active listed companies can pay dividends")
    if c.reputation < settings.div_min_reputation:
        raise GameError(f"Reputation must be ≥ {settings.div_min_reputation}")
    last = (await s.execute(select(Dividend).where(Dividend.company_id == cid).order_by(Dividend.id.desc()).limit(1))).scalar_one_or_none()
    if last and _now() < _aware(last.created_at) + timedelta(hours=settings.div_cooldown_hours):
        raise GameError(f"One dividend per {settings.div_cooldown_hours}h")
    per_share = Decimal(per_share).quantize(Decimal("0.0001"), ROUND_DOWN)
    if per_share <= 0:
        raise GameError("Dividend per share must be > 0")
    total = (per_share * c.total_shares).quantize(C, ROUND_DOWN)
    if total > c.cash * Decimal(str(settings.div_max_cash_pct)):
        raise GameError(f"Payout {total} exceeds {int(settings.div_max_cash_pct * 100)}% of company cash ({c.cash})")
    c.cash -= total  # funds reserved up-front: dividends can never exceed company funds
    rec = _now() + timedelta(minutes=settings.div_record_minutes)
    d = Dividend(company_id=cid, per_share=per_share, reserved=total, record_at=rec, pay_at=rec + timedelta(minutes=settings.div_pay_delay_minutes))
    s.add(d)
    await s.flush()
    return d


async def process_dividends(s: AsyncSession) -> list[dict]:
    out, now_ = [], _now()
    for did in (await s.execute(select(Dividend.id).where(Dividend.status == "ANNOUNCED", Dividend.record_at <= now_))).scalars().all():
        d = (await s.execute(select(Dividend).where(Dividend.id == did).with_for_update())).scalar_one()
        if d.status != "ANNOUNCED": continue
        rows = (await s.execute(select(ShareOwnership).where(ShareOwnership.company_id == d.company_id, ShareOwnership.quantity > 0))).scalars().all()
        for o in rows:  # snapshot at record time: later trades don't change entitlement
            s.add(DividendPayment(dividend_id=d.id, user_id=o.user_id, shares=o.quantity, amount=(d.per_share * o.quantity).quantize(C, ROUND_DOWN)))
        d.status = "RECORDED"
    await s.flush()
    for did in (await s.execute(select(Dividend.id).where(Dividend.status == "RECORDED", Dividend.pay_at <= now_))).scalars().all():
        d = (await s.execute(select(Dividend).where(Dividend.id == did).with_for_update())).scalar_one()
        if d.status != "RECORDED": continue
        c = await s.get(Company, d.company_id)
        pays = (await s.execute(select(DividendPayment).where(DividendPayment.dividend_id == d.id, DividendPayment.paid == False))).scalars().all()  # noqa: E712
        total = Decimal(0)
        for p in pays:
            if p.amount > 0:
                try:
                    async with s.begin_nested():
                        await wallet.apply(s, p.user_id, "DIVIDEND", p.amount, f"Dividend {c.ticker}", key=f"div{d.id}:{p.user_id}")
                except wallet.DuplicateOperation:
                    pass
            p.paid = True
            total += p.amount
        d.paid_total += total
        c.cash += d.reserved - d.paid_total  # return unpaid remainder to company
        d.status = "PAID"
        out.append(dict(ticker=c.ticker, owner=c.owner_id, per_share=d.per_share, total=d.paid_total, holders=len(pays)))
    return out


# ---------------- loans ----------------
async def credit_score(s: AsyncSession, uid: int) -> int:
    rows = (await s.execute(select(Loan.status, func.count()).where(Loan.user_id == uid).group_by(Loan.status))).all()
    cnt = dict(rows)
    return max(300, min(850, 600 + 25 * min(cnt.get("REPAID", 0), 8) - 150 * cnt.get("DEFAULTED", 0)))


async def active_loan(s: AsyncSession, uid: int, lock=False) -> Loan | None:
    q = select(Loan).where(Loan.user_id == uid, Loan.status == "ACTIVE")
    return (await s.execute(q.with_for_update() if lock else q)).scalar_one_or_none()


async def debt_of(s: AsyncSession, uid: int) -> Decimal:
    return (await s.execute(select(func.coalesce(func.sum(Loan.outstanding), 0)).where(Loan.user_id == uid, Loan.status.in_(["ACTIVE", "DEFAULTED"])))).scalar_one()


async def loan_status(s: AsyncSession, uid: int) -> dict:
    from .trading import portfolio
    p = await portfolio(s, uid)
    score = await credit_score(s, uid)
    blocked = (await s.execute(select(Loan.id).where(Loan.user_id == uid, Loan.status == "DEFAULTED", Loan.outstanding > 0))).first() is not None
    limit = min(settings.loan_max, (Decimal("0.5") * (p["cash"] + p["market_value"]) * score / 700).quantize(C))
    loan = (await s.execute(select(Loan).where(Loan.user_id == uid, Loan.status.in_(['ACTIVE', 'DEFAULTED']), Loan.outstanding > 0)
                            .order_by(Loan.id).limit(1))).scalar_one_or_none()
    return dict(credit_score=score, max_amount=str(max(limit, Decimal(0)) if not blocked else 0), blocked=blocked,
                rate_per_day=str(settings.loan_rate_per_day), late_fee_pct=str(settings.loan_late_fee_pct), debt=str(p["debt"]),
                loan=loan and dict(id=loan.id, principal=str(loan.principal), outstanding=str(loan.outstanding), due_at=loan.due_at.isoformat(),
                                   late=loan.late_fee_applied))


async def take_loan(s: AsyncSession, uid: int, amount: Decimal, days: int, key: str) -> Loan:
    await _user(s, uid)
    w = (await s.execute(select(Wallet).where(Wallet.user_id == uid).with_for_update())).scalar_one()  # serialize per player
    amount = Decimal(amount).quantize(C)
    if not 1 <= days <= 14:
        raise GameError("Term must be 1–14 days")
    if await active_loan(s, uid):
        raise GameError("Repay your current loan first")
    st = await loan_status(s, uid)
    if st["blocked"]:
        raise GameError("Defaulted loan outstanding — clear it first")
    if amount <= 0 or amount > Decimal(st["max_amount"]):
        raise GameError(f"You can borrow up to {st['max_amount']}")
    total = (amount * (1 + settings.loan_rate_per_day * days)).quantize(C)
    loan = Loan(user_id=uid, principal=amount, total_due=total, outstanding=total, rate_per_day=settings.loan_rate_per_day,
                term_days=days, due_at=_now() + timedelta(days=days))
    s.add(loan)
    await wallet.apply(s, uid, "LOAN", amount, f"Loan {days}d", key=f"{key}:loan")
    await s.flush()
    return loan


async def repay(s: AsyncSession, uid: int, amount: Decimal, key: str) -> Loan:
    loan = (await s.execute(select(Loan).where(Loan.user_id == uid, Loan.status.in_(["ACTIVE", "DEFAULTED"]), Loan.outstanding > 0)
                            .order_by(Loan.id).limit(1).with_for_update())).scalar_one_or_none()
    if not loan:
        raise GameError("No loan to repay")
    amount = min(Decimal(amount).quantize(C), loan.outstanding)
    if amount <= 0:
        raise GameError("Invalid amount")
    await wallet.apply(s, uid, "LOAN_REPAYMENT", -amount, f"Repay loan #{loan.id}", key=f"{key}:rep")
    loan.outstanding -= amount
    if loan.outstanding <= 0:
        was_default = loan.status == "DEFAULTED"
        loan.status, loan.closed_at = ("REPAID", _now())
        if was_default:  # cleared late: keep the credit hit by not counting as REPAID
            loan.status = "DEFAULTED"
    return loan


async def process_loans(s: AsyncSession) -> list[dict]:
    out, now_ = [], _now()
    for lid in (await s.execute(select(Loan.id).where(Loan.status == "ACTIVE", Loan.due_at <= now_))).scalars().all():
        loan = (await s.execute(select(Loan).where(Loan.id == lid).with_for_update())).scalar_one()
        if loan.status != "ACTIVE": continue
        if not loan.late_fee_applied:
            fee = (loan.outstanding * settings.loan_late_fee_pct).quantize(C)
            loan.outstanding += fee; loan.total_due += fee; loan.late_fee_applied = True
            out.append(dict(user=loan.user_id, kind="LATE", fee=fee))
        if now_ >= _aware(loan.due_at) + timedelta(days=settings.loan_default_after_days):
            w = await s.get(Wallet, loan.user_id)
            take = min(w.available, loan.outstanding)  # seize available cash first
            if take > 0:
                await wallet.apply(s, loan.user_id, "LOAN_REPAYMENT", -take, f"Auto-recovery loan #{loan.id}", key=f"loan{loan.id}:recover")
                loan.outstanding -= take
            loan.status = "DEFAULTED"
            if loan.outstanding <= 0:
                loan.closed_at = now_
            out.append(dict(user=loan.user_id, kind="DEFAULT", remaining=loan.outstanding))
    return out
