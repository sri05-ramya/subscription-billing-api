# 1. Start from a small Linux image with Python 3.11
FROM python:3.11-slim

# Don't create .pyc files, and show logs immediately
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 2. Install packages first (Docker caches this step, so rebuilds are fast)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. Copy our code
COPY app ./app
COPY scripts ./scripts

# 4. Run as a normal user instead of root (safer)
RUN useradd --create-home appuser
USER appuser

# 5. Start the API
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]