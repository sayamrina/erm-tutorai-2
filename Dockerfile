# 1) build the React frontend
FROM node:22-alpine AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# 2) render the lecture slides to images for the source panel
FROM python:3.12-slim AS slides
WORKDIR /app
RUN pip install --no-cache-dir pypdfium2==5.14.0 pillow==13.0.0
COPY backend/app ./app
COPY backend/data/materials ./data/materials
RUN python -m app.slides

# 3) run the FastAPI backend, which also serves the built frontend
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY backend/data/chunks.json ./data/
COPY --from=frontend /src/backend/static ./static
COPY --from=slides /app/data/slides ./data/slides
RUN useradd --create-home appuser && chown -R appuser /app/data
USER appuser
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
