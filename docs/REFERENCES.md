# Sources and reuse decisions

Inspected 2026-09-18. These are design inputs, not runtime qualification. Reverify versions and provider policies during implementation.

## Local reference baseline

- Legacy: `/home/naki/Desktop/itsthatnewshit/isthisreal/Ebookmaker`; no Git repository observed during review. Prototype queue/export behavior is not suitable for reuse.
- MuMu: `/home/naki/Desktop/itsthatnewshit/isthisreal/MuMuAINovel`, inspected commit `749186d40894b40b9fd0589791fec243d42e60c9`, GPL-3.0. No MuMu implementation code copied into this scaffold.
- Pi: observed 0.79.6, `@earendil-works/pi-coding-agent`; reverify installed types before following latest docs.

## MuMu reuse map

| Source relative to MuMu | Reuse decision |
|---|---|
| frontend/src/components/project-agent/ProjectAgentPanel.tsx | study conversation/execution-step/review interactions; reuse maintained UI primitives |
| frontend/src/components/FloatingTaskPanel.tsx | task visibility pattern; avoid inheriting backend assumptions |
| frontend/src/pages/Chapters.tsx; components/ChapterContentComparison.tsx | chapter editor/version comparison concepts |
| backend/app/models/{chapter,outline,project_agent,memory}.py | relationships and content organization; adapt generic document model |
| backend/app/services/chapter_context_service.py | inspect bounded-context strategy before designing novel continuity |
| backend/app/services/project_agent_tools.py | inspect scoped project tools; avoid direct route-to-route coupling |
| backend/app/services/background_task_service.py; app/main.py | do not port queue: in-memory execution and restart-to-failed behavior |
| backend/app/services/import_export_service.py | inspect project backup structure; not proof of Kindle formats |
| backend/app/services/cover_generation_service.py | art metadata lifecycle concept; replace provider route with proven Codex tool |

Before direct source reuse, record exact upstream file/revision, license/notice handling and modifications in a THIRD_PARTY_NOTICES file. Private use is distinct from distributing modified software; do not repeat the earlier blanket claim that personal use forces public source release. Conceptual reuse and copying expressive source are different decisions. Refer to the [GPL license](https://www.gnu.org/licenses/gpl-3.0.html) when distribution is contemplated.

## Official technical sources

- [Pi SDK](https://pi.dev/docs/latest/sdk): sessions, tools, events and runtime configuration.
- [Pi custom providers](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/custom-provider.md): provider/auth integration and normalization.
- [Pi RPC](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/rpc.md): cumulative streaming usage; guard against repeated summation.
- [Codex app-server](https://developers.openai.com/codex/app-server/): documented account quota reads/notifications; installed version may differ. No unattended image capability was verified here.
- [GitHub Copilot usage/billing](https://docs.github.com/en/copilot/how-tos/copilot-sdk/features/usage-and-billing): provider SDK reports usage and quota; not proof Pi forwards the same data. Do not invent currency conversions.
- [Telegram Bot API](https://core.telegram.org/bots/api): durable offset handling and supported message/document operations.
- [Podman run](https://docs.podman.io/en/latest/markdown/podman-run.1.html): implementation agent must verify flags/rootless networking on this host via Context7/official docs.
- [EPUBCheck](https://github.com/w3c/epubcheck): structural validation; not equivalent to Amazon acceptance.
- Kindle sources and format-specific checks are in PUBLISHING.md.

Unknowns that require experiments: exact global-auth refresh behavior under concurrent personal Pi use; credential-free sandbox model proxy; Codex subscription image route and artifact extraction; Pi/Copilot quota access; available Kindle Previewer environment; existing PostgreSQL server ownership. Do not convert any of these into assumed facts.
