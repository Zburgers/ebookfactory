# Durable orchestrator streaming evidence

UTC date: 2026-09-19

The real API and worker services were restarted from the delivered worktree.
For a no-provider-cost boundary check, the worker was paused briefly and a
temporary project conversation was created through the owner API. A trusted
worker lease then submitted one `orchestrator.turn.delta`, completed the same
fenced turn, and replayed `/projects/{id}/events/stream?after=0`.

Observed result:

- delta callback: HTTP 200;
- terminal result callback: HTTP 200;
- SSE body contained `orchestrator.turn.delta` and the exact streamed text;
- API, worker and Telegram systemd units were active again afterward.

The worker parser accepts Pi JSON `message_update` events with
`assistantMessageEvent.type=text_delta`. Deltas are sent through the worker
token boundary, fenced by turn generation, persisted as project events, and
rendered by the dashboard's authenticated reconnecting SSE reader. The final
`message_end` text remains authoritative for durable assistant-message
publication. This proves the relay boundary, not a new provider call.
