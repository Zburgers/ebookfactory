# P05 production-seam evidence

- Code revision: `60af606`
- UTC: 2026-09-18
- API boundary: a leased worker can retrieve only the approved brief, project/run/task IDs, budget and cancellation epoch when worker ID and fencing generation match; the real PostgreSQL API journey covers this context request
- Pi boundary: `production.ts` uses `spawn` with `shell: false`, explicit `--mode json --print --thinking low`, disabled extensions/skills/prompt templates/tools/session, and bounded system instructions; the worker does not accept model-supplied paths or tool names
- Verification: full `make verify` passed; the production-boundary test checks low-thinking JSON flags and absence of tool flags
- Limitation: this is an execution seam, not a production acceptance run. No Pi call was made in this packet, no output was registered as a finished book, and no fiction/nonfiction journey or restart-through-container evidence is claimed
