FROM python:3.12-slim
WORKDIR /app
COPY backend/ backend/
COPY frontend/dist/ frontend/dist/
RUN pip install --no-cache-dir -r backend/requirements.txt
WORKDIR /app/backend
EXPOSE 8787
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8787}
