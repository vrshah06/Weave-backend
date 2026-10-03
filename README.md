# Weave Backend & Automation Service

Node.js (Express + Socket.io) API Backend server & Playwright Python Automation Engine for Weave Appointment Reminders.

## Features
- **REST API**: Workspace, Appointment, Patient, Automation run, and Message History endpoints.
- **Real-Time SSE Events**: Live log streaming and state synchronization for frontend dashboards.
- **Python Automation Engine**: Playwright browser automation driving Weave message composition and delivery.
- **Deduplication & Header Verification**: Recipient validation and persistent logging to prevent misdirected messages.
- **Chronological Execution**: Strict ascending time ordering (`8:15 AM` -> `4:15 PM`).

## Tech Stack
- **Node.js**: Express.js, Socket.io, Mongoose (optional MongoDB / In-Memory Adapter)
- **Python**: Playwright, pytest, csv, logging
- **Storage**: Persistent CSV logs (`logs/reminder_log.csv`) & MongoDB / Memory Store

## Requirements
- Node.js (v18+)
- Python (v3.10+) with Playwright:
  ```bash
  pip install -r requirements.txt
  playwright install chromium
  ```

## Setup & Quick Start

### 1. Install Node Dependencies
```bash
npm install
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Ensure `WEAVE_EMAIL` and `WEAVE_PASSWORD` are populated.

### 3. Start Backend Server
```bash
npm start
# Or for development with auto-reload:
npm run dev
```
The server will run on `http://localhost:5000`.

### 4. Run Python CLI Directly (Optional)
```bash
# Dry Run (Compose & verify without sending)
python main.py --dry-run --file data/appointments.csv

# Production Send Mode
python main.py --send --file data/appointments.csv
```

### 5. Run Unit Tests
```bash
python -m pytest tests/ -v
```
