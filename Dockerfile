FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY doctracker ./doctracker
RUN useradd --create-home appuser && mkdir -p /app/data && chown appuser /app/data
USER appuser
ENV PYTHONUNBUFFERED=1 PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn doctracker.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
