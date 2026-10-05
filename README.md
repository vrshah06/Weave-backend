# Weave Reminder Backend

Sends appointment reminder SMS through the Weave web app. Staff import a CSV of appointments; a background worker drives Weave with Playwright and messages each pending appointment, recording every step.

```
CSV ──▶ API (/api/v1) ──▶ MongoDB ◀── Worker ──▶ Weave (Playwright/Chromium)
                         patients, appointments, imports,
                         runs, run_items, run_logs, screenshots
```

- **API** (`app.py`): FastAPI. Imports CSVs, lists appointments, queues runs, streams run progress. Never touches the browser.
- **Worker** (`python -m worker`): claims queued runs one at a time, drives Weave, and writes results, logs and failure screenshots to MongoDB. Exactly one worker holds the browser lock at a time.

## How it behaves

| Topic | Rule |
|---|---|
| Patient identity | Name + phone. Phones are normalised to E.164 (`772-637-9314` → `+17726379314`); `Doe, Jane` and `Jane Doe` are the same person. |
| Appointment identity | Patient + date + time. Each slot gets its own reminder. |
| Re-importing a date | **Syncs that date.** New rows are created; rows missing from the new file are `CANCELLED` (sent ones are never touched). |
| Runs | One run = every `PENDING`, non-excluded appointment on a date. Extra runs wait in a queue. Past dates are rejected. |
| Dry run | Opens each conversation, types the reminder, verifies it, then clears it. **Never changes appointment status.** |
| Recipient check | The exact phone is selected in Weave's search, and the conversation header must show that number. Names are not compared (they often differ from Weave). |
| Uncertain send | If Send was clicked but delivery cannot be confirmed, the appointment becomes `NEEDS_REVIEW` and is **never** retried automatically. |
| Stop | Queued runs are cancelled; a running run finishes the current patient, then stops. |
| Crash safety | Appointments are atomically claimed (`PENDING` → `SENDING`) right before Send. If the worker dies, recovery marks them `NEEDS_REVIEW`. |
| Real sending | Only when the worker has `SENDING_ENABLED=true`. |

Appointment statuses: `PENDING`, `SENDING`, `SENT`, `FAILED`, `SKIPPED`, `NEEDS_REVIEW`, `CANCELLED`.
Run statuses: `QUEUED`, `RUNNING`, `COMPLETED`, `STOPPED`, `CANCELLED`, `FAILED`, `INTERRUPTED`.

## Project structure

```
app.py                    API entry point
worker/                   python -m worker: loop, run executor, crash recovery, per-run logger
automation/               driver.py (interface), weave_driver.py (Playwright), weave_selectors.py (verified selectors)
routes/                   /api/v1 endpoint declarations
controllers/              request/response mapping, SSE stream
services/                 business rules (imports, runs, settings, message templates)
repositories/             all MongoDB access, one module per collection
models/                   enums and API schemas (camelCase JSON)
core/                     config, database, errors, API key, logging
utils/                    CSV parsing, phone/name/date helpers
scripts/seed_sent_history.py   one-time import of the legacy logs/reminder_log.csv
tests/                    pytest suite (needs a MongoDB; see below)
```

## Local development

```bash
python3.13 -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt
python -m playwright install chromium
cp .env.example .env          # set MONGODB_URI, API_KEY, WEAVE_EMAIL, WEAVE_PASSWORD

uvicorn app:app --reload --port 8000     # API  → http://localhost:8000/docs
python -m worker                          # worker (separate terminal)
```

Use port 8000: on macOS, port 5000 is taken by AirPlay Receiver.

To watch the browser while developing, set `HEADLESS=false`. The saved Weave session lives in `BROWSER_PROFILE_DIR`.

### Tests

The tests run against a real MongoDB (GridFS, unique indexes, atomic claims):

```bash
docker run -d --name weave-test-mongo -p 127.0.0.1:27018:27017 mongo:7
pytest
```

Override the location with `TEST_MONGODB_BASE_URI`. Each test uses a fresh, randomly named database. The Weave driver itself is exercised with real dry runs, not unit tests.

## API (v1)

Every endpoint except `/health` needs the `X-API-Key` header. The SSE and screenshot endpoints also accept `?apiKey=`, because browsers can't set headers on `EventSource` or `<img>`. Errors always look like `{"error": {"code", "message", "details?"}}`. Interactive docs: `/docs`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/health` | Database and worker status (no key) |
| POST | `/api/v1/imports` | Upload CSV (`multipart/form-data`, field `file`); returns per-row results and cancelled appointments |
| GET | `/api/v1/imports`, `/api/v1/imports/{id}` | Import history |
| GET | `/api/v1/appointments?date=YYYY-MM-DD&status=` | Appointments on a date |
| GET | `/api/v1/appointments/dates` | Dates with appointments |
| GET | `/api/v1/appointments/{id}` | One appointment |
| POST | `/api/v1/appointments/exclusions` | `{appointmentIds, excluded}`: leave out of runs |
| POST | `/api/v1/appointments/requeue` | FAILED/SKIPPED/NEEDS_REVIEW → PENDING |
| POST | `/api/v1/appointments/mark-sent` | NEEDS_REVIEW → SENT after checking Weave |
| GET | `/api/v1/patients?search=`, `/api/v1/patients/{id}`, `/api/v1/patients/{id}/appointments` | Patients |
| POST | `/api/v1/runs` | `{appointmentDate, mode: "DRY_RUN" \| "SEND"}` → queued run (202) |
| GET | `/api/v1/runs`, `/api/v1/runs/latest`, `/api/v1/runs/{id}` | Runs (`latest` is 404 when none exist) |
| POST | `/api/v1/runs/{id}/stop` | Cancel or stop a run |
| GET | `/api/v1/runs/{id}/items` | Per-appointment outcomes, with `screenshotUrl` on failures |
| GET | `/api/v1/runs/{id}/logs?after=` | Run log lines |
| GET | `/api/v1/runs/{id}/events` | SSE: `log`, `run`, final `end` events; supports `Last-Event-ID` |
| GET | `/api/v1/runs/{id}/screenshots/{screenshotId}` | Failure screenshot (PNG) |
| GET/PUT | `/api/v1/settings`, GET `/api/v1/settings/message-preview` | Business name, SMS template, time zone |

