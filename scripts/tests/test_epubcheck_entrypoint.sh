#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
entrypoint="$repo_root/scripts/validate-epub.sh"
package_json="$repo_root/tools/epubcheck/package.json"
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
fixture="$tmpdir/valid.epub"

test -x "$entrypoint"
grep -F 'epubcheck-standalone-cli' "$entrypoint" >/dev/null
grep -F '"epubcheck-standalone-cli": "5.4.0-build2"' "$package_json" >/dev/null
test -f "$repo_root/tools/epubcheck/package-lock.json"

if "$entrypoint" >/dev/null 2>&1; then
  echo "validate-epub.sh accepted a missing EPUB path" >&2
  exit 1
fi

if "$entrypoint" "$fixture" "$fixture" >/dev/null 2>&1; then
  echo "validate-epub.sh accepted extra arguments" >&2
  exit 1
fi

if "$entrypoint" "$fixture" >/dev/null 2>&1; then
  echo "validate-epub.sh accepted a nonexistent EPUB path" >&2
  exit 1
fi

python3 - "$fixture" <<'PY'
from pathlib import Path
from sys import argv
from zipfile import ZIP_STORED, ZipFile

target = Path(argv[1])
container = '''<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>'''
opf = '''<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="book-id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="book-id">urn:uuid:ebook-factory-test</dc:identifier>
    <dc:title>Validator fixture</dc:title><dc:language>en</dc:language>
    <meta property="dcterms:modified">2026-09-19T00:00:00Z</meta>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="chapter"/></spine>
</package>'''
nav = '''<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
  <head><title>Contents</title></head><body><nav epub:type="toc"><ol><li><a href="chapter.xhtml">Chapter</a></li></ol></nav></body>
</html>'''
chapter = '''<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Chapter</title></head>
<body><h1>Chapter</h1><p>Valid fixture.</p></body></html>'''
with ZipFile(target, "w") as archive:
    archive.writestr("mimetype", "application/epub+zip", compress_type=ZIP_STORED)
    archive.writestr("META-INF/container.xml", container)
    archive.writestr("OEBPS/content.opf", opf)
    archive.writestr("OEBPS/nav.xhtml", nav)
    archive.writestr("OEBPS/chapter.xhtml", chapter)
PY

output="$($entrypoint "$fixture")"
grep -F '0 fatals / 0 errors / 0 warnings / 0 infos' <<<"$output" >/dev/null

echo "epubcheck entrypoint checks passed"
