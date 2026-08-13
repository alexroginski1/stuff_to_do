# Built from the repo root (see webapi/cloudbuild.yaml), not the webapi/
# directory, so config/settings.py — the single source of truth for scraper
# source labels, shared with the sync job — can be copied into the image.
FROM python:3.11-slim

WORKDIR /app

COPY webapi/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config/__init__.py config/settings.py ./config/
COPY webapi/main.py .

CMD ["sh", "-c", "gunicorn --bind :$PORT --workers 1 --threads 8 main:app"]
