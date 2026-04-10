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

Miniword is developed under Linux but should run under Windows and Mac as well.

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

## Install

Install all dependencies. Then

```
cd miniword
pip install .
```

If you want to install the plugins (you probably will)

```
mkdir -p ~/.miniword/plugins
cp examples/*.py ~/.miniword/plugins
```

If you want to register MiniWord to the desktop (you probably will)

```
cp miniword/icons/miniword.svg ~/.local/share/icons/
cp miniword.desktop ~/.local/share/applications/
```

## License

This project is licensed under the GNU General Public License v3.0 – see LICENSE for details. Contact me if you need something else.
