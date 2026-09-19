# Dashboard redesign live deployment evidence

Date: 2026-09-19 (Asia/Kolkata)

- Remote branch tip fetched and fast-forwarded from `origin/codex/ebook-factory-v2`:
  `747d211` dashboard redesign, `5f9df37` redesign evidence.
- The redesign initially exposed a static bootstrap defect: unauthenticated
  `GET /atlas-cover.png` returned `401`, preventing the login artwork from
  loading.
- Revision `a049d9b` added `/atlas-cover.png` to the public bootstrap asset
  allowlist. Owner data routes remain bearer-protected.
- Focused owner-auth suite: 5 passed after the red/green repair.
- Full `make verify`: passed, with the existing 21 recovery tests skipped when
  `EBOOK_FACTORY_TEST_DATABASE_URL` is absent.
- Live `GET http://192.168.29.14:6969/atlas-cover.png`: HTTP 200,
  3,087,747 bytes.
- Live `GET http://192.168.29.14:6969/ready`: HTTP 200, database status `ok`.
- `ebook-factory-api.service`, `ebook-factory-worker.service`, and
  `ebook-factory-telegram.service`: active.
