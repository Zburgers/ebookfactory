# Owner boundary and transport repair evidence

UTC date: 2026-09-19

Revision `c165d43` and its follow-up security changes add owner bearer
authentication, worker-token separation, login throttling, durable failure
redaction, and OpenAPI security metadata. The login ledger is a short-lived
mode-600 local file shared by the three API listeners, so attempts do not reset
when a request rotates between loopback, LAN, and Tailscale listeners.

The service launcher keeps loopback HTTP for the local worker and serves
non-loopback listeners over TLS on port 6969. Live checks returned 200 health
responses over loopback HTTP and Tailscale HTTPS; a plaintext Tailscale HTTP
request was rejected. The default certificate is self-signed and therefore
requires an explicit trust installation or an operator-provided trusted
certificate/key. This is transport encryption evidence, not a claim of
authenticated server identity for the default certificate.

Focused evidence: 13 API auth/orchestrator tests, the TLS launcher check,
systemd checks, and the live service health checks pass. The independent Luna
critic still records NO-GO because default self-signed TLS permits an unsafe
browser bypass, so H1 remains open.
