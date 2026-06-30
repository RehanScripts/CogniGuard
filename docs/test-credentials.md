# Test Credentials

All accounts are seeded automatically when the stack starts (`RUN_SEED_ON_START=true`).
No manual setup is needed — run `docker compose up` and these are ready.

---

## Banking App — `http://localhost:5173`

| Role | Username | Password | Notes |
|------|----------|----------|-------|
| Customer (genuine) | `genuine` | `Passw0rd!` | Known Mumbai device + seeded behavioral baseline → scores **low / allow** |
| Customer (impostor) | `genuine` | `Passw0rd!` | Use `login_impostor.json` fixture against this account → fires `NEW_DEVICE` + `GEO_CHANGE` |

> The "impostor" is not a separate user — it is the same username submitted with a different device fingerprint and Tallinn geolocation.

---

## SOC Dashboard — `http://localhost:5174`

| Role | Email | Password | Permissions |
|------|-------|----------|-------------|
| Admin | `admin@cogniguard.dev` | `Passw0rd!` | Full access: policy write, model promote/rollback, case actions |
| Analyst | `analyst@cogniguard.dev` | `Passw0rd!` | Read-only + case notes/resolution; cannot modify policy or models |

Login via `POST /api/v1/admin/login` or the dashboard login page at `:5174/login`.

---

## API — Gateway `http://localhost:8000`

Customer JWTs are obtained from:
```
POST /api/v1/auth/login
{ "username": "genuine", "password": "Passw0rd!" }
```

Admin/Analyst JWTs are obtained from:
```
POST /api/v1/admin/login
{ "email": "admin@cogniguard.dev", "password": "Passw0rd!" }
```

Use the returned `access_token` as `Authorization: Bearer <token>` on subsequent requests.

Interactive testing: **http://localhost:8000/docs** (Swagger UI — includes Authorize button).

---

## Infrastructure

| Service | URL | Username | Password |
|---------|-----|----------|----------|
| MinIO console (S3 UI) | http://localhost:9001 | `minioadmin` | `minioadmin` |
| PostgreSQL | `localhost:5432` db `cogniguard` | `cogniguard` | `cogniguard_dev_pw` |
| Redis | `localhost:6379` | — | — |

---

## Step-Up OTP

During development the OTP challenge is always **`123456`** (hardcoded in `gateway/app/services/adaptive_auth.py`).

Configure real email delivery by setting `SMTP_*` variables in `.env`.

---

## Android App

The Android app targets `http://127.0.0.1:8000` via ADB reverse tunnel.
Set up the tunnel before running on a physical device:

```bash
adb reverse tcp:8000 tcp:8000
```

Use the same `genuine` / `Passw0rd!` credentials in the login screen.
See [docs/android-setup.md](android-setup.md) for full setup instructions.
