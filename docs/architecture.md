# Architecture

## Pipeline Overview

```
Mobile / Web (Central Bank of India UI)
    │
    │  Keystroke · Touch · Motion
    │  HMAC-SHA256 signed, single-use nonce, seq-monotonic
    ▼
┌──────────────────────────────────────────────────┐
│  FastAPI Gateway  (:8000)                        │
│  • Integrity     nonce/HMAC verify + consume     │
│  • Auth          Argon2id · JWT · session mgmt   │
│  • Behavior      continuous re-scoring endpoint  │
│  • Payment       amplifier overlay · txn controls│
└────────┬─────────────────────────┬───────────────┘
         │ Kafka events            │ Decisions / events
         ▼                         ▼
┌────────────────┐       ┌────────────────────────┐
│ Apache Flink   │       │ WebSocket /ws/soc-feed  │
│ Feature Engine │       │ (SOC dashboard live)    │
│ Windowed stats │       └────────────────────────┘
│ → Redis + S3   │
└───────┬────────┘
        │ Online features (hot path)
        ▼
┌──────────────┐   ┌───────────────────────────────────────┐
│  Redis 7     │──▶│  Risk Scoring Stack                   │
│  Feature     │   │  LSTM Autoencoder (ONNX)              │
│  Store       │   │    → calibration → Behavior_Score     │
└──────────────┘   │  Isolation Forest (shadow / fallback) │
                   │  XGBoost (stacked fraud probability)  │
                   │  Identity Scorer (robust-z distance)  │
                   │  Decision Engine (policy thresholds)  │
                   │  Dynamic Risk Amplifiers              │
                   └───────────────────────────────────────┘
         │
         ├──▶ PostgreSQL 16  (OLTP — off hot-path write)
         └──▶ MinIO / S3     (data lake · model artifacts)
```

## Core Design Invariants

| # | Rule |
|---|------|
| 1 | **Inference reads Redis only** — never PostgreSQL on the scoring hot path |
| 2 | **LSTM AE primary, IF shadow** — AE reconstruction error → calibration → `Behavior_Score`; IF runs alongside in shadow and is the cold-start / degraded-mode fallback |
| 3 | **Single stacked probability** — `Behavior_Score` → XGBoost → one fraud probability → one policy threshold |
| 4 | **Nonce+HMAC payload binding** — each telemetry payload is single-use; replay / MITM is rejected at the integrity layer |
| 5 | **Continuous re-scoring** — risk is a property of the whole session; a low login can escalate later |
| 6 | **Policy-driven bands** — thresholds, amplifier multipliers, and challenge types come from the active policy in Redis, never hardcoded |
| 7 | **Cold-start → verify** — new users / channels lean on Isolation Forest + rules and bias to `verify`, never `block` |
| 8 | **Graceful degradation** — XGBoost unavailable → IF + rules; Redis degraded → bias to verify; always tag `degraded_mode` |
| 9 | **Anti-poisoning quarantine** — step-up-passed telemetry is quarantined before any training use |
| 10 | **Full audit trail** — every `verify`/`block` carries reason codes; `model_version` stamped on every `risk_scores` row |

## Risk Bands & Decisions

| Band | Score | Default Action |
|------|-------|----------------|
| `low` | 0 – 30 | `allow` |
| `medium` | 30 – 60 | `verify` (light: OTP / MPIN) |
| `high` | 60 – 85 | `verify` (strong: biometric / passkey) |
| `very_high` | ≥ 85 | `block` + alert + case opened |

## Dynamic Risk Amplifiers

Multiplicative overlays applied at payment time (`final = clamp(base × Π multipliers, 0, 100)`):

| Amplifier | Trigger | Multiplier |
|-----------|---------|-----------|
| `NEW_BENEF_HIGHVAL` | New beneficiary, amount > threshold | ×1.5 |
| `RAPID_FAN_OUT` | Many beneficiaries in short window | ×1.4 |
| `DRAIN_MAX_OUT` | Amount approaches account limit | ×1.3 |
| `COERCION_TIME` | Duress indicators (active call, etc.) | ×1.2 |

## Kafka Topics

| Topic | Direction | Purpose |
|-------|-----------|---------|
| `behavior_events` | Gateway → Flink | Raw behavioral signals |
| `device_events` | Gateway → Flink | Device fingerprint + geo |
| `login_events` | Gateway → Flink | Auth attempts |
| `transaction_events` | Gateway → Flink | Payment attempts |
| `risk_scores` | Gateway → Dashboard | Scored events |
| `decisions` | Gateway → Dashboard | allow/verify/block decisions |

## Latency Targets

| Path | p95 Target |
|------|-----------|
| Login decision (gateway in → decision out) | < 300 ms |
| Payment decision | < 500 ms |

## ML Model Stack

| Model | Role | Format | Where |
|-------|------|--------|-------|
| LSTM Autoencoder | Primary behavioral scorer | ONNX | Gateway (ONNX Runtime) |
| LSTM Autoencoder | On-device mobile scorer | TFLite | Android (TensorFlow Lite) |
| Isolation Forest | Shadow scorer / cold-start fallback | joblib | Gateway |
| XGBoost | Stacked fraud probability | joblib | Gateway |

See [docs/android-setup.md](android-setup.md) for the TFLite model copy step.
