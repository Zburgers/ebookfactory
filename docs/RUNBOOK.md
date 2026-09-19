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
after reboot without a login session. Non-loopback listeners use HTTPS: open
`https://<tailscale-ip>:6969` or `https://<private-lan-ip>:6969`. The default
local certificate is generated in `var/tls` and is private/self-signed, so a
browser requires a one-time trust exception or an operator-provided certificate
via `EBOOK_FACTORY_TLS_CERT` and `EBOOK_FACTORY_TLS_KEY`. The worker uses the
loopback HTTP listener only. Use `make start`, `make restart` and `make stop`
for lifecycle operations, and `journalctl --user -u ebook-factory-api.service`
for logs. The separate `scripts/service.sh` wrapper remains a local test helper;
it does not supervise worker or Podman jobs.

Create a custom-format peer-authenticated backup:

```sh
scripts/backup.sh
scripts/restore-check.sh var/backups/ebookfactory-<timestamp>.dump
```

The restore check creates a temporary user-owned PostgreSQL cluster under
`/tmp`, starts it on a temporary Unix socket and port, restores into its
default `postgres` database, verifies the `projects` row count and migration
marker table, then removes the cluster with a cleanup trap. It does not create
or modify a persistent database and does not use sudo. It fails closed when
the required PostgreSQL binaries are unavailable or restoration/sanity checks
fail.

Run the rubric-aware acceptance command:

```sh
make acceptance
```

It runs `make verify` and returns exit code 2 with a redacted PARTIAL report
until the Telegram and Codex image evidence exists. This is
intentional; a green unit suite is not product acceptance.

Rootless containment evidence is reproduced with:

```sh
scripts/check-isolation.sh
```

Provider, Telegram, publishing and image capabilities must be reconnected and
rechecked after credentials/tools are supplied; unknown billing and quota are
reported as unknown, never zero.
