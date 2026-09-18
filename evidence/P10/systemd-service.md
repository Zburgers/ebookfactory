# P10 systemd user service evidence

- UTC: 2026-09-18T20:48:58Z
- Host: Razor Crest, Linux user `naki`
- Service: `ebook-factory-api.service`
- Unit: `infra/systemd/ebook-factory-api.service`
- Install path: `/home/naki/.config/systemd/user/ebook-factory-api.service`

## Contract update

The owner-raised completion gate is now strictly `>90/100`, meaning at least
91, with all hard gates still mandatory. Current score remains 76/100 and is
not being inflated by this deployment change.

## Service behavior

The service is a rootless systemd user unit enabled under `default.target`, with
`loginctl show-user naki -p Linger` returning `Linger=yes`. It uses
`Restart=on-failure`, `RestartSec=5s`, `NoNewPrivileges=true`, `PrivateTmp=true`,
and `UMask=0077`. Credentials remain in the ignored local `.env` via the unit's
optional `EnvironmentFile`; no credential values are logged or committed.

The launcher discovers the current Tailscale IPv4 and the explicit `eno1`
private LAN IPv4, starts one Uvicorn listener per address on port 6969, and
also binds loopback. It excludes wildcard, Docker, Podman, and bridge
addresses. Observed listeners:

```text
127.0.0.1:6969
100.87.104.100:6969
192.168.29.14:6969
```

Both real health checks returned:

```json
{"service":"ebook-factory-api","status":"ok","version":"0.1.0"}
```

After revision `ca7d6bc`, the unit was daemon-reloaded and restarted. Health
checks passed on all three listeners. A deliberate `SIGKILL` of the systemd
main process produced `restart-after-kill: passed`, followed by a successful
Tailscale health check. `systemctl --user` reports the unit enabled and active.

The first service start exposed a missing systemd PATH for `/home/naki/.local/bin/uv`
and exited 127. The unit was corrected to carry the explicit user-local PATH;
the service then started successfully. A deliberate main-process SIGKILL was
followed by systemd restart (`NRestarts` increased) and both address health
checks passed after the restart settled.

## Reproduction

```sh
make install-service
make status
make restart
make stop
make start
journalctl --user -u ebook-factory-api.service
```

The legacy `scripts/service.sh` remains a bounded local lifecycle test helper;
the boot service is the systemd unit above. Worker and rootless Podman job
supervision remain separate product boundaries.
