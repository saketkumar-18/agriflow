FROM python:3.11-slim
WORKDIR /srv/api
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# Context is the REPO ROOT (Render builds with root context; docker-compose sets context: . )
COPY services/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt psycopg2-binary==2.9.10
COPY services/api/app ./app
COPY services/api/alembic.ini ./
COPY services/api/alembic ./alembic
RUN useradd -m api && mkdir -p /srv/api/data && chown -R api /srv
USER api
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=4)" || exit 1
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
