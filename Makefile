.PHONY: help setup demo dev-env farmer-env dev api web db-up db-down db-reset migrate upgrade downgrade seed seed-reset fetch fetch-due fetch-status check lint fmt typecheck test test-api test-web progress progress-check clean

API := apps/api
PY  := $(API)/.venv/bin/python
UV  := uv
COMPOSE := docker compose -f infra/docker-compose.yml

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-14s\033[0m %s\n", $$1, $$2}'

# ------------------------------------------------------------------ setup

setup: ## Install deps, start the database, apply migrations
	cd $(API) && $(UV) venv --python 3.12 --quiet || true
	cd $(API) && $(UV) pip install --quiet -e ".[dev]"
	cd apps/web && npm install
	$(COMPOSE) up -d --build
	@sleep 5
	$(MAKE) upgrade
	@echo ""
	@echo "Dependencies installed and the schema is up. Next:  make demo"

demo: ## One command from a fresh clone to a running demo
	$(MAKE) seed
	@printf 'NEXT_PUBLIC_API_URL=http://localhost:8000\n' > apps/web/.env.local
	@echo ""
	@echo "  Ready. Run 'make dev', then open http://localhost:3000 and sign in:"
	@echo ""
	@echo "    ceo@demo.agrivardhak      the organization console"
	@echo "    officer@demo.agrivardhak  the console, narrower approval rights"
	@echo "    farmer@demo.agrivardhak   one member's own farm"
	@echo ""
	@echo "  Password for all three: agrivardhak"
	@echo ""

dev-env: ## Legacy: bypass the sign-in screen with a CEO token in .env.local
	@cd $(API) && .venv/bin/python -c "import sys; sys.path.insert(0,'.'); 	from sqlalchemy import select; 	from agrivardhak.api.auth import issue_token; 	from agrivardhak.db.session import session_scope; 	from agrivardhak.domain.enums import Role; 	from agrivardhak.domain.models.organization import Organization, RoleGrant; 	s=session_scope().__enter__(); 	org=s.execute(select(Organization)).scalars().first(); 	g=s.execute(select(RoleGrant).where(RoleGrant.role==Role.FPO_CEO)).scalars().first(); 	print(issue_token(user_id=g.user_id, roles={Role.FPO_CEO}, organization_id=org.id))" 	> /tmp/agrivardhak-token || (echo "No seeded organization found. Run 'make seed' first." && exit 1)
	@printf 'AGRI_DEV_TOKEN=%s\nNEXT_PUBLIC_API_URL=http://localhost:8000\n' \
	  "$$(cat /tmp/agrivardhak-token)" > apps/web/.env.local
	@rm -f /tmp/agrivardhak-token
	@echo "Wrote apps/web/.env.local (CEO token, expires in 12h — re-run this if the UI says 403)."

farmer-env: ## Legacy: bypass the sign-in screen with a FARMER token in .env.local
	@cd $(API) && .venv/bin/python -c "import uuid, sys; sys.path.insert(0,'.'); 	from sqlalchemy import select; 	from agrivardhak.api.auth import issue_token; 	from agrivardhak.db.session import session_scope; 	from agrivardhak.domain.enums import Role; 	from agrivardhak.domain.models.organization import Organization, Farmer; 	s=session_scope().__enter__(); 	org=s.execute(select(Organization)).scalars().first(); 	f=s.execute(select(Farmer)).scalars().first(); 	print(issue_token(user_id=uuid.uuid4(), roles={Role.FARMER}, organization_id=org.id, farmer_id=f.id))" 	> /tmp/agrivardhak-token || (echo "No seeded farmer found. Run 'make seed' first." && exit 1)
	@printf 'AGRI_DEV_TOKEN=%s\nNEXT_PUBLIC_API_URL=http://localhost:8000\n' \
	  "$$(cat /tmp/agrivardhak-token)" > apps/web/.env.local
	@rm -f /tmp/agrivardhak-token
	@echo "Wrote a FARMER token. Restart the web server, then open /today."
	@echo "Every /fpo/* and /decisions route will now return 403 — that is the point (INV-5)."

# ------------------------------------------------------------------ database

db-up: ## Start Postgres
	$(COMPOSE) up -d --build

db-down: ## Stop Postgres (keeps data)
	$(COMPOSE) down

db-reset: ## Destroy and recreate the database from scratch
	$(COMPOSE) down -v
	$(COMPOSE) up -d --build
	@sleep 6
	$(MAKE) upgrade

migrate: ## Autogenerate a migration:  make migrate m="add buyer reliability"
	@test -n "$(m)" || (echo "usage: make migrate m=\"message\"" && exit 1)
	cd $(API) && .venv/bin/alembic revision --autogenerate -m "$(m)"

upgrade: ## Apply migrations
	cd $(API) && .venv/bin/alembic upgrade head

downgrade: ## Roll back one migration
	cd $(API) && .venv/bin/alembic downgrade -1

seed: ## Load the synthetic Prayagraj FPO
	cd $(API) && .venv/bin/python -m agrivardhak.seed

seed-reset: ## Truncate all data and re-seed (faster than db-reset; keeps the schema)
	cd $(API) && .venv/bin/python -m agrivardhak.seed --reset

fetch-status: ## Show every registered external source, its health and whether it is due
	@python3 seed/fetch_datagovin.py --status

fetch-due: ## Re-fetch every source past its recheck cadence (the periodic entry point)
	@python3 seed/fetch_datagovin.py --due
	@python3 seed/fetch_up_schemes.py --due

fetch: ## Fetch one batch of external sources, e.g. make fetch b=1
	@python3 seed/fetch_datagovin.py $(if $(b),--batch $(b),)

weather: ## Fetch real Open-Meteo weather:  make weather from=2024-06-01 to=2026-08-22
	@test -n "$(from)" -a -n "$(to)" || (echo 'usage: make weather from=YYYY-MM-DD to=YYYY-MM-DD' && exit 1)
	python3 seed/fetch_weather.py --from $(from) --to $(to)

dev-token: ## Print a CEO bearer token for local UI work (export AGRI_DEV_TOKEN=...)
	@cd $(API) && .venv/bin/python -c "from sqlalchemy import select; \
	from agrivardhak.api.auth import issue_token; \
	from agrivardhak.db.session import session_scope; \
	from agrivardhak.domain.enums import Role; \
	from agrivardhak.domain.models.organization import Organization, RoleGrant; \
	s=session_scope().__enter__(); \
	org=s.execute(select(Organization)).scalars().one(); \
	g=s.execute(select(RoleGrant).where(RoleGrant.role==Role.FPO_CEO)).scalars().one(); \
	print(issue_token(user_id=g.user_id, roles={Role.FPO_CEO}, organization_id=org.id))"

agmarknet: ## Backfill real Agmarknet price/arrival data:  make agmarknet from=2024-08-22 to=2026-08-22
	@test -n "$(from)" -a -n "$(to)" || (echo 'usage: make agmarknet from=YYYY-MM-DD to=YYYY-MM-DD' && exit 1)
	python3 seed/fetch_agmarknet.py --from $(from) --to $(to)

# ------------------------------------------------------------------ dev servers

dev: ## Run API and web together
	@$(MAKE) -j2 api web

api: ## Run the FastAPI server on :8000
	cd $(API) && .venv/bin/uvicorn agrivardhak.api.main:app --reload --port 8000

web: ## Run the Next.js server on :3000
	cd apps/web && npm run dev

# ------------------------------------------------------------------ quality

check: lint typecheck ## Lint and typecheck everything

lint: ## Ruff + eslint
	cd $(API) && .venv/bin/ruff check agrivardhak tests
	cd $(API) && .venv/bin/ruff format --check agrivardhak tests
	cd apps/web && npm run lint

fmt: ## Autoformat
	cd $(API) && .venv/bin/ruff check --fix agrivardhak tests
	cd $(API) && .venv/bin/ruff format agrivardhak tests

typecheck: ## mypy (strict on domain/ and intelligence/) + tsc
	cd $(API) && .venv/bin/mypy agrivardhak
	cd apps/web && npx tsc --noEmit

test: test-api test-web ## Run all tests

test-api: ## pytest
	cd $(API) && .venv/bin/python -m pytest -q

test-web: ## vitest — component tests, including partial-packet rendering
	cd apps/web && npx vitest run

progress: ## Regenerate PROGRESS.md from what the repo can prove
	$(API)/.venv/bin/python scripts/progress.py

progress-check: ## Fail if PROGRESS.md is stale (for CI)
	$(API)/.venv/bin/python scripts/progress.py --check

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf $(API)/.pytest_cache $(API)/.mypy_cache $(API)/.ruff_cache
