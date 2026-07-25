FROM python:3.12-alpine

RUN apk add --no-cache gcc musl-dev libffi-dev

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8082

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -qO- http://localhost:8082/api/health || exit 1

USER nobody

CMD ["gunicorn", "--bind", "0.0.0.0:8082", "--workers", "2", "--timeout", "120", "app:app"]
