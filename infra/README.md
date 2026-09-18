# Infrastructure scaffold

Intended directories: migrations/, podman/, services/. Exact PostgreSQL target requires owner confirmation. No Compose stack should claim existing ports/volumes blindly. Rootless production containers belong to this installation and are reconciled by labels. A user service may supervise API/worker; startup/shutdown must prove ownership. No infrastructure deployed yet.
