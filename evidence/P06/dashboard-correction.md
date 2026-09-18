# P06 dashboard and review evidence

- UTC: 2026-09-18T18:48Z–18:55Z; the same-origin FastAPI dashboard loaded in Chromium 153 at `http://127.0.0.1:18080/` and exposed Projects, Studio, Usage and Settings navigation.
- API/browser boundary: Chromium loaded the generated project cards and new usage/document sections; API smoke checks returned 200 for health, project sections, usage, review findings and export downloads.
- Review journey: revision `c22d0a5c-3be5-42d1-9ad8-327f746c0539` received finding `c88fb98e-bdf2-4967-8ae8-07a8ce4fede0`, then the owner revision `0c185f6b-0741-4ef1-93dd-56dba930190e` resolved it. The dashboard now lists findings, edits sections with stale-parent protection, and renders export download links.
- Accessibility/reconnect surface: existing labeled forms, `aria-live` message/timeline/review regions, keyboard-native buttons/links, persisted event cursors and narrow-screen CSS remain in the delivered shell. A full interactive owner journey through Chromium is still less strong than a dedicated browser automation trace.
