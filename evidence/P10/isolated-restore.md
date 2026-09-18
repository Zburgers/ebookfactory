# H9 isolated PostgreSQL restore evidence

- UTC: 2026-09-18T21:10:31Z
- Delivery revision: `5f9c9183773a7eee5381ff75adf43c6c871a88cd`
- Source target: PostgreSQL `ebookfactory`, peer role `naki`, Unix socket
  `/var/run/postgresql`; the source identity query returned
  `naki|ebookfactory|16.15 (Ubuntu 16.15-0ubuntu0.24.04.1)`.
- Archive: `var/backups/ebookfactory-20260918T211031Z.dump`
- Archive SHA-256: `5edfe46e13ef68c3030e90b00d3b1ffaf4a87edf0a5ebb8562632bcfebc948b2`
- Archive mode: `600`
- PostgreSQL tooling: `16.15` for `pg_dump`, `pg_restore`, `initdb`, `pg_ctl`,
  and `psql`.

## Command and observed result

```text
make backup
scripts/restore-check.sh var/backups/ebookfactory-20260918T211031Z.dump
```

The restore check created a user-owned temporary cluster under
`/tmp/ebookfactory-restore.*`, used a private Unix socket and temporary port,
verified `current_setting('data_directory')` through that socket, restored the
custom-format archive into the temporary `postgres` database, and queried the
restored data:

```text
isolated restore check passed (projects rows: 9; migration markers: 1)
port attempts: 1
```

The focused boundary test also used real `initdb`, `pg_ctl`, `pg_dump`,
`pg_restore`, and `psql`, deliberately occupied the first candidate port, and
observed `port attempts: 2`. It rejected an invalid base of `64517` so the
20-port retry window remains within the valid port range. The test passed:

```text
restore-check real isolated restore test passed
```

After the checks, `pgrep -a -x -u naki postgres` returned no temporary cluster
processes, no `/tmp/ebookfactory-restore.*` directories remained, the native
peer-authenticated `ebookfactory` query still passed, and the API systemd unit
remained active. No persistent second database, sudo, unrelated service, or
credential value was used.

## Review

The separate GPT-5.6 Luna low critic re-ran the repaired focused test and found
no remaining critical, high, or medium findings. Requested GPT-5.6 Luna high
critic sessions were unavailable after repeated polls and shutdown; this model
limitation is recorded rather than represented as a high-effort approval.

H9 is evidenced as PASS at the direct runtime boundary, with reduced review
confidence because the requested high-effort critic capability was unavailable.
