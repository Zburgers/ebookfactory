# P10 backup evidence

- Code revision: `ba9a18a`
- UTC: 2026-09-18
- Target: native PostgreSQL 16.15, database `ebookfactory`, peer role `naki`, socket `/var/run/postgresql`; no sudo or password was used
- Command: `scripts/backup.sh`
- Result: custom-format archive `var/backups/ebookfactory-20260918T181346Z.dump`, mode 600, 40,882 bytes, SHA-256 `d365b70cb101a0acd2a4ac4f1032898c6237d3fa5370570e61b4505a3e2b7668`
- Check: `scripts/restore-check.sh` verified `public.projects` and `public.alembic_version` entries without creating or modifying another database
- Limitation: isolated database restore is not demonstrated because the owner prohibited creating another database; operations points and H9 remain unclaimed
