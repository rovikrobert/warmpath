# Developer shortcuts for WarmPath local dev environment
# Usage: make <target>

.PHONY: dev down seed test lint format logs logs-app clean rebuild migrate migration help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

dev: ## Start all services (Postgres + Redis + API + Worker + Frontend)
	docker compose -f docker-compose.dev.yml up -d
	@echo ""
	@echo "  API:      http://localhost:8000"
	@echo "  Frontend: http://localhost:5173"
	@echo "  Postgres: localhost:5433"
	@echo "  Redis:    localhost:6380"
	@echo ""

down: ## Stop all services
	docker compose -f docker-compose.dev.yml down

seed: ## Seed the dev database with test data
	docker compose -f docker-compose.dev.yml exec app python3 -m scripts.seed_dev

test: ## Run pytest (locally, not in Docker)
	pytest -n auto --timeout=120 -q

lint: ## Run ruff format + lint checks
	ruff format . && ruff check --fix .

format: lint ## Alias for lint

logs: ## Tail logs from all services
	docker compose -f docker-compose.dev.yml logs -f

logs-app: ## Tail logs from app service only
	docker compose -f docker-compose.dev.yml logs -f app

clean: ## Stop services and remove volumes (fresh start)
	docker compose -f docker-compose.dev.yml down -v
	@echo "Volumes removed. Run 'make dev && make seed' to start fresh."

rebuild: ## Rebuild Docker images (after requirements.txt change)
	docker compose -f docker-compose.dev.yml build --no-cache

migrate: ## Run alembic migrations in the app container
	docker compose -f docker-compose.dev.yml exec app alembic upgrade head

migration: ## Create a new alembic migration (usage: make migration m="description")
	docker compose -f docker-compose.dev.yml exec app alembic revision --autogenerate -m "$(m)"
