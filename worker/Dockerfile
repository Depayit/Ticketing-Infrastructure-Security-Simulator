FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium && playwright install-deps chromium

COPY bot.py .
COPY stealth.py .
COPY config.json .
COPY ai_recovery.py .
COPY core/ ./core/
COPY browser/ ./browser/
COPY flows/ ./flows/
COPY ai/ ./ai/

CMD ["python", "bot.py"]
