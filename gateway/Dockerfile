FROM python:3.11-slim

# Runtime libs for scikit-learn / xgboost (OpenMP) and psql client for healthchecks
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# App source + install (package build needs app/ present)
COPY . .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

ENTRYPOINT ["./entrypoint.sh"]
