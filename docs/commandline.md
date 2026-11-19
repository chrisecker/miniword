# MiniWord command line

```
miniword [-h] [-o OUTFILE] [--template TEMPLATE] [--set KEY=VALUE]
         [--debug] [--install-desktop] [--uninstall-desktop]
         [--version] [file]
```

(from a source folder without installation: `python miniword.py [options] [file]`)

| Option | Meaning |
|---|---|
| `file` | Document to open: `.txl`, or a format a plugin imports, e.g. Markdown (`.md`). Without it, MiniWord starts with a new document. |
| `-o`, `--output OUTFILE` | Write the document to `OUTFILE` and exit, without a window. The format follows the extension: `.pdf`, `.txl`, `.md`, `.txt`. Example: `miniword report.md -o report.pdf` |
| `--template TEMPLATE` | With `-o`: take the page setup (paper, margins, header and footer, …; not title and author) from the document `TEMPLATE` (`.txl`), and for each style with a role (normal, heading 1, list, …) the values of the template's style with the same role. Example: `miniword report.md -o report.pdf --template letter.txl` |
| `--set KEY=VALUE` | With `-o`, repeatable: a document setting, applied after `--template`. Keys: `paper` (`A4`, `A5`, `Letter`, … or `170x240mm`), `margin_top`/`_right`/`_bottom`/`_left` (`2cm`, `20mm`, `1in`, `12pt`), `title`, `author`, `language`, `hyphenation` (`yes`/`no`), `header_left`/`_center`/`_right` and `footer_…` (`page`, `page_pages`, `title`, `author`, `date`, `chapter`, `section`, `none`, `text:Your text`), `header_footer_first_page`, `header_footer_mirror`. Example: `--set paper=A5 --set margin_left=2cm` |
| `-h`, `--help` | Show the options and exit. |
| `--version` | Show the version and exit. |
| `--debug` | Print debug output of the page layout. |
| `--install-desktop` | Linux: add MiniWord to the desktop menu and open `.txl` files with it (see [INSTALL.md](../INSTALL.md)). |
| `--uninstall-desktop` | Linux: undo `--install-desktop`. |
