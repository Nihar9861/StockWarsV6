import random
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..config import settings
from ..models import Company, MarketEvent, MarketSnapshot, MarketState, PriceHistory, Sector
from .events import TEMPLATES

IST = ZoneInfo(settings.tz_display)
FLOOR = Decimal("0.01")


def _t(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def scheduled_status(now: datetime | None = None) -> str:
    t = (now or datetime.now(timezone.utc)).astimezone(IST).time()
    o, c = _t(settings.market_open), _t(settings.market_close)
    pre = (datetime.combine(datetime.today(), o) - timedelta(minutes=30)).time()
    if o <= t < c:
        return "OPEN"
    if pre <= t < o:
        return "PRE-MARKET"
    return "CLOSED"


async def refresh_status(s: AsyncSession, st: MarketState) -> str:
    st.status = "HALTED" if st.halted else scheduled_status()
    return st.status


def _matches(ev: MarketEvent, c: Company, sector_name: str) -> bool:
    if ev.event_type == "COMPANY":
        return c.ticker in ev.tickers
    return "*" in ev.sectors or sector_name in ev.sectors


async def _spawn_events(s, st, rng, companies, sectors) -> list[MarketEvent]:
    active = list((await s.execute(select(MarketEvent).where(MarketEvent.status == "ACTIVE"))).scalars().all())
    created: list[MarketEvent] = []

    async def build(t) -> MarketEvent | None:
        last = (await s.execute(select(MarketEvent).where(MarketEvent.template_key == t["key"])
                                .order_by(MarketEvent.id.desc()).limit(1))).scalar_one_or_none()
        if last and (last.status == "ACTIVE" or st.cycle_no < last.cooldown_until):
            return None  # duplicate prevention + cooldown
        tickers, headline, desc = [], t["headline"], t["desc"]
        if t["type"] == "COMPANY":
            c = rng.choice(companies)
            tickers = [c.ticker]
            headline, desc = headline.format(ticker=c.ticker, name=c.name), desc.format(name=c.name, ticker=c.ticker)
            if any(c.ticker in e.tickers and (e.impact > 0) != (t["impact"] > 0) for e in active + created):
                return None
        elif any(set(e.sectors) & set(t["sectors"]) and (e.impact > 0) != (t["impact"] > 0) for e in active + created):
            return None  # conflict resolution: no opposite-sign event on same scope
        dur = t["dur"] * settings.event_duration_mult
        ev = MarketEvent(template_key=t["key"], headline=headline, description=desc, event_type=t["type"],
                         severity=t["sev"], sectors=t["sectors"], tickers=tickers, impact=t["impact"],
                         duration=dur, remaining=dur, start_cycle=st.cycle_no, cooldown_until=st.cycle_no + dur + t["cd"],
                         expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.cycle_minutes * dur))
        s.add(ev)
        await s.flush()
        return ev

    for t in TEMPLATES:
        if len(active) + len(created) >= settings.max_active_events:
            break
        if rng.random() < t["prob"] * settings.event_rate:
            ev = await build(t)
            if ev: created.append(ev)
    # keep the news feed alive: always at least min_active_events running
    if len(active) + len(created) < settings.min_active_events:
        pool = [t for t in TEMPLATES if t["sev"] != "EXCEPTIONAL"]
        rng.shuffle(pool)
        for t in pool:
            ev = await build(t)
            if ev:
                created.append(ev)
                break
    return created