SMS template placeholders: `{patient_name}`, `{first_name}`, `{last_name}`, `{appointment_date}`, `{appointment_time}`, `{provider}`, `{business_name}`.

### Migrating the frontend from the old API

| Old | New |
|---|---|
| `POST /api/import/csv` | `POST /api/v1/imports` |
| `GET /api/appointments?date=` | `GET /api/v1/appointments?date=` (date is required) |
| `POST /api/appointments/selection {appointmentIds, selected}` | `POST /api/v1/appointments/exclusions {appointmentIds, excluded: !selected}` |
| `POST /api/automation/start {mode: "send"\|"dry_run", date}` | `POST /api/v1/runs {mode: "SEND"\|"DRY_RUN", appointmentDate}` |
| `POST /api/automation/stop` | `POST /api/v1/runs/{id}/stop` |
| `GET /api/automation/status` | `GET /api/v1/runs/latest` |
| `GET /api/automation/events` | `GET /api/v1/runs/{id}/events?apiKey=…` |
| `GET /api/automation/runs[/id]` | `GET /api/v1/runs[/id]` + `/items` + `/logs` |
| `POST /api/automation/retry` | `POST /api/v1/appointments/requeue`, then `POST /api/v1/runs` |
| `/api/automation/confirmations/*` | removed |
| `GET /api/patients/{id}/history` | `GET /api/v1/patients/{id}/appointments` |
| `PATCH /api/settings` | `PUT /api/v1/settings` |
| `X-Workspace-ID` header | removed; send `X-API-Key` instead |

## Deployment (Render)

`render.yaml` defines two Docker services built from the same `Dockerfile`, which is based on Microsoft's Playwright image so Chromium and its libraries are preinstalled:

- **weave-api**: web service, health check `/api/v1/health`.
- **weave-worker**: background worker (`python -m worker`) with a 1 GB disk at `/data` that keeps the Weave login session across deploys.

1. **Database.** Create a MongoDB Atlas database, e.g. `weave_reminders`. Allow Render's outbound IPs (or `0.0.0.0/0` with a strong password). The URI must include the database name: `mongodb+srv://user:pass@cluster/weave_reminders?retryWrites=true`.
2. **Blueprint.** In Render, choose New → Blueprint and select this repo. When prompted, fill in:
   - `MONGODB_URI`, in the `weave-shared` group;
   - `CORS_ORIGINS`, your frontend URL(s);
   - `WEAVE_EMAIL` and `WEAVE_PASSWORD`, on the worker.

   `API_KEY` is generated automatically; copy it from the weave-api environment into your frontend's server-side config.
3. **Deploy.** Both services start, and indexes are created automatically. `GET https://<api>/api/v1/health` should return `"database": "up", "worker": "online"`.
4. **Seed send history (once).** Locally, with `MONGODB_URI` pointing at production: `python -m scripts.seed_sent_history` (report), then `--apply`. This marks reminders the old system already sent as `SENT` so they are never re-sent.
5. **First login.** The worker logs in with `WEAVE_EMAIL`/`WEAVE_PASSWORD` and saves the session on the disk. If Weave asks for a verification code, the run fails with a clear error. In that case, log in once with a visible browser locally (`HEADLESS=false`) and upload that profile, or ask Weave support to disable verification for this account.
6. **Dry run in production.** Import a CSV for an upcoming date, `POST /api/v1/runs {"mode": "DRY_RUN"}`, and check `/runs/{id}/items`: every item should be `DRY_RUN_VERIFIED`.
7. **Enable sending.** Set `SENDING_ENABLED=true` on weave-worker (it redeploys). Start with one appointment by excluding the rest, confirm the SMS in Weave, then run whole days.

Operational notes:
- Ideally give the worker its **own Weave user** with the softphone disabled. With a softphone-enabled user, the worker's browser registers as an extra, inactive softphone. It uses a silent fake microphone so Weave's "Microphone Access" pop-up never blocks it, and calls stay on your staff's softphone.
- Run **one** worker instance. The MongoDB lock prevents two browsers from driving Weave, but a second instance would only sit idle.
- Deploying the worker during a run finishes the current patient, marks the run `INTERRUPTED`, and leaves the remaining appointments `PENDING`. Queue the date again afterwards.
- Check `NEEDS_REVIEW` appointments in Weave, then `mark-sent` or `requeue` them.
