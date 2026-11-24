FROM python:3.12-slim
WORKDIR /srv/backend
COPY backend/requirements-lock.txt .
RUN pip install --no-cache-dir -r requirements-lock.txt
COPY backend/app ./app
COPY data /srv/data
RUN useradd --uid 10001 --create-home sapar && chown -R sapar:sapar /srv
USER sapar
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
