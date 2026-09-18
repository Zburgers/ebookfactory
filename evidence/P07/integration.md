# P07 usage-accounting evidence

- Code revision: `b2e1d5a`
- UTC: 2026-09-18
- Behavior: normalized usage rows use the provider call UUID as the durable dedupe key; repeated stream aggregates return the existing call and repeated finalization does not overwrite accepted totals
- Unknowns: `estimated_cost` and `reported_billed_cost` remain JSON `null` until an observed pricing/billing source exists; no subscription spend is inferred from tokens
- API: `/usage/calls`, `/usage/calls/{call_id}/finalize` and `/usage` are generated in the OpenAPI/TypeScript contract
- Verification: the replay test and full `make verify` pass; PostgreSQL recovery/API target passes 9 tests and the web/worker/containment checks pass
- Limitation: no live Pi provider call is yet routed through this recorder, no quota adapter is proven, and the usage score/H6 remain unclaimed
