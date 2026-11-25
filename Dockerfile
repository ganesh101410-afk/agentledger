FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app

RUN useradd --system --uid 10001 --no-create-home app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY main.py .
COPY core ./core
COPY static ./static
COPY scripts/healthcheck.py ./scripts/healthcheck.py

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 CMD ["python", "scripts/healthcheck.py"]

CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
