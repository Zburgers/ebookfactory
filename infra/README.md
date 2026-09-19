# Infrastructure scaffold

Directories: migrations/, podman/, systemd/. The owner-confirmed PostgreSQL target is
`ebookfactory` through peer role `naki`; no Compose stack claims existing
ports/volumes. Rootless production containers belong to this installation and
are reconciled by labels. `systemd/ebook-factory-api.service` is installed as a
rootless user service by `scripts/install-user-service.sh`; it binds the API to
the Tailscale IPv4 and private LAN IPv4 addresses on port 6969 and restarts on
failure. Non-loopback listeners use HTTPS; loopback remains HTTP for the local
worker. The worker/container supervision boundary remains separate and must
prove ownership.
