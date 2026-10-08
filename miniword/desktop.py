# -*- coding: utf-8 -*-

"""
Desktop integration on Linux (freedesktop): a menu entry, the file type
of .txl documents and MiniWord as their default application - optionally
also for Markdown. pip can't do this itself (it runs no code on install
and installs relative to its environment), hence

    miniword --install-desktop [--markdown]
    miniword --uninstall-desktop

Everything goes into the user's data folder ($XDG_DATA_HOME, usually
~/.local/share); no root rights needed.
"""

import os
import shutil
import subprocess
import sys

MIME_TYPE = 'application/x-miniword'

MIME_XML = '''\
<?xml version="1.0" encoding="UTF-8"?>
<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">
  <mime-type type="application/x-miniword">
    <comment>MiniWord document</comment>
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


def install(markdown=False, data_dir=None, run=_run):
    """Install the desktop entry, the .txl file type and the icon, and
    make MiniWord the default for .txl (and with markdown for .md)."""
    data_dir = data_dir or data_home()
    entry, mime, icon = _files(data_dir)
    mime_types = [MIME_TYPE] + (['text/markdown'] if markdown else [])
    program = sys.executable
    if ' ' in program:
        program = '"%s"' % program
    for path in (entry, mime, icon):
        os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(entry, 'w', encoding='utf-8') as f:
        f.write(ENTRY.format(exec=program + ' -m miniword',
                             mime_types=''.join(t + ';'
                                                for t in mime_types)))
    with open(mime, 'w', encoding='utf-8') as f:
        f.write(MIME_XML)
    shutil.copyfile(os.path.join(os.path.dirname(__file__), 'icons',
                                 'miniword.svg'), icon)
    _update(data_dir, run)
    for mime_type in mime_types:
        run(['xdg-mime', 'default', 'miniword.desktop', mime_type])


def uninstall(data_dir=None, run=_run):
    """Remove what install wrote. Default applications set with xdg-mime
    stay listed but point to no entry anymore - the system then falls
    back to the next application."""
    data_dir = data_dir or data_home()
    for path in _files(data_dir):
        if os.path.exists(path):
            os.remove(path)
    _update(data_dir, run)
