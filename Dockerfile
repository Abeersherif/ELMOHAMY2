# ---------- Stage 1: build Angular frontend ----------
FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY angular.json tsconfig*.json ./
COPY .postcssrc.json ./
COPY src ./src
COPY public ./public
RUN npm run build

# ---------- Stage 2: Python runtime ----------
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Create non-root user
RUN groupadd -r mohamy && useradd -r -g mohamy -d /app -s /usr/sbin/nologin mohamy

WORKDIR /app

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY mohamy.py utils.py ./
COPY agents ./agents

# Copy built frontend into /app/static
COPY --from=frontend /build/dist/mahami-masry/browser ./static

# Database path (mount via volume or provide via DB_PATH env)
# law_database.db must be made available at runtime — do NOT bake into image.

RUN chown -R mohamy:mohamy /app
USER mohamy

EXPOSE 7860
ENV PORT=7860

CMD ["sh", "-c", "uvicorn mohamy:app --host 0.0.0.0 --port ${PORT:-7860}"]
