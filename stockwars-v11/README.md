# STOCK WARS

## Deploy on Railway
1. Push this folder to a GitHub repo → Railway → **New Project → Deploy from GitHub**. It builds from `Dockerfile` (`railway.json` included).
2. In the same project add **PostgreSQL** and **Redis** (+ New → Database).
3. App service → **Variables**:
   - `BOT_TOKEN` = token from @BotFather
   - `OWNER_IDS` = your Telegram user ID (auto-admin)
   - `DATABASE_URL` = `${{Postgres.DATABASE_URL}}`
   - `REDIS_URL` = `${{Redis.REDIS_URL}}`
   - `WEBAPP_URL` = your public URL (step 4)
   - optional: `NEWS_CHANNEL_ID` (bot must be channel admin), `IPO_REQUIRES_APPROVAL=1`, `IPO_MIN_AGE_HOURS=0` for testing
4. App service → **Settings → Networking → Generate Domain**, paste it into `WEBAPP_URL`, redeploy.
5. Keep **1 replica** (bot uses polling). Tables are created automatically on first boot (`AUTO_CREATE_TABLES=1`).
6. Open the bot → /start. Owner is auto-approved; others /register → you /approve <id>.

## Local
`cp .env.example .env` → `docker compose up --build`

## Bot commands
Players: /start /register /profile /market /stocks /stock /buy /sell /portfolio /history /news /leaderboard /mycompany /ipos /loan /repay /dividends
Admin: /pending /approve /reject /suspend /unsuspend /ban /unban /playerinfo /addcash /removecash /marketpause /marketresume /forceevent <key> /stop_event <id> /approveipo <id> /rejectipo <id> /audit

## Database migrations
- Default (`AUTO_CREATE_TABLES=1`): tables are created and any *new columns* are added automatically on boot. Nothing to run.
- Alembic baseline is in `migrations/versions/0001_baseline.py`.
  - Fresh database: set `AUTO_CREATE_TABLES=0`, run `alembic upgrade head`.
  - Existing database created by auto-create: run `alembic stamp head` once, then use `alembic revision --autogenerate` for future changes.

## New env vars (all optional)
`FIN_EVERY_CYCLES=12` (company financial cycle), `BANKRUPT_AFTER_CYCLES=12`, `SNAPSHOT_EVERY_CYCLES=3`, `OFFER_TTL_MINUTES=30`, `NOTIFY_MAX_PER_HOUR=6`, `DAILY_REWARD=10000`
Extra bot command: /notify all|company|sector|major|none

## Limit orders
/limitbuy TICKER QTY PRICE [days] · /limitsell TICKER QTY PRICE [days] · /orders · /cancelorder ID (also in Mini App: stock → Buy/Sell → Limit, Portfolio → Orders). Checked after every market cycle.

## Portfolio Battle
/battle /battlecreate [quick|daily|weekly|sector Technology,Banking] /battlejoin CODE /battleleave /battlestart /battleportfolio /battlemarket /battlebuy /battlesell /battleleaderboard /battleresult /battlehistory — also the Arena tab in the Mini App.
Env: BATTLE_MIN_PLAYERS=2, BATTLE_MAX_PLAYERS=6, BATTLE_PRIZE_MIN_PLAYERS=3, BATTLE_DAILY_REWARD_BUDGET=500000
