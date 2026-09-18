.DEFAULT_GOAL := verify

API_DIR := apps/api
EVIDENCE_DIR := evidence/P00

.PHONY: doctor dev verify backup restore-check acceptance

doctor:
	./scripts/doctor.sh --strict --output $(EVIDENCE_DIR)/capabilities.json

dev:
	set -a; [ ! -f .env ] || . ./.env; set +a; cd $(API_DIR) && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000

backup:
	@./scripts/backup.sh

restore-check:
	@test -n "$(BACKUP)" || (printf 'usage: make restore-check BACKUP=var/backups/file.dump\n' >&2; exit 2)
	@./scripts/restore-check.sh "$(BACKUP)"

acceptance:
	./scripts/acceptance.sh

verify:
	uv sync --directory $(API_DIR)
	uv run --directory $(API_DIR) pytest -q
	bash -n scripts/doctor.sh
	./scripts/tests/test_doctor.sh
	./scripts/tests/test_migrations.sh
	./scripts/tests/test_contract_generation.sh
	./scripts/tests/test_recovery_postgres.sh
	npm run verify --prefix apps/worker
	npm run verify --prefix apps/web
	./scripts/tests/test_sandbox_args.sh
	./scripts/tests/test_production_boundary.sh
	./scripts/tests/test_operations_entrypoints.sh
	./scripts/check-isolation.sh
