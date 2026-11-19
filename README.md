# MiniWord

**Real pages. Plain files.**

A small desktop word processor that typesets real pages and stores your documents as readable text: diff them, script them, extend MiniWord in Python.

**[⬇ Download for Windows, macOS and Linux](https://github.com/chrisecker/miniword/releases)**

<!-- hero.png is exported from screenshots/hero/hero.svg (Inkscape) -->
![MiniWord editing a page with a photo, footnote and table; the inspector shows the local formatting of the selected words](https://codeberg.org/chrisecker/miniword/raw/branch/main/screenshots/hero/hero.png)

## Why MiniWord

- **Real page layout:** headers and footers, footnotes, tables, images and hyphenation, typeset by MiniWord itself, so the page looks the same every time.
- **Your files stay readable:** a simple plain text format that works with git, diff, scripts and AI tools.
- **Markdown in, PDF out:** open Markdown files and export PDFs with selectable text and embedded fonts.
- **Native and fast:** a desktop app that starts in a blink. No browser, no account, no cloud.
- **Hackable:** Python plugins add menu commands and import, export and paste filters.

## Status

MiniWord is young but already usable. Please keep backups of important documents. Found a bug or missing something? [Open an issue](https://codeberg.org/chrisecker/miniword/issues).

## Install

Download the installer for Windows (`.exe`), macOS (`.dmg`) or Linux (`.deb`, `.rpm`) from the [Releases page](https://github.com/chrisecker/miniword/releases). On Linux, MiniWord can also be installed with pip. Details and other systems: see [INSTALL.md](https://codeberg.org/chrisecker/miniword/src/branch/main/INSTALL.md).

## Documentation

- [Command line](https://codeberg.org/chrisecker/miniword/src/branch/main/docs/commandline.md): convert documents without a window, e.g. `miniword report.md -o report.pdf`
- [Plugins](https://codeberg.org/chrisecker/miniword/src/branch/main/docs/plugins.md): install Python plugins, with examples
- [File format](https://codeberg.org/chrisecker/miniword/src/branch/main/docs/txl_format.md): the `.txl` format
- [Hacking](https://codeberg.org/chrisecker/miniword/src/branch/main/docs/hacking.md): run the tests and demos

## License

This project is licensed under the GNU Lesser General Public License v3.0 or later - see LICENSE (LGPL) and COPYING (GPL, which the LGPL builds on) for details. Contact me if you need something else.

The bundled hyphenation patterns (`miniword/hyphenation/patterns/`) come from the hyph-utf8 package and have their own permissive licences - see `miniword/hyphenation/patterns/LICENSES.md`.
