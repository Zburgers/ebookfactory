# P06 dashboard-shell evidence

- Code revision: `89640b4`
- UTC: 2026-09-18
- Local boot: Uvicorn on `127.0.0.1:18080` returned `/health` 200 and same-origin `/` 200; the process was stopped cleanly with Ctrl-C
- Browser check: headless Chromium loaded the page title `Ebook Factory`, `/src/styles.css` and `/src/app.js`; its only observed browser warning was the host AppArmor/DBus denial, not an application failure
- Implemented shell: project list/create, durable chat send/display, brief creation/hash-bound approval, event polling with per-project localStorage cursor, and provider metadata form with non-secret credential state
- Event API: replay-only `text/event-stream` endpoint emits bounded cursor events and closes cleanly; the dashboard shell still uses JSON polling until a live relay is connected
- Accessibility/layout: semantic labels, live regions, keyboard-submit forms, mobile media layout and visible error/status text are present in the static dashboard
- Verification: `make verify` passed API, migration, contract, PostgreSQL recovery, worker, web syntax and rootless containment checks
- Limitation: no full review/editor/download/usage page, authenticated dashboard session, live SSE relay, or browser interaction acceptance journey is claimed yet; dashboard score remains zero
