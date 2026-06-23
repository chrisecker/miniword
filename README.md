# MiniWord

A minimal word processor in python. In development but already great.

![Screenshot](https://codeberg.org/chrisecker/miniword/raw/branch/main/screenshots/miniword.png)

## Key Aspects

- Real WYSIWYG editing (no HTML layer, no embedded browser)
- Lightweight and fast startup
- Clean, simple file format (human-readable, diff-friendly, git-friendly, AI-friendly)
- Good Markdown support
- Extensible via Python-plugins

## Install from a pre-built package

Pre-built installers for Windows (`.exe`) and macOS (`.dmg`) are published on the [Releases page](https://github.com/chrisecker/miniword/releases) for each tagged version, with all dependencies (including the optional extras) already bundled — nothing else to install. On Linux, install from source instead (see below); no separate installer is provided there.

### Windows

Download the `.exe` from the [Releases page](https://github.com/chrisecker/miniword/releases) and run it.

### macOS

Download the `.dmg` from the [Releases page](https://github.com/chrisecker/miniword/releases), open it, and drag `MiniWord.app` into your Applications folder.

**First launch:** MiniWord isn't (yet) signed with a paid Apple Developer ID, so macOS blocks it the first time with "MiniWord can't be opened because Apple cannot check it for malicious software." To allow it, no Terminal needed:

1. Double-click MiniWord in Applications once and dismiss the warning.
2. Open **System Settings → Privacy & Security**, scroll down to the **Security** section.
3. Click **Open Anyway** next to the MiniWord entry, then confirm with your password or Touch ID.
4. Open MiniWord again and confirm **Open** in the dialog that appears.

This is a one-time step per installed version.

## Install from source

Miniword is developed under Linux. In principle it should run under Windows and Mac as well.

You always need Python >= 3.9 and wxPython >= 4.0. Further required dependencies vary between platforms — see the per-platform instructions below.

Three optional packages add extra features and are all installed together via the `full` extra (`pip install ".[full]"`): `uharfbuzz` adds ligatures and non-Latin script support, `fonttools` is needed for non-Latin scripts specifically on Windows, and `mistune` enables richer Markdown import (without it, a built-in parser handles the common subset).

### Running without installation

```
python miniword.py
```

Alternatively, double-click `miniword.py` in your file explorer.

### Linux

Install system dependencies:

```
sudo apt install python3-wxgtk4.0 fontconfig
```

Then install miniword (this also pulls in `cairocffi`):

```
cd miniword
pip install .
```

For ligature support, non-Latin scripts, and richer Markdown import, install with the `full` extra instead:

```
pip install ".[full]"
```

If you want to register MiniWord to the desktop (you probably will):

```
cp miniword/icons/miniword.svg ~/.local/share/icons/
cp miniword.desktop ~/.local/share/applications/
```

### Windows

No separate Cairo installation is needed — wxPython already bundles `libcairo-2.dll`, and `pip install .` pulls in `cairocffi` to bind to it.

```
cd miniword
pip install ".[full]"   # full installs uharfbuzz, fonttools, mistune: ligatures, non-Latin scripts, richer Markdown import
```

MiniWord stores its configuration and plugins in `%APPDATA%\miniword\` (e.g. `C:\Users\<you>\AppData\Roaming\miniword\`).

**Note** that MiniWord is not yet **optimised** for Windows. While it mostly works, the GUI is less polished and startup takes a bit longer.

### macOS

`fontconfig` must be installed via Homebrew:

```
brew install fontconfig
```

Then install miniword (this also pulls in `cairocffi`):

```
cd miniword
pip install ".[full]"   # full installs uharfbuzz, mistune: ligatures, non-Latin scripts, richer Markdown import
```

MiniWord stores its configuration and plugins in `~/Library/Application Support/miniword/`.

**Note** that MiniWord is not yet **optimised** for macOS (tested on Apple Silicon; Intel Macs are untested). While it works, some GUI elements aren't as polished as on Linux.

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

This project is licensed under the GNU General Public License v3.0 - see LICENSE for details. Contact me if you need something else.
