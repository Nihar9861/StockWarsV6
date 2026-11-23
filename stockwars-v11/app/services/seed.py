import random
from decimal import Decimal
from sqlalchemy import func, select
from ..config import settings
from ..models import Company, MarketState, Sector

DATA = {
 "Technology": [("NovaByte Systems","NVBY"),("QuantumLeaf Software","QLFS"),("PixelForge Labs","PXFG")],
 "Artificial Intelligence": [("NeuroSphere AI","NRSP"),("Cognitra Dynamics","CGTD"),("SynapseWorks","SYNW")],
 "Banking": [("Meridian Trust Bank","MRTB"),("Crestline Capital","CRCP"),("Ironvault Financial","IRVF")],
 "Energy": [("SolarisGrid Power","SLGP"),("Petrovia Oil & Gas","PTVG"),("WindCrest Energy","WNDC")],
 "Healthcare": [("VitaCure Pharma","VTCR"),("HelixMed Labs","HLXM"),("CarePulse Hospitals","CPLS")],
 "Automobile": [("Veloxa Motors","VLXM"),("TorqueWorks Auto","TRQW"),("ElectraDrive","EDRV")],
 "FMCG": [("FreshNest Foods","FRNS"),("HomeBloom Products","HMBL"),("GoldenGrain Co","GGRN")],
 "Telecommunications": [("SignalWave Telecom","SGWV"),("Orbitel Networks","ORBT"),("LinkSphere Comms","LNKS")],
 "Real Estate": [("Skyline Habitat","SKHB"),("UrbanNest Realty","URBN"),("TerraHomes","TRHM")],
 "Infrastructure": [("BridgeMark Infra","BRMK"),("Titanbuild Construction","TTBL"),("RailNova Projects","RLNV")],
 "Entertainment": [("StarReel Studios","STRL"),("PlayVerse Games","PLVR"),("BeatBox Media","BTBX")],
 "Mining": [("DeepRock Minerals","DPRK"),("Ironcrest Mining","IRCM"),("AuraGold Resources","ARGD")],
}
SECTOR_VOL = {"Technology": .012, "Artificial Intelligence": .016, "Banking": .008, "Energy": .012, "Healthcare": .010,
              "Automobile": .011, "FMCG": .006, "Telecommunications": .008, "Real Estate": .010,
              "Infrastructure": .009, "Entertainment": .014, "Mining": .013}
CEOS = ["Arjun Mehta", "Riya Kapoor", "Vikram Sethi", "Anaya Rao", "Kabir Malhotra", "Isha Nair", "Rohan Bajaj", "Tara Iyer"]


# Low-priced (penny-style) stocks: ₹5–60, higher volatility
LOW = {
 "Technology": ("ByteNest", "BYNT"), "Artificial Intelligence": ("DataMint AI", "DTMT"), "Banking": ("PennyTrust Bank", "PNTR"),
 "Energy": ("SunDrop Energy", "SNDR"), "Healthcare": ("MediSpark", "MDSP"), "Automobile": ("ZippyRide Motors", "ZPRD"),
 "FMCG": ("SnackBox Foods", "SNBX"), "Telecommunications": ("PingNet", "PNGN"), "Real Estate": ("BrickLane Homes", "BRKL"),
 "Infrastructure": ("RoadRise Infra", "RDRS"), "Entertainment": ("ReelBuzz Media", "RLBZ"), "Mining": ("GemDust Minerals", "GMDS"),
}


async def seed(s):
    """Idempotent: creates any missing sector/company, so new stocks appear on the next deploy."""
    secs = {x.name: x for x in (await s.execute(select(Sector))).scalars()}
    for n in DATA:
        if n not in secs:
            secs[n] = Sector(name=n); s.add(secs[n])
    await s.flush()
    have = set((await s.execute(select(Company.ticker))).scalars())
    st = await s.get(MarketState, 1)
    old_mcap = sum((c.price * c.total_shares for c in (await s.execute(select(Company).where(Company.listing == "LISTED"))).scalars()), Decimal(0))
    added = Decimal(0)
    plan = [(sn, n, t, False) for sn, cs in DATA.items() for n, t in cs] + [(sn, n, t, True) for sn, (n, t) in LOW.items()]
    for sname, name, tick, low in plan:
        if tick in have:
            continue
        r = random.Random(f"{settings.seed}:{tick}")
        price = (Decimal(r.randint(500, 6000)) / 100 if low else Decimal(r.randint(50, 1500))).quantize(Decimal("0.0001"))
        vol = SECTOR_VOL[sname] * r.uniform(0.8, 1.3) * (1.5 if low else 1)
        shares = r.randint(5, 20) * 1_000_000 if low else r.randint(1, 10) * 1_000_000
        s.add(Company(name=name, ticker=tick, sector_id=secs[sname].id, ceo=r.choice(CEOS),
                      description=f"{name} is a fictional {sname} company" + (" (low-priced stock)." if low else "."),
                      total_shares=shares, price=price, prev_close=price,
                      revenue=Decimal(r.randint(50, 900)) * 10_000_000, profit=Decimal(r.randint(-5, 120)) * 1_000_000,
                      debt=Decimal(r.randint(0, 300)) * 1_000_000, reputation=r.randint(40, 85), growth_rate=r.uniform(-2, 12),
                      volatility=vol, risk_level="HIGH" if vol > .013 else "LOW" if vol < .008 else "MEDIUM"))
        added += price * shares
    if st is None:
        s.add(MarketState(id=1))
    elif st.index_base is not None and added > 0 and old_mcap > 0:
        st.index_base = st.index_base * (old_mcap + added) / old_mcap  # keep the index continuous