async def run_cycle(s: AsyncSession) -> dict:
    """One market cycle. Caller wraps in a transaction. Row-locks MarketState so only one instance runs it."""
    st = (await s.execute(select(MarketState).where(MarketState.id == 1).with_for_update())).scalar_one()
    status = await refresh_status(s, st)
    if status != "OPEN":
        return {"ran": False, "status": status, "new_events": []}
    st.cycle_no += 1
    rng = random.Random(f"{settings.seed}:{st.cycle_no}")
    sectors = {x.id: x for x in (await s.execute(select(Sector))).scalars()}
    companies = (await s.execute(select(Company).where(Company.listing == "LISTED", Company.status.notin_(["SUSPENDED", "BANKRUPT"]))
                                 .with_for_update())).scalars().all()
    new_events = await _spawn_events(s, st, rng, companies, sectors)
    active = (await s.execute(select(MarketEvent).where(MarketEvent.status == "ACTIVE"))).scalars().all()
    limit = settings.limit_normal
    if any(e.severity == "STRONG" for e in active):
        limit = settings.limit_strong
    if any(e.severity == "EXCEPTIONAL" for e in active):
        limit = settings.limit_exceptional
    for sec in sectors.values():  # sector momentum: mean-reverting random walk
        sec.momentum = max(-0.01, min(0.01, sec.momentum * 0.8 + rng.gauss(0, 0.003)))
    total_ret = 0.0
    for c in companies:
        crng = random.Random(f"{settings.seed}:{st.cycle_no}:{c.ticker}")  # deterministic per cycle/company
        sec = sectors[c.sector_id]
        applied: set[int] = set()
        news = 0.0
        for e in active:  # each event applied at most once per company per cycle
            if e.id not in applied and _matches(e, c, sec.name):
                news += e.impact
                applied.add(e.id)
        liquidity = max(c.total_shares * 0.01, 1)
        inputs = dict(
            sector=sec.momentum,
            company=c.growth_rate * 0.0001 + (c.reputation - 50) / 50 * 0.001 - (0.001 if c.status == "DISTRESSED" else 0)
            + max(-0.08, min(0.08, (float(c.profit / c.revenue) if c.revenue and c.revenue > 0 else 0.03) - 0.03)) * 0.02,
            news=news, sentiment=st.sentiment * 0.01,
            pressure=max(-0.02, min(0.02, c.pressure / liquidity * 0.02)),
            noise=crng.gauss(0, c.volatility), events=sorted(applied), limit=limit)
        raw = sum(inputs[k] for k in ("sector", "company", "news", "sentiment", "pressure", "noise"))
        ret = max(-limit, min(limit, raw))
        c.prev_close = c.price
        new_price = (c.price * Decimal(str(1 + ret))).quantize(Decimal("0.0001"))
        c.price = max(new_price, FLOOR)
        c.pressure, c.volume = 0, 0
        inputs.update(raw=raw, clamped=ret)
        s.add(PriceHistory(company_id=c.id, cycle_no=st.cycle_no, price=c.price, ret=ret, inputs=inputs))
        total_ret += ret
    avg = total_ret / max(len(companies), 1)
    st.sentiment = max(-1.0, min(1.0, st.sentiment * 0.9 + avg * 20))
    for e in active:  # tick down + expire
        if e.start_cycle < st.cycle_no or e in new_events:
            e.remaining -= 1
        if e.remaining <= 0:
            e.status = "EXPIRED"
    mcap = sum(c.price * c.total_shares for c in companies)
    if st.index_base is None:
        st.index_base = mcap
    st.index_value = (mcap / st.index_base * 1000).quantize(Decimal("0.01"))
    st.last_cycle_at = datetime.now(timezone.utc)
    s.add(MarketSnapshot(cycle_no=st.cycle_no, index_value=st.index_value, status=status))
    fin_events = await run_financials(s, st) if st.cycle_no % settings.fin_every_cycles == 0 else []
    return {"ran": True, "status": status, "cycle": st.cycle_no, "index": st.index_value, "fin_events": fin_events,
            "new_events": [(e.headline, e.description, e.severity, e.impact, e.duration, e.sectors, e.tickers, e.event_type) for e in new_events]}


async def run_financials(s: AsyncSession, st: MarketState) -> list[dict]:
    """Simulated company financial cycle ('quarter'): revenue growth, margins, profit/loss, distress and bankruptcy."""
    C = Decimal("0.01")
    out = []
    cs = (await s.execute(select(Company).where(Company.status != "BANKRUPT").with_for_update())).scalars().all()
    for c in cs:
        r = random.Random(f"{settings.seed}:fin:{st.cycle_no}:{c.ticker}")
        rev = c.revenue if c.revenue > 0 else max(c.cash * Decimal("0.10"), Decimal(100000))
        growth = c.growth_rate / 100 * 0.05 + (c.reputation - 50) / 1000 * 0.02 + r.gauss(0, 0.02)
        rev = max(Decimal(100000), (rev * Decimal(str(1 + growth))).quantize(C))
        debt_ratio = min(float(c.debt / rev), 1.0)
        margin = max(-0.4, min(0.4, 0.03 + (c.reputation - 50) / 400 - debt_ratio * 0.05 + r.gauss(0, 0.05)))
        c.revenue, c.profit = rev, (rev * Decimal(str(margin))).quantize(C)
        if c.owner_id is None:
            continue  # NPC companies: reported numbers only, no cash flows
        c.cash += c.profit
        c.neg_cycles = c.neg_cycles + 1 if c.cash <= 0 else 0
        low = c.cash < rev * Decimal("0.5")
        if low:
            c.reputation = max(0, c.reputation - 2)
        if low and c.status == "ACTIVE":
            c.status = "DISTRESSED"; out.append(dict(ticker=c.ticker, owner=c.owner_id, kind="DISTRESSED"))
        elif not low and c.status == "DISTRESSED":
            c.status = "ACTIVE"; out.append(dict(ticker=c.ticker, owner=c.owner_id, kind="RECOVERED"))
        if c.neg_cycles >= settings.bankrupt_after_cycles:
            c.status, c.listing, c.price, c.prev_close = "BANKRUPT", "DELISTED", Decimal("0.01"), c.price
            out.append(dict(ticker=c.ticker, owner=c.owner_id, kind="BANKRUPT"))
    return out


async def force_event(s: AsyncSession, key: str) -> MarketEvent | None:
    st = (await s.execute(select(MarketState).where(MarketState.id == 1))).scalar_one()
    t = next((x for x in TEMPLATES if x["key"] == key), None)
    if not t:
        return None
    tickers, headline, desc = [], t["headline"], t["desc"]
    if t["type"] == "COMPANY":
        c = (await s.execute(select(Company).order_by(Company.id).limit(1))).scalar_one()
        tickers, headline, desc = [c.ticker], headline.format(ticker=c.ticker, name=c.name), desc.format(name=c.name, ticker=c.ticker)
    ev = MarketEvent(template_key=key, headline=headline, description=desc, event_type=t["type"], severity=t["sev"],
                     sectors=t["sectors"], tickers=tickers, impact=t["impact"], duration=t["dur"], remaining=t["dur"],
                     start_cycle=st.cycle_no, cooldown_until=st.cycle_no + t["dur"] + t["cd"])
    s.add(ev)
    await s.flush()
    return ev
