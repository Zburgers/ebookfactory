# On-demand Codex quota evidence

Revision `2ad955e` exposes `GET /quota/live`. The route invokes the local
`codexctl status` command on every request, parses only the 5-hour and 7-day
table windows, redacts account identity, and returns `503` when the command or
output is unavailable. It does not write a `QuotaSnapshot` row.

Real service check on 2026-09-19 returned HTTP 200 with a current
`fetched_at` timestamp and CLI values:

```text
source: codexctl status
fetched_at: 2026-09-19T00:06:16.978002Z
windows: account 1 — 5-hour 48% used / 52% remaining; 7-day 38% used / 62% remaining

The parser retains every valid CLI account as a redacted numeric account
label; a multi-account result is no longer silently truncated.
```

The dashboard calls `/quota/live` when Usage is opened or refreshed. It uses
human-readable window names, shows fetch source/time, and renders an explicit
unavailable message instead of `unknown%` or a placeholder bucket. The
persisted `/quota` snapshot API remains available for separately authenticated
worker observations, but is not used for this live dashboard panel.

Latest service recheck at `2026-09-19T01:04Z` returned two consecutive live
responses with source `codexctl status` and distinct fetch timestamps
(`01:04:11.401Z` and `01:04:13.916Z`). Both returned two measurable windows;
the CLI values changed from the earlier observation, confirming that the panel
is not replaying a stored snapshot. The PostgreSQL `quota_snapshots` count was
unchanged at `2` before and after the request.

Final post-restart check at `2026-09-19T01:29Z` repeated the same boundary:
two responses both reported `codexctl status`, had distinct fetch timestamps
(`01:29:21.570Z` and `01:29:23.112Z`), returned two windows, and left the
`quota_snapshots` count at `2`.
