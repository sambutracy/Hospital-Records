FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/
RUN DEMO_MODE=1 USE_SQLITE=1 DJANGO_SECRET_KEY=static-build-only python src/manage.py collectstatic --noinput \
    && useradd --create-home --uid 10001 app
USER app
EXPOSE 8000
CMD ["python", "src/tools/start_app.py"]
