# MiniWord

A minimal word processor in python. In development but already great.

![Screenshot](https://codeberg.org/chrisecker/miniword/raw/branch/main/screenshots/miniword_10apr26.png)

## Key Aspects

- Real WYSIWYG editing (no HTML layer, no embedded browser)
- Lightweight and fast startup
- Minimal dependencies (wxPython + Cairo)
- Clean, simple file format (human-readable, diff-friendly, git-friendly, AI-friendly)
- Good Markdown support
- Extensible via Python-plugins


## Dependencies

Miniword is developed under Linux. In principle it should run under Windows and Mac as well.

The following dependencies are required:

- Python >= 3.9
- wxPython >= 4.0
- Cairo >= 1.2

On Debian all dependencies are installed by

```
sudo apt install python3-wxgtk4.0 python3-cairo
```

## Testing

Running miniword without installation is possible: 

```
cd miniword
python -m miniword
```

## Install (Linux)

Install all dependencies. Then

```
cd miniword
pip install .
```

MiniWord stores its configuration and plugins in `~/.config/miniword/` (Linux).
If you want to install the plugins (you probably will)

```
mkdir -p ~/.config/miniword/plugins
cp examples/*.py ~/.config/miniword/plugins
```

If you want to register MiniWord to the desktop (you probably will)

```
cp miniword/icons/miniword.svg ~/.local/share/icons/
cp miniword.desktop ~/.local/share/applications/
```

## Install (Windows)

Installation on Windows is possible, but more challenging.
You should use cairocffi instead of pycairo:

```
pip install cairocffi
```

No separate Cairo installation is needed — wxPython already bundles `libcairo-2.dll`.

If you want to install the plugins (you probably will)

```
mkdir %APPDATA%\miniword\plugins
copy examples\*.py %APPDATA%\miniword\plugins
```

MiniWord stores its configuration and plugins in `%APPDATA%\miniword\`
(e.g. `C:\Users\<you>\AppData\Roaming\miniword\`).

**Note** that MiniWord is not yet **optimised** for Windows. While it mostly works, the rendering quality is lower and startup times are a bit slow.

## Install (macOS)

If you want to install the plugins (you probably will)

```
mkdir -p ~/Library/Application\ Support/miniword/plugins
cp examples/*.py ~/Library/Application\ Support/miniword/plugins
```

MiniWord stores its configuration and plugins in `~/Library/Application Support/miniword/`.

**Note** that MiniWord has not been tested on macOS.

## License

This project is licensed under the GNU General Public License v3.0 â€“ see LICENSE for details. Contact me if you need something else.
