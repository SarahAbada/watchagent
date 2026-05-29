FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_PATH=/app/data/weather.db \
    LOG_DIR=/app/logs \
    POLL_INTERVAL_SECONDS=300

RUN mkdir -p /app/data /app/logs

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000

CMD ["python", "-m", "app.main"]
