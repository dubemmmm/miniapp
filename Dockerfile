# ============
# Base Image
# ============
FROM python:3.11-slim

# Prevent Python from buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get clean

# Copy project
COPY . .

# Collect static (optional: you may do this in CI)
RUN python manage.py collectstatic --noinput

EXPOSE 80

# Gunicorn command - changed to port 80
CMD ["gunicorn", "miniapp.wsgi:application", "--bind", "0.0.0.0:80"]