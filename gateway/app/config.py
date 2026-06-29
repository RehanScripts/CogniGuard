from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, read from environment / .env (pydantic-settings)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Postgres (OLTP system of record)
    database_url: str = "postgresql+psycopg://cogniguard:cogniguard_dev_pw@postgres:5432/cogniguard"

    # Redis (online feature store)
    redis_url: str = "redis://redis:6379/0"

    # Kafka (event log)
    kafka_bootstrap: str = "kafka:9092"

    # S3 / MinIO (data lake + model store)
    s3_endpoint: str = "http://minio:9000"
    s3_bucket: str = "cogniguard"
    aws_access_key_id: str = "minioadmin"
    aws_secret_access_key: str = "minioadmin"

    # Auth / integrity
    jwt_secret: str = "change_me_dev_only_super_secret"
    jwt_alg: str = "HS256"
    jwt_ttl_minutes: int = 30
    admin_jwt_ttl_minutes: int = 480
    nonce_ttl_s: int = 120
    integrity_skew_s: int = 30

    # SMTP (real OTP delivery) — leave smtp_host empty to suppress email in dev
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = "noreply@centralbankofindia.co.in"

    # ML
    model_dir: str = "/models"

    # LLM investigation assistant (Phase D5) — set LLM_PROVIDER=claude + ANTHROPIC_API_KEY to enable
    llm_provider: str = "stub"
    anthropic_api_key: str = ""

    # Groq (SHAP AI explanation) — set GROQ_API_KEY to enable; omit for graceful fallback
    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"

    # App
    app_env: str = "dev"
    log_level: str = "INFO"
    run_migrations_on_start: bool = True
    run_seed_on_start: bool = True
    login_latency_budget_ms: int = 300
    payment_latency_budget_ms: int = 500


settings = Settings()
