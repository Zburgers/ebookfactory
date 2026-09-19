# Ebook Factory dashboard

The dashboard is a small vanilla HTML/CSS/JavaScript client served by the API.
It provides Projects, Studio, Usage and Settings views over the existing owner
token, JSON and SSE endpoints. Studio keeps the real chat, brief approval,
review, chapter, event and export flows; Settings keeps the live Pi catalog and
the orchestration, drafting and review model selectors.

Artifact downloads and image previews use authenticated fetches and short-lived
object URLs. Keep artifact routes owner-protected; a plain `href` or `img src`
cannot carry the dashboard's bearer token. The Studio stage rail is derived
from persisted project state, sections, findings, artifacts and replayed events,
so the owner can see the current checkpoint even when no new event is arriving.

The UI deliberately has no client framework or bespoke component library. Keep
the existing element IDs and endpoint contracts stable when changing the
presentation. `npm run verify` checks the client syntax; the API serves this
directory directly in deployment, so `atlas-cover.png` must remain at this
directory's root.
