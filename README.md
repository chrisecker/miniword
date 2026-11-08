# MiniWord

A small word processor. In development but already great.

![Screenshot](https://codeberg.org/chrisecker/miniword/raw/branch/main/screenshots/miniword.png)

## Key Aspects

- Real WYSIWYG editing (no HTML layer, no embedded browser)
- Lightweight and fast startup
- Clean, simple file format (human-readable, diff-friendly, git-friendly, AI-friendly)
- Good Markdown support
- Extensible via Python-plugins

## Install

Download the installer for Windows (`.exe`), macOS (`.dmg`) or Linux (`.deb`, `.rpm`) from the [Releases page](https://github.com/chrisecker/miniword/releases). On Linux, MiniWord can also be installed with pip. Details and other systems: see [INSTALL.md](INSTALL.md).

## Command line

```
miniword [-h] [--debug] [--install-desktop] [--uninstall-desktop]
         [--version] [file]
```

(from a source folder without installation: `python miniword.py [options] [file]`)

| Option | Meaning |
|---|---|
| `file` | Document to open: `.txl`, or a format a plugin imports, e.g. Markdown (`.md`). Without it, MiniWord starts with a new document. |
| `-h`, `--help` | Show the options and exit. |
| `--version` | Show the version and exit. |
| `--debug` | Print debug output of the page layout. |
| `--install-desktop` | Linux: add MiniWord to the desktop menu and open `.txl` files with it (see [INSTALL.md](INSTALL.md)). |
| `--uninstall-desktop` | Linux: undo `--install-desktop`. |

## Hacking

Run the full test suite:

```
python test_all.py
```

Run tests for a single module:

```
python runtests.py miniword/layout/pagegen.py
```

Run a specific test or demo:

```
python runtests.py miniword/ui/searchtool.py test_00
python runtests.py miniword/texteditor/textcanvas.py demo_00
```

## Plugins

MiniWord is extensible via Python plugins. To install a plugin, copy the `.py` file into the plugins directory for your platform:

| Platform | Plugins directory                                 |
| -------- | ------------------------------------------------- |
| Linux    | `~/.config/miniword/plugins/`                     |
| macOS    | `~/Library/Application Support/miniword/plugins/` |
| Windows  | `%APPDATA%\miniword\plugins\`                     |

Example plugins are provided in the `examples/` directory:

| File            | Description                           |
| --------------- | ------------------------------------- |
| `wordcount.py`  | Shows a live word count               |
| `txtfilter.py`  | Filter for importing plain text files |

To install all example plugins on Linux:

```
mkdir -p ~/.config/miniword/plugins
cp examples/*.py ~/.config/miniword/plugins
```

## License

This project is licensed under the GNU Lesser General Public License v3.0 or later - see LICENSE (LGPL) and COPYING (GPL, which the LGPL builds on) for details. Contact me if you need something else.

The bundled hyphenation patterns (`miniword/hyphenation/patterns/`) come from the hyph-utf8 package and have their own permissive licences - see `miniword/hyphenation/patterns/LICENSES.md`.
