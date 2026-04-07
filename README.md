# MiniWord

A minimal word processor in python. In development but already great.

![Screenshot](https://codeberg.org/chrisecker/miniword/raw/branch/main/screenshots/miniword_2apr26.png)

## Project Goals

- **Consistent and transparent:** Simplicity. Don't hide from the user. Simple style model, no "intelligence".
- **Lightweight & Fast:** Minimal dependencies (currently wx and Cairo), no server, no cloud, no HTML/JS stack. A fast, always-available tool that starts instantly and works offline.
- **AI- and human-friendly file format:** TXL is plain text, diff-able, git-able, human readable, and easy for language models to inspect and generate.
- **Security by design:** The document is passive data – no executable code, no macro language, no implicit network access.
- **Open system:** Extensible via Python plugins, embeddable as a library, no proprietary lock-in.

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

## License

This project is licensed under the GNU General Public License v3.0 – see LICENSE for details. Contact me if you need something else.
