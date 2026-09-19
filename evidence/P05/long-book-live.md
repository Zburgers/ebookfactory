# Live 50-page section graph

Date: 2026-09-19 (Asia/Kolkata)

The first real no-art 50-page probe used run
`526bd50c-e0ae-47fd-a6d8-74677f6b8b17`. Its outline and 13 section-draft
tasks succeeded, but server assembly failed durably because provider section
content contained nested Markdown `##` headings. Those headings collided with
the manuscript's top-level section grammar; production and review were marked
failed and no partial manuscript was accepted.

After the red/green repair, replay run
`3b440fb7-3502-4470-8caf-9709ea654c13` completed under enabled systemd
services:

```text
outline=succeeded
section-draft=succeeded (11 tasks)
production=succeeded (server assembly)
review=succeeded
run=draft_review
```

The approved target was exactly 50 pages. The persisted section revisions
contain 5,824 words, within the validator's 5,000–9,000 estimated-page-word
bound. The durable Markdown artifact is
`3b440fb7-3502-4470-8caf-9709ea654c13/book.md`, 35,941 bytes, SHA-256
`5a25de1f1b7d507d3acd7ec842f1cad549af5f3e952fa85b1985f0cf22ca9764`.

Usage lineage is real and persisted for outline, 11 section drafts, server
assembly, and review. All provider/model rows identify
`openai-codex / openai-codex/gpt-5.6-luna`; the replay recorded 14 successful
task usage rows (1 outline, 11 section-draft, 1 production assembly, 1
review). The live quota snapshot row count remained 2; live quota reads are
not used as durable book state.

This closes the real multi-section 50-page outline → section drafts → assembly
→ review evidence for H4's long-book portion. EPUBCheck/Kindle, art review,
and the separate Telegram same-conversation gate remain open.
