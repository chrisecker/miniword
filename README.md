# MiniWord

A minimal word processor in python. In development but already great.

![Screenshot](https://codeberg.org/chrisecker/miniword/raw/branch/main/screenshots/miniword_10apr26.png)

## Key Aspects

- Real WYSIWYG editing (no HTML layer, no embedded browser)
- Lightweight and fast startup
- Clean, simple file format (human-readable, diff-friendly, git-friendly, AI-friendly)
- Good Markdown support
- Extensible via Python-plugins

## Dependencies

Miniword is developed under Linux. In principle it should run under Windows and Mac as well. 

Dependencies vary between platforms and prefered features. You always need Python >= 3.9 and wxPython >= 4.0.

| Dependency | Linux    | Windows  | macOS    | Notes                                      |
| ---------- | -------- | -------- | -------- | ------------------------------------------ |
| pycairo    | required | —        | required | system library                             |
| cairocffi  | —        | required | —        | alternative to pycairo; required on Windows |
| fontconfig | required | —        | required | system CLI-tool                            |
| uharfbuzz  | optional | optional | optional | needed for ligatures and non-Latin scripts |
| fonttools  | —        | optional | —        | needed for non-Latin scripts on Windows    |

## Running without installation

```
python miniword.py
```

Alternatively, double-click `miniword.py` in your file explorer.

## Install (Linux)

Install all dependencies:

```
sudo apt install python3-wxgtk4.0 python3-cairo fontconfig
```

For ligature support and non-Latin scripts install uharfbuzz:                                                                                                                              

```
pip install uharfbuzz
```

Then install miniword:

```
cd miniword
pip install .
```

If you want to register MiniWord to the desktop (you probably will):

```
cp miniword/icons/miniword.svg ~/.local/share/icons/
cp miniword.desktop ~/.local/share/applications/
```

## Install (Windows)

No separate Cairo installation is needed — wxPython already bundles `libcairo-2.dll`.

```
pip install cairocffi
pip install uharfbuzz fonttools   # optional: ligatures, non-Latin scripts
```

MiniWord stores its configuration and plugins in `%APPDATA%\miniword\` (e.g. `C:\Users\<you>\AppData\Roaming\miniword\`).

**Note** that MiniWord is not yet **optimised** for Windows. While it mostly works, the GUI is less polished and startup takes a bit longer.

## Install (macOS)

On macOS, `fontconfig` must be installed via Homebrew:

```
brew install fontconfig
pip install uharfbuzz   # optional: ligatures and non-Latin scripts
```

MiniWord stores its configuration and plugins in `~/Library/Application Support/miniword/`.

**Note** that MiniWord has not been tested on macOS.

## Hacking

Run the full test suite:

```
python test_all.py
```

Run tests for a single module:

```
python runtests.py miniword/pagegen.py
```

Run a specific test or demo:

```
python runtests.py miniword/ui/searchtool.py test_00
python runtests.py miniword/wxtextview/wxtextview.py demo_00
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
| `texelcount.py` | Shows a live texel count              |
| `txtfilter.py`  | Filter for importing plain text files |

To install all example plugins on Linux:

```
mkdir -p ~/.config/miniword/plugins
cp examples/*.py ~/.config/miniword/plugins
```

## License

This project is licensed under the GNU General Public License v3.0 - see LICENSE for details. Contact me if you need something else.
