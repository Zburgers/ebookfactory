# P06 SSE correction

- Revision: `54635c5`
- Added and real-PostgreSQL-tested a bounded replay SSE route at `/projects/{id}/events/stream`, with event IDs, envelopes, no-cache headers and clean close semantics.
- This is replay transport, not a live event relay; no dashboard score or H5 claim changes.
