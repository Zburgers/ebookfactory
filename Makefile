.DEFAULT_GOAL := verify

API_DIR := apps/api
EVIDENCE_DIR := evidence/P00

.PHONY: doctor dev install-service start stop restart status verify backup restore-check acceptance

doctor:
	./scripts/doctor.sh --strict --output $(EVIDENCE_DIR)/capabilities.json

dev:
	set -a; [ ! -f .env ] || . ./.env; set +a; cd $(API_DIR) && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000

install-service:
	./scripts/install-user-service.sh

start:
	systemctl --user start ebook-factory-api.service ebook-factory-worker.service ebook-factory-telegram.service

stop:
	systemctl --user stop ebook-factory-telegram.service ebook-factory-worker.service ebook-factory-api.service

restart:
	systemctl --user restart ebook-factory-api.service ebook-factory-worker.service ebook-factory-telegram.service

status:
	systemctl --user status ebook-factory-api.service ebook-factory-worker.service ebook-factory-telegram.service --no-pager

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
	./scripts/tests/test_restore_check.sh
	./scripts/tests/test_service_entrypoint.sh
	./scripts/tests/test_serve_api_tls.sh
	./scripts/tests/test_systemd_service.sh
	./scripts/tests/test_worker_supervisor.sh
	./scripts/tests/test_worker_runner.sh
	./scripts/tests/test_worker_service.sh
	PYTHONPATH=$(API_DIR) $(API_DIR)/.venv/bin/python scripts/tests/test_telegram_worker.py
	./scripts/check-isolation.sh
