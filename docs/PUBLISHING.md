# Manuscript and Kindle package acceptance

EPUB is the primary reflowable Kindle ebook artifact. PDF is a reading/review copy; it is not automatically a KDP print interior. DOCX and Markdown are editable deliverables. Keep one frozen manuscript revision and generate all formats from it through maintained converters (evaluate installed Pandoc first). Do not write format encoders from scratch.

## Editorial contract

The approved brief determines audience, language, target length range, structure and content promise. Each section must fulfill its outline purpose, remain consistent with the style guide, and connect coherently to adjacent sections. Required internal review: missing/repeated sections, contradictions, unfinished placeholders, word-count bounds, duplicated passages, unsupported citations/claims, and broken references. Reviewer returns specific passages/revision IDs and repairs are versioned. Model approval alone is not proof of factual accuracy.

Nonfiction: source URLs, access dates, claim-to-source references and actual supporting evidence. Unverifiable essential claims block completion or are removed/qualified; references are never fabricated. Fiction: character/world/timeline state and unresolved plot commitments. Context retrieval uses this register plus section summaries. Keep author edits on separate versions and invalidate dependent review/export results when they change.

## Package

- `book.epub`: EPUB 3, ordered spine, navigation/TOC, language/title/author/identifier, embedded cover, semantic headings, accessible image alternatives, portable styles and no missing assets.
- `book.pdf`: readable pagination, embedded/available fonts, intact images, no clipped/blank content; explicitly labelled reading copy.
- `book.docx`, `book.md`: complete editable manuscript.
- `cover.jpg`: RGB ebook cover; current KDP guidance gives 1600 wide × 2560
  high as the ideal dimensions, requires JPEG/TIFF-compatible image data under
  50 MB, and recommends high-resolution source artwork. The exporter enforces
  RGB, 1600×2560 geometry and the 50 MB KDP ceiling, and records 300 DPI
  metadata for generated covers. Preserve illustration and typography sources
  separately.
- `metadata.json` and `metadata.csv`: title/subtitle/author/language/description/keywords/category suggestions and AI-content provenance. These are owner handoff data, not an asserted Amazon bulk-upload schema.
- `sources.json`, `manifest.json`, `validation.json`: citations, exact revision/asset hashes and checks performed.

The Studio's delivery-format selection controls the optional book files
(`book.epub`, `book.pdf`, `book.docx`, and/or `book.md`). The mandatory cover,
metadata, sources, manifest and validation files are retained in every package
so a selective delivery can still be audited. The title, author, subtitle,
description, audience, genre, keywords and language come from the exact
approved brief that owns the production run; they are not replaced by generic
factory defaults.

An export requested from any section revision in a completed multi-section run
resolves the run's dependency-fenced section revisions and packages the whole
manuscript. If the owner edits one of those sections, the new revision replaces
only that section while the other frozen run revisions remain in the package;
`metadata.json` and `manifest.json` record the complete source-revision list.
Packages created before this scope record was introduced are not silently
treated as complete: a multi-section replay fails closed until a new immutable
package is generated.

Cover guidance snapshot: Amazon's current page says the ideal size is 2560 high
× 1600 wide, the file must be under 50 MB, and the color profile should be RGB.
Re-read official requirements during implementation. Do not silently distort
generated artwork to match a ratio; use deliberate crop/layout. Cover text must
agree with metadata.

## Validation levels

1. Structural: run EPUBCheck; no errors, warnings reviewed. Verify that the
   EPUB navigation links to every manuscript heading. Open DOCX with a parser.
   Parse PDF and inspect rendered pages and document metadata. Check image
   decoding, dimensions and color mode. Compare section counts and
   representative text across all formats.
2. Reader review: render opening/middle/end, TOC, chapter breaks, long headings, lists, links, illustrations and citations. Verify no missing or repeated content. Retain redacted screenshots and tool/version output.
3. Kindle review: use Kindle Previewer or KDP's preview surface with owner-authorized access. Record exact artifact hash and observed result. On Linux where Previewer is unavailable, retain status `kindle_preview_pending`; never relabel EPUBCheck as Kindle certification.

Package states: `generated`, `structurally_validated`, `kindle_preview_pending`, `kindle_preview_verified`, `owner_approved`. Do not claim Amazon acceptance before an actual acceptance result. KDP submission/publication remains a human action.

Current KDP guidelines require disclosure of AI-generated text/images/translations. Track provenance so the owner can answer the publishing form accurately. Do not auto-submit disclosures or claim medical/legal accuracy from an AI reviewer.

Sources: [Kindle guidelines](https://kdp.amazon.com/en_US/help/topic/GU72M65VRFPH43L6), [cover criteria](https://kdp.amazon.com/en_US/help/topic/G6GTK3T3NUHKLEFX), [Previewer](https://kdp.amazon.com/en_US/help/topic/G202131170), [online preview](https://kdp.amazon.com/en_US/help/topic/G200641240), [content quality](https://kdp.amazon.com/en_US/help/topic/G200952510), [AI content disclosure](https://kdp.amazon.com/en_US/help/topic/G200672390). Checked 2026-09-19; verify again before shipping.
