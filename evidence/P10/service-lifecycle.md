# P10 owned API lifecycle evidence

- Code revision: `a20f00f`; the wrapper runs as Linux user `naki` with no
  sudo, database password, container socket or global-home mount.
- `scripts/tests/test_service_entrypoint.sh` started the API on
  `127.0.0.1:18084`, confirmed `status` reported the owned PID, fetched
  `/health`, stopped the exact PID, and confirmed `status` reported stopped.
  The test is part of `make verify`, which passed with 20 tests passing and 9
  optional PostgreSQL tests skipped when their separate test-database variable
  is unset.
- `scripts/service.sh` keeps a mode-restricted PID/log directory under
  `var/run` by default, waits for health readiness, refuses to stop a live
  process whose command does not match the owned Uvicorn service, and supports
  `start`, `stop`, `restart` and `status` through Make targets.
- Limitation: this is the API/dashboard lifecycle only. The trusted worker and
  rootless production job lifecycle remain separate and are not claimed as
  fully supervised by this packet.
