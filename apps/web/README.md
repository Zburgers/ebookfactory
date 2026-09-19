# Ebook Factory studio preview

This worktree now contains the first visual dashboard slice for the documented product surface. It is a static React/Vite preview, not a claim that the API, database, worker, exports, or Telegram adapter exist.

Surfaces included:

- Projects library with expandable project rows
- Studio landing surface with current project, brief, draft map, review room, package state, pinned production checkpoints, and review notes
- Usage ledger with observed, pending, and unknown provider states
- Settings with provider, Telegram, and execution-boundary states

Run locally from this directory:

```sh
npm install
npm run dev
```

`npm run build` is the focused frontend check. The generated cover asset is stored at `public/atlas-cover.png`; runtime wiring remains a later packet.
