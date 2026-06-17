import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from . import kafka_client, s3_client
from .config import settings
from .db import engine
from .redis_client import ping as redis_ping

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger("cogniguard.gateway")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure Kafka topics exist (idempotent, best-effort — never block startup).
    try:
        from scripts.create_topics import create_topics

        created = create_topics()
        logger.info("kafka topics ready (created: %s)", created or "all present")
    except Exception as exc:  # broker not up yet / transient
        logger.warning("topic creation skipped: %s", exc)
    yield


def _db_ping() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def create_app() -> FastAPI:
    app = FastAPI(title="CogniGuard Gateway", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:5174"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> JSONResponse:
        checks = {
            "db": "ok" if _db_ping() else "down",
            "redis": "ok" if redis_ping() else "down",
            "kafka": "ok" if kafka_client.ping() else "down",
            "s3": "ok" if s3_ping_safe() else "down",
            "model_registry": "empty",  # populated in Phase 6
        }
        healthy = all(v == "ok" for k, v in checks.items() if k != "model_registry")
        body = {"status": "ok" if healthy else "degraded", "env": settings.app_env, **checks}
        return JSONResponse(body, status_code=200 if healthy else 503)

    # Routers are mounted in later phases:
    # from .routers import auth, payment, behavior, risk, admin, ws
    # app.include_router(auth.router,     prefix="/api/v1/auth",     tags=["auth"])
    # app.include_router(payment.router,  prefix="/api/v1/payment",  tags=["payment"])
    # app.include_router(behavior.router, prefix="/api/v1/behavior", tags=["behavior"])
    # app.include_router(risk.router,     prefix="/api/v1/risk",     tags=["risk"])
    # app.include_router(admin.router,    prefix="/api/v1/admin",    tags=["admin"])
    # app.include_router(ws.router,       tags=["ws"])
    return app


def s3_ping_safe() -> bool:
    return s3_client.ping()


app = create_app()
