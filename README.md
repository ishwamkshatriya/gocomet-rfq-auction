# British Auction RFQ System

FastAPI + SQLAlchemy backend, React (Vite) frontend. Docs are in `docs/` (`HLD.md` with architecture diagram, `schema.sql`).

## Run

```bash
# backend (http://localhost:8000, docs at /docs)
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload

# frontend (http://localhost:5173, proxies /api to :8000)
cd frontend
npm install
npm run dev
```

Set `DATABASE_URL` (e.g. a PostgreSQL URL) to use another database; default is SQLite (`auction.db`).

## Test

```bash
cd backend && python -m pytest
```

Covers: validation rules, all three triggers, window boundaries, extension cap at the forced close, force-close status, rejected bids, overlapping SQLite bids (no lost extensions or stale supplier validation).

## Quick try

Create an RFQ with start = now, close = +5 min, forced close = +15 min, X = 2, Y = 2. Submit bids in the last two minutes and watch the close time, countdown and activity log update.

Input validation also rejects blank RFQ/carrier names and non-finite charges or totals.
