FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

# Cloud Run injects PORT; uvicorn must bind it or the revision never goes healthy.
ENV PORT=8080
EXPOSE 8080
# The console, not the v1 baseline. Mutations stay off unless the deployment
# explicitly sets GEMINGA_ALLOW_MUTATIONS — an image that can delete things by
# default is an image someone runs by accident.
CMD exec uvicorn app.nightshift:app --host 0.0.0.0 --port ${PORT}
