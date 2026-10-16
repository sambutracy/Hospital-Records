FROM node:22-bookworm-slim AS frontend-build
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# Optional, cached CI/test target; excluded from the default app image.
FROM frontend-build AS frontend-test
RUN npm test -- --run --maxWorkers=1

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN python -m pip install --no-cache-dir --upgrade pip==26.2.1 \
    && python -m pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/
COPY --from=frontend-build /frontend/dist/ ./src/static/comfort/
COPY data/ ./data/
RUN DEMO_MODE=1 USE_SQLITE=1 DJANGO_SECRET_KEY=static-build-only python src/manage.py collectstatic --noinput \
    && useradd --create-home --uid 10001 app
USER app
EXPOSE 8000
CMD ["python", "src/tools/start_app.py"]
