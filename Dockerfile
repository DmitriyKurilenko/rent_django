FROM node:20-alpine AS assets

WORKDIR /app

COPY package.json tailwind.config.js ./
COPY assets ./assets
COPY templates ./templates
COPY boats ./boats
COPY accounts ./accounts
COPY static ./static

RUN npm install --no-audit --no-fund \
    && npm run build:css

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    postgresql-client \
    gettext \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Установка Python зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование проекта
COPY . .

# Копирование собранного CSS из assets stage
COPY --from=assets /app/static/css/styles.css /app/static/css/styles.css

# Создание директорий
RUN mkdir -p /app/staticfiles /app/mediafiles /app/media/boats

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=30s \
    CMD curl -sf http://localhost:8000/health/ || exit 1
