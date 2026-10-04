# Weave Backend & Automation Service

FastAPI (+ Socket.IO / SSE) API server and Playwright automation engine for Weave appointment reminders. This repo is API-only; the frontend is deployed separately.

## Features
- **REST API** (`/api/*`): CSV import, appointments, patients, automation runs, message history, settings.
- **Real-time events**: Socket.IO and Server-Sent Events (`/api/automation/events`).
- **Automation engine**: Playwright drives Weave message composition and delivery (`main.py`, run as a subprocess per run).
- **Deduplication & header verification** to prevent misdirected messages.

## Tech Stack
- Python 3.10+, FastAPI, Uvicorn, python-socketio, Motor (MongoDB), Playwright

## Setup

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env              # then fill in MONGODB_URI, WEAVE_EMAIL, WEAVE_PASSWORD
```

## Running

Always serve `app:sio_app` (the Socket.IO-wrapped app). `app:app` serves the REST API only.

```bash
# Development (auto-reload)
uvicorn app:sio_app --reload --port 5000

# Production
uvicorn app:sio_app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips='*'
```

Health check: `GET /api/health`. Interactive API docs: `/docs`.

## Configuration
See `.env.example`. Key variables:

| Variable | Purpose |
|---|---|
| `MONGODB_URI` | MongoDB connection string |
| `CORS_ORIGINS` | Comma-separated allowed origins (falls back to `FRONTEND_URL`, then `*`) |
| `WEAVE_EMAIL` / `WEAVE_PASSWORD` | Weave account used by the automation |
| `HEADLESS` | Run Chromium headless (`true` in production) |

## Run the automation CLI directly (optional)
```bash
python main.py --dry-run --file data/appointments.csv   # compose & verify, no send
python main.py --send --file data/appointments.csv      # send
```

## Tests
```bash
python -m pytest tests/ -v
```
