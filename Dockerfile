# Official Playwright image: Python, Chromium and its system libraries preinstalled.
FROM mcr.microsoft.com/playwright/python:v1.63.0-noble

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HEADLESS=true

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# API by default; the worker service overrides the command with: python -m worker
CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
