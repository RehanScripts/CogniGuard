#!/usr/bin/env bash
set -euo pipefail

# Phase 1+: run migrations on start when configured and alembic is present.
if [ "${RUN_MIGRATIONS_ON_START:-false}" = "true" ] && [ -f "alembic.ini" ]; then
  echo "[entrypoint] applying alembic migrations..."
  alembic upgrade head
fi

# Phase 5/8+: seed demo personas + active policy when present.
if [ "${RUN_SEED_ON_START:-false}" = "true" ] && [ -f "scripts/seed_demo.py" ]; then
  echo "[entrypoint] seeding demo data..."
  python -m scripts.seed_demo || echo "[entrypoint] seed step skipped/failed (non-fatal)"
fi

# Phase 16/26: register the AE production row from a local pre-trained artifact (if one
# exists) and seed calib:ae:population, so AE can clear cold-start without a manual,
# multi-minute TensorFlow training run inside the container.
if [ "${RUN_SEED_ON_START:-false}" = "true" ] && [ -f "scripts/seed_calibration.py" ]; then
  echo "[entrypoint] seeding AE calibration..."
  python -m scripts.seed_calibration || echo "[entrypoint] AE calibration seed skipped/failed (non-fatal)"
fi

# Phase 11: regenerate signed demo fixtures (nonces are single-use/TTL'd, so these are
# refreshed every start rather than committed as permanently-valid artifacts).
if [ "${RUN_SEED_ON_START:-false}" = "true" ] && [ -f "scripts/generate_fraud_scenarios.py" ]; then
  echo "[entrypoint] generating fraud-scenario fixtures..."
  python -m scripts.generate_fraud_scenarios || echo "[entrypoint] fixture generation skipped/failed (non-fatal)"
fi

echo "[entrypoint] starting uvicorn on :8000"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
