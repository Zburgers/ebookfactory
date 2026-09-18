# P03 provider connection-test evidence

- Revision: `ca7d6bc`
- UTC: 2026-09-18T20:48:58Z
- Scope: local HTTP protocol boundary; this does not claim H1 or a live Pi answer.

## Behavior

`POST /providers/{provider}/connection-test` supports the saved
`openai-compatible` and `health-json` protocols. It uses credential references
to local environment variables, never persists or returns credential bytes,
filters usage fields, caps response reads at 64 KiB, and returns no response
body. The control route requires loopback access or the worker token.

Private and loopback provider destinations require an exact normalized origin in
`EBOOK_FACTORY_PROVIDER_ALLOWED_ORIGINS`. DNS results are validated once and
the probe connects to the already-validated address, preventing a second DNS
lookup from creating a rebinding gap. The probe uses direct HTTP(S) connections
with redirects and environment proxies disabled by construction. Endpoint
userinfo, query strings, fragments, invalid credential references, malformed
allowlist origins, and disallowed address classes are rejected.

## Evidence

The real local `ThreadingHTTPServer` tests in
`apps/api/tests/test_providers.py` cover:

- OpenAI-compatible POST path, model payload, Bearer credential delivery and
  response secret/usage redaction;
- health JSON GET behavior;
- unauthorized connection-test rejection;
- blocked versus exact-origin-allowlisted private endpoint behavior;
- malformed allowlist and secret-bearing endpoint rejection.

Focused result: `3 passed, 2 warnings`.

Independent GPT-5.6 Luna low critic review found no remaining high- or
medium-severity findings after the pinned-address and endpoint validation
repairs. The full `make verify` suite also passed; its expected optional DB
recovery skips remain external-environment dependent.
