# Installing MiniWord

MiniWord runs on Linux, Windows and macOS. The easiest way is a pre-built package from the [Releases page](https://github.com/chrisecker/miniword/releases); on Linux, MiniWord can also be installed with pip.

- [Pre-built packages](#pre-built-packages): [Linux](#linux) · [Windows](#windows) · [macOS](#macos)
- [Installing with pip](#installing-with-pip): [Linux](#linux-1) · [Windows](#windows-1) · [macOS](#macos-1)
- [Desktop integration on Linux](#desktop-integration-on-linux)
- [Running without installation](#running-without-installation)
- [Switching and uninstalling](#switching-and-uninstalling)

## Pre-built packages

### Linux

`.deb` and `.rpm` packages for Debian 12, Ubuntu 24.04, Fedora 42 or newer, for x86_64 and ARM. They include `uharfbuzz` and `mistune`; the package manager installs wxPython and the other dependencies from the distribution:

```bash
sudo apt install ./miniword_*_amd64.deb      # Debian, Ubuntu (ARM: *_arm64.deb)
sudo dnf install ./miniword-*.x86_64.rpm     # Fedora (ARM: *.aarch64.rpm)
```

The package adds MiniWord to the menu, opens `.txl` files with it and offers it for `.md` and `.txt` files ("Open with"). On other distributions, install with pip (see below).

### Windows

Download the `.exe` and run it. All dependencies are included. The installer registers `.txl` files and offers MiniWord for `.md` and `.txt` files ("Open with").

**Note** that MiniWord is not yet optimised for Windows. While it mostly works, the GUI is less polished and startup takes a bit longer.

### macOS

Download the `.dmg`, open it, and drag `MiniWord.app` into your Applications folder. All dependencies are included. MiniWord then opens `.txl` and `.md` files from the Finder and is offered for `.txt` files.

**First launch:** MiniWord isn't (yet) signed with a paid Apple Developer ID, so macOS blocks it the first time with "MiniWord can't be opened because Apple cannot check it for malicious software." To allow it, no Terminal needed:

1. Double-click MiniWord in Applications once and dismiss the warning.
2. Open **System Settings → Privacy & Security**, scroll down to the **Security** section.
3. Click **Open Anyway** next to the MiniWord entry, then confirm with your password or Touch ID.
4. Open MiniWord again and confirm **Open** in the dialog that appears.

This is a one-time step per installed version.

**Note** that MiniWord is not yet optimised for macOS (tested on Apple Silicon; Intel Macs are untested). While it works, some GUI elements aren't as polished as on Linux.

## Installing with pip

You need Python >= 3.9 and wxPython >= 4.0. pip also installs `cairocffi`, `mistune` (Markdown) and `uharfbuzz` (ligatures, non-Latin scripts, font fallback). `fonttools`, needed for non-Latin scripts on Windows only, comes with the `full` extra.

The commands install the latest release from PyPI; to install from a source folder instead, replace `miniword` by `.`.

### Linux

wxPython and cairocffi come from the distribution (pip would compile wxPython), the rest from pip:

```bash
sudo apt install python3-wxgtk4.0 python3-cairocffi fontconfig    # Debian, Ubuntu
sudo dnf install python3-wxpython4 python3-cairocffi fontconfig   # Fedora
sudo pip install --break-system-packages miniword
```

pip only adds what the distribution doesn't provide. `--break-system-packages` is needed on Debian and Ubuntu for any installation with pip outside a virtual environment. Then add MiniWord to the desktop menu, see [Desktop integration on Linux](#desktop-integration-on-linux).

### Windows

```
pip install "miniword[full]"
```

wxPython bundled `libcairo-2.dll` up through 4.2.1, so this alone was enough for `cairocffi` to bind to it. wxPython >= 4.2.2 dropped the bundled DLL (an upstream regression, reported at wxWidgets/Phoenix), so on those versions install a Cairo runtime yourself first, e.g. the [GTK3 runtime for Windows](https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer).

(Advanced: alternatively, download just `libcairo-2.dll` from [wxWidgets/Phoenix's packaging assets](https://github.com/wxWidgets/Phoenix/blob/wxPython-4.2.1/packaging/msw-cairo/x64/bin/libcairo-2.dll) and drop it into your installed `wx` package folder, e.g. `site-packages/wx/`.)

If you skip this and see an error mentioning a missing `libcairo-2.dll`, install a Cairo runtime as described above (or downgrade to `wxPython<4.2.2`).

### macOS

`fontconfig` must be installed via Homebrew:

```
brew install fontconfig
pip install miniword
```

## Desktop integration on Linux

The packages do this themselves. After an installation with pip, add MiniWord to your desktop menu:

```
miniword --install-desktop
```

This writes a menu entry, the `.txl` file type and the icon into `~/.local/share` (no root rights needed; pip itself can't do this). MiniWord then opens `.txl` files and is offered for `.md` and `.txt` files; add `--markdown` to make it the default application for `.md` too. `miniword --uninstall-desktop` removes it again.

## Running without installation

From a source folder, with the dependencies installed:

```
python miniword.py
```

Alternatively, double-click `miniword.py` in your file explorer.

## Switching and uninstalling

| Installed with | Uninstall |
|---|---|
| `.deb` | `sudo apt remove miniword` |
| `.rpm` | `sudo dnf remove miniword` |
| pip (Linux) | `miniword --uninstall-desktop`, then `sudo pip uninstall --break-system-packages miniword` |
| Windows installer | Settings → Apps → MiniWord → Uninstall |
| macOS | Move `MiniWord.app` to the Trash |

To switch from pip to a package on Linux, uninstall the pip installation first, including `--uninstall-desktop`: a menu entry in `~/.local/share` takes precedence over the package's and would still start the old installation.

Configuration and plugins stay when MiniWord is uninstalled:

| Platform | Folder |
|---|---|
| Linux | `~/.config/miniword/` |
| Windows | `%APPDATA%\miniword\` |
| macOS | `~/Library/Application Support/miniword/` |
