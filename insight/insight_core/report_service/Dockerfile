# F05-S07 — Cloud Run bridge container.
# Build context is insight_core/ (the parent of this file):
#   docker build -f report_service/Dockerfile -t report-service .
#
# Layout inside the image mirrors the existing local dev layout on purpose —
# insight_core/render_report.js already does
#   require('../insight_receiptgenerator/node_modules/puppeteer')
# and that file is untouched here (F05-S07 is out of scope for pipeline
# changes). So this Dockerfile recreates the sibling relationship instead of
# editing render_report.js: /app/insight_core next to /app/insight_receiptgenerator.

FROM python:3.11-slim

# Chromium runtime deps for headless Puppeteer (--no-sandbox, per render_report.js).
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl gnupg ca-certificates \
        libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 \
        libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2 \
        libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libx11-6 libx11-xcb1 \
        libxcb1 libxext6 libxi6 libxrender1 libxtst6 libglib2.0-0 libdbus-1-3 \
        libexpat1 libfontconfig1 libnspr4 \
        fonts-liberation \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Node side — puppeteer lives at the sibling path render_report.js expects.
COPY report_service/package.json /app/insight_receiptgenerator/package.json
RUN cd /app/insight_receiptgenerator && npm install --omit=dev

# Python side.
COPY requirements.txt /app/insight_core/requirements.txt
COPY report_service/requirements.txt /app/insight_core/report_service/requirements.txt
RUN pip install --no-cache-dir -r /app/insight_core/report_service/requirements.txt

# App code — everything generate_full_report()'s pipeline needs, plus the bridge.
COPY . /app/insight_core/

ENV PYTHONUNBUFFERED=1
WORKDIR /app/insight_core/report_service

# Cloud Run sets PORT; gunicorn timeout > worst-case cold start + render (see DEPLOY.md).
CMD exec gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 1 --timeout 180 app:app
