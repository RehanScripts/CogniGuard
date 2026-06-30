# Security Policy

## Prototype Disclaimer

CogniGuard is a **research prototype** built for a hackathon. It is **not intended for production use** with real financial data or accounts. The security controls described here are implemented for demonstration purposes.

---

## Supported Versions

| Version | Supported |
|---------|-----------|
| `main` (latest) | Yes |
| All others | No |

---

## Reporting a Vulnerability

If you discover a security vulnerability, please **do not open a public GitHub issue**.

Report vulnerabilities by emailing the repository owner directly (see GitHub profile). Include:
- A description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested remediation

You will receive a response within 72 hours. If the vulnerability is confirmed, a fix will be prioritised and credited to you (unless you prefer anonymity).

---

## Security Controls (implemented in this prototype)

| Control | Implementation |
|---------|---------------|
| Password hashing | Argon2id (`argon2-cffi`) |
| Session tokens | Short-lived JWT (HS256), tracked in Redis denylist |
| Payload integrity | HMAC-SHA256 + single-use nonce + monotonic `seq` + timestamp skew check |
| Replay protection | Nonce consumed on first use; replay returns `401 NONCE_REUSED` |
| Brute-force throttling | IP/device throttle (never account lockout) |
| SQL injection | SQLAlchemy 2.x parameterized queries only |
| Secret management | All secrets via environment variables / `.env` — never committed |
| Data minimization | Raw sensor streams extracted on-device; only derived features transmitted |
| Consent gate | Behavioral capture requires explicit user consent (DPDP Act 2023) |
| Audit trail | Every `verify`/`block` decision immutably logged with reason codes |

---

## Known Limitations (prototype scope)

- `JWT_SECRET` defaults to a weak dev value — **must** be changed before any deployment
- SMTP credentials in `.env` are plaintext — use a secrets manager in production
- TLS/HTTPS is not configured in the Docker Compose stack — add a reverse proxy (nginx/traefik) for any non-local deployment
- The dev OTP fallback (`123456`) is hardcoded — disable `SMTP_*` env bypass in production
- MinIO credentials default to `minioadmin` — change before exposing to a network
