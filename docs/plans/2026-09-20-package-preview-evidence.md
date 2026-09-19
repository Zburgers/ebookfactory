# Package preview evidence plan

## Objective

Make the final ebook handoff actionable without claiming Amazon certification:
the owner can record a Kindle Previewer or KDP Online Previewer result against
the exact generated EPUB hash, see it in the journey and replay, and keep a
failed visual check attached to the package until a new immutable package is
built.

## Contract

- The API accepts only `verified` or `issues_found`, an allowed preview surface,
  the exact SHA-256 of the package's `book.epub`, and bounded notes.
- The server verifies that the EPUB belongs to the owner project, is a valid
  package member, and still matches its persisted bytes/hash before appending
  an immutable `package.preview_reviewed` event.
- A verified result is owner evidence for that exact artifact, not Amazon
  acceptance or publication. A later package hash has no inherited result.
- The dashboard shows the preview checkpoint, records the tool/surface/version
  and notes, and includes the event in the control-room timeline.

## Verification

- API tests cover exact-hash binding, project scoping, missing EPUBs, rejected
  decisions, required issue notes, and replay payloads.
- View-model tests cover the new Kindle stage and event presentation.
- Full web/API/worker/operational verification and `git diff --check` run before
  commit; no owner token or KDP account is required for these checks.
