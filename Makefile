.PHONY: help up up-ui down build restart logs health \
        migrate seed train \
        test test-backend test-flink test-frontend \
        lint lint-python lint-ts \
        submit-flink drift promote clean

# ── Default target ────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "CogniGuard — available targets"
	@echo ""
	@echo "  Stack management"
	@echo "    make up          Bring up core stack (gateway + infra) in detached mode"
	@echo "    make up-ui       Bring up core stack + web-app + bank-dashboard"
	@echo "    make down        Stop all containers"
	@echo "    make build       Rebuild all images"
	@echo "    make restart     Restart the gateway container"
	@echo "    make logs        Follow gateway logs"
	@echo "    make health      Curl the /health endpoint"
	@echo ""
	@echo "  Database"
	@echo "    make migrate     Apply Alembic migrations"
	@echo ""
	@echo "  Data & models"
	@echo "    make seed        Seed demo personas, policy, and Redis baseline"
	@echo "    make train       Load datasets + train all three ML models"
	@echo "    make drift       Run PSI/KS drift report"
	@echo "    make promote     Promote a challenger (MODEL= VERSION= required)"
	@echo ""
	@echo "  Tests"
	@echo "    make test        Run all test suites (backend + flink)"
	@echo "    make test-backend  Gateway pytest suite"
	@echo "    make test-flink    Flink unit tests"
	@echo "    make test-frontend Run Vitest suites for all three TS packages"
	@echo ""
	@echo "  Linting"
	@echo "    make lint        Run all linters"
	@echo "    make lint-python Ruff + Black (gateway)"
	@echo "    make lint-ts     ESLint (web-app, bank-dashboard, behavior-sdk)"
	@echo ""
	@echo "  Cleanup"
	@echo "    make clean       Tear down containers + volumes + pycache"
	@echo ""

# ── Stack management ──────────────────────────────────────────────────────────
up:
	docker compose up -d

up-ui:
	docker compose --profile ui up -d

down:
	docker compose down

build:
	docker compose build

restart:
	docker compose restart gateway

logs:
	docker compose logs -f gateway

health:
	@curl -s http://localhost:8000/health | python -m json.tool

# ── Database ──────────────────────────────────────────────────────────────────
migrate:
	docker compose exec gateway alembic upgrade head

# ── Data & models ─────────────────────────────────────────────────────────────
seed:
	docker compose exec gateway python -m scripts.seed_demo

train:
	docker compose exec gateway python -m scripts.load_datasets
	docker compose exec gateway python -m training.train_isolation_forest
	docker compose exec gateway python -m training.train_lstm_autoencoder
	docker compose exec gateway python -m training.train_xgboost

submit-flink:
	docker compose up -d flink-job-submit

drift:
	docker compose exec gateway python -m training.drift_monitor

promote:
	@[ -n "$(MODEL)" ] && [ -n "$(VERSION)" ] || (echo "Usage: make promote MODEL=xgboost_txn VERSION=<ver>"; exit 1)
	docker compose exec gateway python -m training.promote --model $(MODEL) --version $(VERSION) --to production

# ── Tests ─────────────────────────────────────────────────────────────────────
test: test-backend test-flink

test-backend:
	docker compose exec gateway python -m pytest -q

test-flink:
	docker compose exec -e PYTHONPATH=/flink-jobs gateway python -m pytest /flink-jobs/tests -q

test-frontend:
	cd behavior-sdk && npm test
	cd web-app && npm test
	cd bank-dashboard && npm test

# ── Linting ───────────────────────────────────────────────────────────────────
lint: lint-python lint-ts

lint-python:
	docker compose exec gateway ruff check .
	docker compose exec gateway black --check .

lint-ts:
	cd web-app && npm run lint
	cd bank-dashboard && npm run lint
	cd behavior-sdk && npm run lint

# ── Cleanup ───────────────────────────────────────────────────────────────────
clean:
	docker compose down -v --remove-orphans
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
