# MiniWord

A minimal word processor in python. In development but, already great.

![Screenshot](https://codeberg.org/chrisecker/miniword/raw/branch/main/screenshots/miniword_mrz26.png)
---


## Features

- **Simple & Diffable File Format** – Clean file structure, perfect for version control (Git).
- **Markdown Support** – Native ability to read and write Markdown.
- **Plugin System** – Expand the editor's features with your own Python scripts.
- **Minimalist Design** – A clean, distraction-free interface.
- **Lightweight & Fast** – Built with Python for a snappy user experience.

## Install

```bash
cd miniword
pip install .
```

If you want to install the plugins (you probably will)
```bash
mkdir -p ~/.miniword/plugins
cp examples/*.py ~/.miniword/plugins
```

## License

This project is licensed under the GNU General Public License v3.0 –
see LICENSE for details. Contact me if you need something else.
