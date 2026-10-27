# ---- Stage 1: build the React frontend ----
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build
# vite.config.js outputs directly to ../backend/static

# ---- Stage 2: Python backend, serving API + built frontend ----
# The v4 model is pure Python (coefficients in model.json): no compiler, numpy, scikit-learn or xgboost needed.
FROM python:3.12-slim
WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/artifacts ./artifacts
COPY --from=frontend-build /app/backend/static ./static

ENV ARTIFACT_DIR=/app/artifacts PYTHONUNBUFFERED=1

# Run as an unprivileged user
RUN useradd --system --uid 10001 --no-create-home appuser
USER appuser

EXPOSE 8000
# Azure App Service (Linux containers) routes traffic to port 80 by default —
# set the app setting WEBSITES_PORT=8000 so it forwards correctly here.
CMD ["sh", "-c", "gunicorn app.main:app --bind 0.0.0.0:${PORT:-8000} --worker-class uvicorn.workers.UvicornWorker --workers 1 --timeout 120"]
