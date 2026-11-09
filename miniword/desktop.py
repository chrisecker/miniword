# -*- coding: utf-8 -*-

"""
Desktop integration on Linux (freedesktop): a menu entry, the file type
of .txl documents and MiniWord as their default application; for
Markdown and plain text it is offered under "Open with". pip can't do
this itself (it runs no code on install and installs relative to its
environment), hence

    miniword --install-desktop
    miniword --uninstall-desktop

Everything goes into the user's data folder ($XDG_DATA_HOME, usually
~/.local/share); no root rights needed.
"""

import os
import shutil
import subprocess
import sys

MIME_TYPE = 'application/x-miniword'
# in the menu entry: .txl, and "Open with" for Markdown and plain text
MIME_TYPES = MIME_TYPE + ';text/markdown;text/plain;'

# generic-icon too: GTK 4 searches theme by theme, so the default
# application-x-generic (Adwaita) would win over miniword (hicolor)
MIME_XML = '''\
<?xml version="1.0" encoding="UTF-8"?>
<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">
  <mime-type type="application/x-miniword">
    <comment>MiniWord document</comment>
    <icon name="miniword"/>
    <generic-icon name="miniword"/>
    <glob pattern="*.txl"/>
  </mime-type>
</mime-info>
'''

ENTRY = '''\
[Desktop Entry]
Type=Application
Name=MiniWord
Comment=A small word processor
Exec={exec} %f
Icon=miniword
Terminal=false
StartupWMClass=miniword
Categories=Office;WordProcessor;
MimeType={mime_types}
'''


def data_home():
    return os.environ.get('XDG_DATA_HOME') \
        or os.path.expanduser('~/.local/share')


def _files(data_dir):
    """Where the desktop entry, the file type and the icon go."""
    return (os.path.join(data_dir, 'applications', 'miniword.desktop'),
            os.path.join(data_dir, 'mime', 'packages', 'miniword.xml'),
            os.path.join(data_dir, 'icons', 'hicolor', 'scalable', 'apps',
                         'miniword.svg'))


def _run(command):
    """Run a command; a missing tool only gives a note."""
    try:
        subprocess.run(command, check=False)
    except FileNotFoundError:
        print("Note: '%s' not found, skipped." % command[0])


def _update(data_dir, run):
    run(['update-mime-database', os.path.join(data_dir, 'mime')])
    run(['update-desktop-database', os.path.join(data_dir, 'applications')])


def command(argv0=None):
    """The launcher MiniWord was started with (/usr/bin/miniword, pip's
    script), else "python -m miniword" (fails for the .deb: its package
    is not on the Python path)."""
    argv0 = os.path.abspath(argv0 or sys.argv[0])
    if os.path.basename(argv0) != '__main__.py' \
            and os.access(argv0, os.X_OK):
        return quote(argv0)
    return quote(sys.executable) + ' -m miniword'


def quote(path):
    if ' ' in path:
        return '"%s"' % path
    return path


def install(data_dir=None, run=_run, argv0=None):
    """Install the desktop entry, the .txl file type and the icon, and
    make MiniWord the default for .txl; for .md and .txt it is offered
    under "Open with"."""
    data_dir = data_dir or data_home()
    entry, mime, icon = _files(data_dir)
    for path in (entry, mime, icon):
        os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(entry, 'w', encoding='utf-8') as f:
        f.write(ENTRY.format(exec=command(argv0),
                             mime_types=MIME_TYPES))
    with open(mime, 'w', encoding='utf-8') as f:
        f.write(MIME_XML)
    shutil.copyfile(os.path.join(os.path.dirname(__file__), 'icons',
                                 'miniword.svg'), icon)
    _update(data_dir, run)
    run(['xdg-mime', 'default', 'miniword.desktop', MIME_TYPE])


def uninstall(data_dir=None, run=_run):
    """Remove what install wrote. Default applications set with xdg-mime
    stay listed but point to no entry anymore - the system then falls
    back to the next application."""
    data_dir = data_dir or data_home()
    for path in _files(data_dir):
        if os.path.exists(path):
            os.remove(path)
    _update(data_dir, run)
