# Phase 26 — Boot Correctness: Flink Auto-Submit + AE Calibration Self-Seeding

## Goal

`docker compose up` alone (no manual `flink run`, no manual training/seeding command)
must yield a fully operational system: the Flink feature-engine job running, Redis
behavioral baselines / velocity counters / device trust / geo context / beneficiary
context populating from real events, and the AE able to clear cold-start whenever a
pre-trained autoencoder artifact is present.

No new models, scoring systems, or calculations were introduced — this phase only wires
already-built pieces (Phase 4's `feature_engine.py`, Phase 16's calibration layer) into
the boot sequence.

## What changed

1. **`docker-compose.yml`**
   - `flink-jobmanager` gained a REST healthcheck (`wget` against `:8081/overview` —
     `wget` is what `flink-jobs/Dockerfile` installs, not `curl`), with a 30s
     `start_period` for JVM boot.
   - New one-shot `flink-job-submit` service, mirroring the existing `minio-init`
     pattern: `depends_on: flink-jobmanager {service_healthy}` +
     `flink-taskmanager {service_started}`, `restart: "no"`, runs
     `flink run -d -py /jobs/feature_engine.py -m flink-jobmanager:8081`.
     `flink-jobs/feature_engine.py` already had a `__main__` entrypoint — zero code
     change needed there.
   - `gateway` now also depends on
     `flink-job-submit: {condition: service_completed_successfully}`, so the gateway
     (and therefore `seed_demo.py`'s behavior) never starts ahead of the feature
     pipeline being live.
   - New one-shot `kafka-topics-init` service (gateway image,
     `python -m scripts.create_topics`, `depends_on: kafka {service_healthy}`,
     `restart: "no"`). **Found during verification, not anticipated in the original
     plan:** auto-submitting the Flink job before anything else creates the Kafka
     topics raced ahead of topic creation (`KAFKA_AUTO_CREATE_TOPICS_ENABLE=false`) —
     the job submitted but immediately failed with
     `UnknownTopicOrPartitionException` because `login_events` etc. didn't exist yet.
     Previously this was masked because the job was always submitted by hand, well
     after the gateway (the only thing that created topics, in its `lifespan`) had
     already booted. `flink-job-submit` now also depends on
     `kafka-topics-init: {condition: service_completed_successfully}`.

2. **`gateway/scripts/seed_calibration.py`** (extended, not replaced)
   - Previously: pure disaster-recovery — required a production `lstm_autoencoder` row
     with real `metrics["calibration"]` already in Postgres, raised `LookupError`
     otherwise. That only ever happens after a manual, multi-minute
     `training.train_lstm_autoencoder` run (it requires TensorFlow, which is
     deliberately *not* a gateway dependency per CLAUDE.md).
   - Now: if no production `lstm_autoencoder`/`lstm_autoencoder_tflite` row exists, it
     scans `MODEL_DIR` (the `./models:/models` bind mount) for the newest
     `{model_name}@<date>/model.{onnx,tflite}` artifact already on disk (e.g. from a
     prior offline training run) and registers it via the existing
     `training.registry.register_model()` — the same write path
     `train_lstm_autoencoder.py` itself uses. If that run's real calibration metrics
     aren't available, it falls back to `calibration.default_calibration()`
     (`scale=1.0, threshold=0.5, temperature=1.0`) — the same neutral default
     `calibration.py` already documents and ships, not a new calculation.
   - If neither a registry row nor a local artifact exists (fresh checkout, training
     never run), this is a no-op and AE correctly stays cold-start, falling back to the
     Isolation Forest shadow score — existing CLAUDE.md invariant 9 behavior, not a
     regression.
   - `gateway/entrypoint.sh`: new `RUN_SEED_ON_START`-gated step calling
     `python -m scripts.seed_calibration`, alongside the existing `seed_demo.py` step
     (non-fatal on failure, same pattern).

3. **`PROGRESS.md`**: removed the now-stale "Flink job submitted manually" gotcha and
   the duplicate "Auto-submit Flink job" TODO line; updated §2's setup instructions;
   added the Phase 26 row to the phase tracker.

## Files changed

- `docker-compose.yml`
- `gateway/scripts/seed_calibration.py`
- `gateway/entrypoint.sh`
- `PROGRESS.md`
- `phases/PHASE_26_boot_correctness.md` (this file)

## Verification (actually run against this branch, not just described)

```
docker compose down            # kept named volumes -- see PROGRESS.md §1.4
docker compose up --build -d
```

- `kafka-topics-init` exited 0, log: `created: ['behavior_events', 'device_events',
  'login_events', 'transaction_events', 'risk_scores', 'decisions']`.
- `flink-job-submit` exited 0, log: `Job has been submitted with JobID ...`.
- `curl localhost:8081/jobs/overview` → `"state":"RUNNING"`, `"tasks":{"running":4,...}`
  — no manual `flink run`/`docker compose exec` step at any point.
- `gateway` entrypoint log shows, in order with no manual intervention: alembic
  migrations → `seed_demo` (policy + genuine persona + beneficiary) → `seed_calibration`
  (`version: lstm_autoencoder@2026-06-21`, real `scale`/`threshold` from a prior
  training run already in this Postgres volume — confirms the disaster-recovery path
  still works when real calibration already exists, not just the new self-heal path) →
  `generate_fraud_scenarios` → uvicorn up.
- `redis-cli GET calib:ae:population` → `{"scale": 6.91..., "threshold": 48194.6...,
  "temperature": 1.0}`.
- Drove a real `POST /api/v1/auth/login` with a freshly-regenerated
  `tests/fixtures/login_genuine.json` → `200 allow`, `risk_band: low`, with
  `trust_score`/`device_trust`/`enrollment` populated in the response.
- After that single login, `redis-cli KEYS 'device:*:trust'` returned
  `device:<id>:trust` — written by `flink-jobs/sinks.py` from the `login_events` Kafka
  message the login produced, proving the auto-submitted job is actually consuming and
  writing features, not just sitting `RUNNING` idle.
- `docker compose exec gateway python -m pytest -q` → **185 passed, 1 skipped** (no
  scoring/behavior change, boot-sequence only).
