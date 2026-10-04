# Weave Backend & Automation Service

FastAPI API server and Playwright automation engine for Weave appointment reminders. This repo is API-only; the frontend is deployed separately.

## Features
- **REST API** (`/api/*`): CSV import, appointments, patients, automation runs, message history, settings.
- **Live run updates**: Server-Sent Events at `GET /api/automation/events`.
- **Automation engine**: Playwright drives Weave message composition and delivery (`run_reminders.py`, run as a subprocess per run).
- **Deduplication & header verification** to prevent misdirected messages.

## Tech Stack
- Python 3.10+, FastAPI, Uvicorn, Motor (MongoDB), Playwright

## Setup

```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium
cp .env.example .env              # then fill in MONGODB_URI, WEAVE_EMAIL, WEAVE_PASSWORD
```

## Running

```bash
# Development (auto-reload)
uvicorn app:app --reload --port 5000

# Production
uvicorn app:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips='*'
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

## Project Structure
Requests flow `routes → controllers → services → repositories → MongoDB`.

```
app.py                     FastAPI app: CORS, error handlers, router mount
run_reminders.py           Automation CLI; spawned once per run by the API
core/
  config.py                Environment-driven settings
  database.py              MongoDB (Motor) client
  event_stream.py          SSE publish/subscribe
  exceptions.py            Domain errors (mapped to HTTP codes in app.py)
routes/                    Endpoint declarations only (paths, params, dependencies)
controllers/               Request parsing and response envelopes
services/                  Business logic
  automation_runner.py     Spawns run_reminders.py, turns its [EVENT] output into DB updates + SSE events
repositories/              All MongoDB queries, one module per collection
utils/                     Pure helpers (CSV parsing, formatting)
automation/                Playwright engine
  browser_manager.py       Chromium lifecycle
  weave_messenger.py       Weave UI navigation and message sending
  message_templates.py     Reminder text generation
  validation.py            Row/phone validation, dedup keys
  deduplication.py         Prevents duplicate reminders (logs/reminder_log.csv)
  models.py                Dataclasses and status enums
  logging_utils.py         Logger, phone masking, error screenshots
tests/                     pytest suite
```

## Run the automation CLI directly (optional)
```bash
python run_reminders.py --dry-run --file data/appointments.csv   # compose & verify, no send
python run_reminders.py --send --file data/appointments.csv      # send
```

## Tests
```bash
python -m pytest tests/ -v
```
