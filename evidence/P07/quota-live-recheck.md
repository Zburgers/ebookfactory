# On-demand Codex quota recheck

Date: 2026-09-19 (Asia/Kolkata), against the enabled API service on port 6969.

Two authenticated `GET /quota/live` calls were made directly to the local API.
The endpoint invoked the local `codexctl status` command on each request and
did not read or write a quota snapshot.

- Snapshot row count before and after: `2` → `2`.
- First fetch: `2026-09-19T02:59:58.550789Z`, source `codexctl status`, 5-hour
  window `9% used / 91% remaining`, 7-day window `45% used / 55% remaining`.
- Second fetch: `2026-09-19T03:00:00.035559Z`, source `codexctl status`, same
  current windows and a new fetch timestamp.
- Account identity was not returned; valid accounts are represented only by a
  redacted account index.

The dashboard Usage navigation and Refresh action both call this same endpoint.
Unavailable or malformed CLI output is surfaced as an explicit unavailable
response; no placeholder percentage is synthesized.
