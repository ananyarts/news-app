# Dockerfile for The Daily Brief (Django news application).
#
# Build:  docker build -t daily-brief .
# Run:    docker run -p 8000:8000 daily-brief
#
# The container uses SQLite by default so it runs anywhere (including
# Docker Playground) without a database server. Pass -e DB_ENGINE=mariadb
# and the DB_* variables to use MariaDB instead.

FROM python:3.14-slim

# Don't write .pyc files and send output straight to the container logs.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DB_ENGINE=sqlite \
    DJANGO_DEBUG=True \
    DJANGO_ALLOWED_HOSTS=*

WORKDIR /app

# Build tools and MariaDB client headers are needed to compile mysqlclient.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential pkg-config default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first so this layer is cached between code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Create/update the database tables, then start the development server on
# all interfaces so it can be reached from outside the container.
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py runserver 0.0.0.0:8000"]
