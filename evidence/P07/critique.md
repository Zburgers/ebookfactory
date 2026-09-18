# P07 usage lead critique

- Revision reviewed: `b2e1d5a`; an independent high-effort critic session was unavailable, so no separate agent identity is claimed.
- Pass: same call ID is replay-safe and finalization preserves the first accepted aggregate; unknown cost fields stay null.
- Finding [high]: no real provider call is wired from Pi to the recorder, so provider attribution and H6 are not passed.
- Finding [medium]: corrections currently need a future explicit correction event/row rather than silently replacing finalized values; implement that before production retries.
- Finding [medium]: quota snapshots are still schema-only and unavailable/auth-required states are not surfaced in the UI.
- Confidence: 76/100 for the accounting primitive; direct unit evidence is good, but live integration and quota proof are absent.
