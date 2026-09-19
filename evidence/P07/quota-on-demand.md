# On-demand Codex quota evidence

Revision `2ad955e` exposes `GET /quota/live`. The route invokes the local
`codexctl status` command on every request, parses only the 5-hour and 7-day
table windows, redacts account identity, and returns `503` when the command or
output is unavailable. It does not write a `QuotaSnapshot` row.

Real service check on 2026-09-19 returned HTTP 200 with a current
`fetched_at` timestamp and CLI values:

```text
source: codexctl status
fetched_at: 2026-09-18T23:59:33.604113Z
windows: 5-hour 47% used / 53% remaining; 7-day 37% used / 63% remaining
```

The dashboard calls `/quota/live` when Usage is opened or refreshed. It uses
human-readable window names, shows fetch source/time, and renders an explicit
unavailable message instead of `unknown%` or a placeholder bucket. The
persisted `/quota` snapshot API remains available for separately authenticated
worker observations, but is not used for this live dashboard panel.
