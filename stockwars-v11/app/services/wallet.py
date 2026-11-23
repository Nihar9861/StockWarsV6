from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..models import Wallet, WalletTransaction

CATEGORIES = {"STARTING_BALANCE", "STOCK_BUY", "STOCK_SELL", "IPO_PURCHASE", "IPO_PROCEEDS", "COMPANY_CREATION",
              "COMPANY_UPGRADE", "DIVIDEND", "LOAN", "LOAN_REPAYMENT", "TRADING_FEE", "EVENT_REWARD", "PENALTY",
              "ADMIN_ADJUSTMENT"}


class WalletError(Exception): ...
class InsufficientFunds(WalletError): ...
class DuplicateOperation(WalletError): ...


async def apply(s: AsyncSession, uid: int, category: str, amount: Decimal, reason: str = "",
                key: str | None = None) -> WalletTransaction:
    """Single entry point for ALL cash movement. Row-locks the wallet, writes ledger entry atomically."""
    assert category in CATEGORIES
    amount = Decimal(amount).quantize(Decimal("0.01"))
    if key and (await s.execute(select(WalletTransaction.id).where(WalletTransaction.idempotency_key == key))).first():
        raise DuplicateOperation(key)
    w = (await s.execute(select(Wallet).where(Wallet.user_id == uid).with_for_update())).scalar_one_or_none()
    if w is None:
        raise WalletError("No wallet")
    before, after = w.available, w.available + amount
    if after < 0:
        raise InsufficientFunds(f"Need {-amount}, have {before}")
    w.available = after
    tx = WalletTransaction(user_id=uid, category=category, amount=amount, balance_before=before,
                           balance_after=after, reason=reason[:255], idempotency_key=key)
    s.add(tx)
    await s.flush()
    return tx
