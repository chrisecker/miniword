# Changelog

All notable changes to MiniWord are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Command line option `-o OUTFILE`: write PDF, TXL, Markdown or plain text without opening a window.
- Python syntax colouring in code blocks.

### Changed
- The "Normal" style is now an ordinary style, found by its role: it can be edited, deleted and is saved with the document. Roles are shown and set in the paragraph style dropdown.
- Images larger than the text area are limited in the layout.
- Linux packages are built per architecture and include uharfbuzz and mistune; uharfbuzz is now required.
- `--markdown` removed: `.md` and `.txt` are offered under "Open with", as with the installers.
- Installation instructions moved to `INSTALL.md`.

### Fixed
- Formatting marks skip pages outside the view (much faster repaint of large documents).

## [0.2.2] - 2026-11-07

### Added
- New elements: code blocks (with colouring), checkboxes, horizontal rules, raw/inline HTML.
- Quotes with quote levels, inspector parameters and HTML import; Markdown alerts.
- List continuation paragraphs; Backspace at the start of a list item removes its marker.
- Linux packages (`.deb`, `.rpm`) and file associations for `.txl`, `.md` and `.txt`; `miniword --install-desktop` registers MiniWord on Linux.
- Markdown: escaping on export, hard breaks, entities, HTML blocks, start numbers, column alignment, alerts.

### Changed
- Redesigned elements panel; tidier side panels.
- Space around tables and code blocks without empty paragraphs.
- Clipboard uses TXL instead of pickle (no code execution on paste).
- TXL: lower-case container types (`table`, `code`; old names are still read); `[blobs]` after `[document]`.
- mistune is now mandatory; the built-in Markdown parser was removed.
- File dialogs start in the folder of the last opened or saved file; Save As offers TXL and Markdown together; new windows fit the page.
- Too large images are drawn clipped and scaled while loading.
- Faster layout of large documents (delayed scroll updates).
- License: LGPL v3 or later everywhere; GPL text added (`COPYING`).

### Fixed
- Cursor was drawn too low by the font's descent.
- Cell alignment was not written to TXL files.
- Markdown export of nested lists and nested formatting.
- Exceptions caused by destroyed windows.

## [0.2.1] - 2026-10-07

### Added
- Linked images (instead of embedded): import, paste, loading of web images, error reasons, relative and absolute paths.
- Progress bar for long running layout updates.
- Indent/dedent with 4 spaces in code mode.
- Keyboard shortcuts shown in the menus.

### Changed
- Character formatting without a selection applies to the word at the cursor.
- Shortcuts: Ctrl-B (bold), Ctrl-I (italics), Ctrl-U (underline).
- Markdown export of tables keeps formatting, links and images; HTML and Markdown import keep the formatting of table cells.
- Image sizes from `<img>` tags are used.
- Much faster line wrapping and measuring (moby.txl: 17 s → 3 s).
- Improved command line interface and documentation.

### Fixed
- Paste of HTML, Markdown and images.
- Images wobbling while building large documents.
- Measuring of characters from a fallback font.
- Image panel did not update the path after Save As.

## [0.2.0] - 2026-10-06

### Added
- New page layout engine: complete rewrite of page generation, including tables, images and footnotes.
- Hyphenation, protected and soft hyphens; CJK line breaking with kinsoku.
- Widow and orphan control, keep with next.
- Right indent, block offset and border lines for paragraphs.
- Tab stops.
- Simple headers and footers (styles selected by role).
- Footnotes in tables and in the file format.
- New image storage (blob architecture).
- Paste of HTML and Markdown keeps structure.
- "All supported files" as default filter for Open and Import.

### Changed
- Redesigned inspector: three tabs, scrollable panels, rounding in unit input.
- Normal style uses line spacing 1.15 and 7 pt space after.
- Improved Markdown menu and initial window size.

