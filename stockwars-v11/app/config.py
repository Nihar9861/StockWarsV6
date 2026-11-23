from decimal import Decimal
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    bot_token: str = ""
    owner_ids: str = ""
    database_url: str = "postgresql+asyncpg://stockwars:stockwars@localhost:5432/stockwars"
    redis_url: str = "redis://localhost:6379/0"
    news_channel_id: str = ""
    market_open: str = "09:00"
    market_close: str = "23:00"
    tz_display: str = "Asia/Kolkata"
    cycle_minutes: int = 5
    trading_fee_pct: Decimal = Decimal("0.0025")
    start_cash: Decimal = Decimal("1000000")
    auto_create_tables: int = 1
    seed: str = "stockwars"
    # price limits per cycle
    limit_normal: float = 0.05
    limit_strong: float = 0.12
    limit_exceptional: float = 0.20
    max_active_events: int = 3
    min_active_events: int = 1
    event_rate: float = 2.0
    event_duration_mult: int = 2
    webapp_url: str = ""
    company_fee: Decimal = Decimal("50000")
    min_capital: Decimal = Decimal("500000")
    max_companies_per_player: int = 3
    ipo_fee: Decimal = Decimal("150000")
    ipo_min_age_hours: int = 24
    ipo_min_reputation: int = 50
    ipo_min_valuation: Decimal = Decimal("500000")
    ipo_max_public_pct: float = 0.49
    ipo_requires_approval: int = 0
    div_min_reputation: int = 50
    div_cooldown_hours: int = 24
    div_record_minutes: int = 60
    div_pay_delay_minutes: int = 30
    div_max_cash_pct: float = 0.5
    fin_every_cycles: int = 12
    bankrupt_after_cycles: int = 12
    snapshot_every_cycles: int = 3
    offer_ttl_minutes: int = 30
    offer_price_band: float = 0.10
    notify_max_per_hour: int = 6
    daily_reward: Decimal = Decimal("10000")
    battle_min_players: int = 2
    battle_max_players: int = 6
    battle_prize_min_players: int = 3
    battle_daily_reward_budget: Decimal = Decimal("500000")
    max_open_orders: int = 10
    loan_max: Decimal = Decimal("1000000")
    loan_rate_per_day: Decimal = Decimal("0.015")
    loan_late_fee_pct: Decimal = Decimal("0.05")
    loan_default_after_days: int = 3

    @field_validator("database_url", mode="before")
    @classmethod
    def _fix_db(cls, v: str) -> str:  # Railway gives postgres:// / postgresql://
        if v.startswith("postgres://"):
            v = "postgresql://" + v[len("postgres://"):]
        if v.startswith("postgresql://"):
            v = "postgresql+asyncpg://" + v[len("postgresql://"):]
        return v.split("?sslmode")[0]

    @property
    def owners(self) -> set[int]:
        return {int(x) for x in self.owner_ids.split(",") if x.strip()}


settings = Settings()
