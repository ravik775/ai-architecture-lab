FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

RUN addgroup --system expense-ai \
    && adduser --system --ingroup expense-ai expense-ai \
    && mkdir -p /data/chroma \
    && chown -R expense-ai:expense-ai /app /data/chroma

COPY --chown=expense-ai:expense-ai . .

USER expense-ai


CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]