### Fixed
- Paragraph properties were applied to whole tables instead of the selected cells.
- Trailing spaces hung over the right edge when aligning.
- List counters were not always reset after section changes; unnumbered headings restart the item counter.
- Wrong text metrics.
- Markdown import lost H3+ headings indented by up to 3 spaces.
- Built-in plugins were loaded twice.
- Paste of plain text crashed and blocked the clipboard.
- Crash in the style inspector with different border sides.

## [0.1.10] - 2026-07-01

### Added
- "Show Markdown" menu with live preview window.

### Fixed
- `runtests.py` module name resolution for absolute and Windows paths.

## [0.1.9] - 2026-07-01

### Fixed
- Windows build bundles `libcairo-2.dll` (dropped upstream by wxPython ≥ 4.2.2).

## [0.1.8] - 2026-07-01

### Fixed
- Footnotes in tables and in footnotes.
- Crash in "Fit to Page".
- Table size popup could not be closed on Windows.
- wxPython's bundled cairo DLL is found on Windows source installs.

## [0.1.7] - 2026-06-23

### Fixed
- Markdown import with mistune was broken.

## [0.1.6] - 2026-06-23

### Fixed
- macOS bundle is re-signed after adding cairo/fontconfig files.

## [0.1.5] - 2026-06-23

### Changed
- fontconfig and mistune bundled in the macOS and Windows builds.
- README restructured (installer vs. source install, macOS Gatekeeper notes).

## [0.1.4] - 2026-06-23

### Changed
- Application renamed to "MiniWord".

### Fixed
- Installation on macOS.
- Page numbering.

## [0.1.3] - 2026-06-19

### Changed
- Much better font rendering on Windows (font cache).

### Fixed
- Build problems.

## [0.1.2] - 2026-06-18

### Added
- Binary builds include all optional dependencies.

### Fixed
- High DPI support on Windows (manifest, DPI awareness).
- Cursor was sometimes drawn too small.

## [0.1.1] - 2026-06-18

### Fixed
- Plugins were missing in the Windows installer.

## [0.1.0] - 2026-06-18

First public release.

- WYSIWYG word processor with paragraph and character styles, base styles and lists.
- Tables, images, footnotes, hyperlinks, sub-/superscript and strike-through.
- One and two column page views, outline and footnote panels, search.
- Markdown import and export; human-readable TXL file format.
- Printing and PDF export.
- Python plugins.
- Installers for Windows and macOS, package on PyPI.

[Unreleased]: https://codeberg.org/chrisecker/miniword/compare/v0.2.2...HEAD
[0.2.2]: https://codeberg.org/chrisecker/miniword/compare/v0.2.1...v0.2.2
[0.2.1]: https://codeberg.org/chrisecker/miniword/compare/v0.2.0...v0.2.1
[0.2.0]: https://codeberg.org/chrisecker/miniword/compare/v0.1.10...v0.2.0
[0.1.10]: https://codeberg.org/chrisecker/miniword/compare/v0.1.9...v0.1.10
[0.1.9]: https://codeberg.org/chrisecker/miniword/compare/v0.1.8...v0.1.9
[0.1.8]: https://codeberg.org/chrisecker/miniword/compare/v0.1.7...v0.1.8
[0.1.7]: https://codeberg.org/chrisecker/miniword/compare/v0.1.6...v0.1.7
[0.1.6]: https://codeberg.org/chrisecker/miniword/compare/v0.1.5...v0.1.6
[0.1.5]: https://codeberg.org/chrisecker/miniword/compare/v0.1.4...v0.1.5
[0.1.4]: https://codeberg.org/chrisecker/miniword/compare/v0.1.3...v0.1.4
[0.1.3]: https://codeberg.org/chrisecker/miniword/compare/v0.1.2...v0.1.3
[0.1.2]: https://codeberg.org/chrisecker/miniword/compare/v0.1.1...v0.1.2
[0.1.1]: https://codeberg.org/chrisecker/miniword/compare/v0.1.0...v0.1.1
[0.1.0]: https://codeberg.org/chrisecker/miniword/releases/tag/v0.1.0
