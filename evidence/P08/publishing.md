# P08 publishing evidence

- UTC: 2026-09-18T18:43Z–18:55Z; maintained packages pinned in `apps/api/pyproject.toml`: EbookLib 0.20, python-docx 1.2.0, ReportLab 4.4.9 and Pillow 12.3.0.
- Real owner-revision package: `var/artifacts/exports/0c185f6b-0741-4ef1-93dd-56dba930190e/` contains `book.epub` (SHA-256 `f8c29fcd998475921644044e9e117953e2f7657412884e9128e903218e09b98c`), `book.pdf` (`1d9a1c5329c2ff2b6d31e392c8007c4c0a908ab4e06966516012b33a5b7fd1dd`), `book.docx` (`3c038ca0d70c60dbddb25bce6ce842f2a8ce309aa3e7c4ff604c839aef6100d9`), `book.md` (`7cc422c46acf0ace1cd4ddee8c9fe275983574c9281eb3ab6762c1c86f6c885b`), RGB cover (`f5683a1742a1cc6a8e98390d1a3147a28a0d069b9edf8a5fc8494be341f90627`), metadata, sources, manifest and validation files.
- Structural evidence: API returned `package_state: structurally_validated`; EPUB zip integrity/navigation, DOCX XML members, PDF `%PDF-` signature, cover RGB mode and 1600×2560 dimensions were checked. Download route returned HTTP 200 and hashes match PostgreSQL artifact rows.
- Same package route generated a fiction package at `var/artifacts/exports/ecc7a1aa-6781-41cb-9ef7-4788e3fd00db/` with the same ten immutable members.
- EPUBCheck evidence (2026-09-19): the pinned local runner
  `scripts/validate-epub.sh` uses `epubcheck-standalone-cli` 5.4.0-build2 from
  `tools/epubcheck/package-lock.json`. Against
  `apps/api/var/artifacts/exports/d7c5f819-c4dc-4491-94a6-a133491592ba/book.epub`
  (SHA-256
  `37ab2151798eaa4fd4d59aa0f29632f008fcdd42bff29522c7f9c4918b23277c`), the
  command returned `0 fatals / 0 errors / 0 warnings / 0 infos`.
- Kindle Previewer was not run, so `kindle_preview_pending` remains explicit
  and no Amazon certification is claimed. PDF is a reading copy, not a KDP
  print guarantee.
