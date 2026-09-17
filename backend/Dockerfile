FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .
RUN useradd --create-home meridian && mkdir -p /app/data/uploads && chown -R meridian:meridian /app
USER meridian
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && python -m app.bootstrap_invite && python -m app.bootstrap_admin && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
