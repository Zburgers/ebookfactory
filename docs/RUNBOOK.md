# Local operations runbook

The API uses native PostgreSQL through the owner-confirmed peer role `naki` and
database `ebookfactory` on `/var/run/postgresql`. Normal operation does not use
sudo, database passwords, or a second database.

Start the local API and dashboard in the foreground:

```sh
make dev
```

Open `http://127.0.0.1:8000` for foreground development. Stop with Ctrl-C. The worker callback token is
only needed when the trusted supervisor is enabled; keep it in the ignored root
`.env` as `EBOOK_FACTORY_WORKER_TOKEN`.

For the boot-persistent API service, install it once as the unprivileged `naki`
user and let the user manager own port 6969:

```sh
make install-service
make status
tailscale ip -4
```

The service binds separately to the current Tailscale IPv4 and detected private
LAN IPv4 addresses, restarts on failure, and is enabled under the user manager's
`default.target`. This host already has user lingering enabled, so it starts
after reboot without a login session. Open `http://<tailscale-ip>:6969` or
`http://<private-lan-ip>:6969`. Use `make start`, `make restart` and `make stop`
for lifecycle operations, and `journalctl --user -u ebook-factory-api.service`
for logs. The separate `scripts/service.sh` wrapper remains a local test helper;
it does not supervise worker or Podman jobs.

Create a custom-format peer-authenticated backup:

```sh
scripts/backup.sh
scripts/restore-check.sh var/backups/ebookfactory-<timestamp>.dump
```

The restore check validates archive structure without creating or modifying a
database. A full isolated restore demonstration remains pending because the
owner prohibited creating another database during this build.

Run the rubric-aware acceptance command:

```sh
make acceptance
```

It runs `make verify` and returns exit code 2 with a redacted PARTIAL report
until the Telegram, Codex image, and isolated-restore evidence exists. This is
intentional; a green unit suite is not product acceptance.

Rootless containment evidence is reproduced with:

```sh
scripts/check-isolation.sh
```

Provider, Telegram, publishing and image capabilities must be reconnected and
rechecked after credentials/tools are supplied; unknown billing and quota are
reported as unknown, never zero.
