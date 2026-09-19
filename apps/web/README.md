# Ebook Factory dashboard

The dashboard is a small vanilla HTML/CSS/JavaScript client served by the API.
It provides Projects, Studio, Usage and Settings views over the existing owner
token, JSON and SSE endpoints. Studio keeps the real chat, brief approval,
review, chapter, event and export flows; Settings keeps the live Pi catalog and
the orchestration, drafting and review model selectors.

The UI deliberately has no client framework or bespoke component library. Keep
the existing element IDs and endpoint contracts stable when changing the
presentation. `npm run verify` checks the client syntax; the API serves this
directory directly in deployment, so `atlas-cover.png` must remain at this
directory's root.
