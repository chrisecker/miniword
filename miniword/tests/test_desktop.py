# -*- coding: utf-8 -*-

"""
Tests for the desktop integration on Linux (miniword --install-desktop).
They write into a temporary folder and only record the commands, which
would otherwise change the user's file associations. IDs DSK-n.

Run with: python runtests.py miniword/tests/test_desktop.py
"""

import os
import sys
import tempfile

from .. import desktop


def install(markdown=False):
    """(data folder, commands run) of an install into a temporary
    folder; the folder is removed on exit of the generator."""
    commands = []
    with tempfile.TemporaryDirectory() as tmp:
        desktop.install(markdown, data_dir=tmp, run=commands.append)
        yield tmp, commands


def read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def test_DSK_1():
    "DSK-1: install writes desktop entry, file type and icon; sets .txl"
    for tmp, commands in install():
        entry = read(os.path.join(tmp, 'applications', 'miniword.desktop'))
        assert sys.executable in entry and '-m miniword %f' in entry
        assert 'MimeType=application/x-miniword;\n' in entry
        mime = read(os.path.join(tmp, 'mime', 'packages', 'miniword.xml'))
        assert 'type="application/x-miniword"' in mime
        assert 'pattern="*.txl"' in mime
        assert os.path.exists(os.path.join(
            tmp, 'icons', 'hicolor', 'scalable', 'apps', 'miniword.svg'))
        assert ['update-mime-database', os.path.join(tmp, 'mime')] \
            in commands
        assert ['update-desktop-database',
                os.path.join(tmp, 'applications')] in commands
        assert ['xdg-mime', 'default', 'miniword.desktop',
                'application/x-miniword'] in commands
        assert not any('text/markdown' in c for c in commands)


def test_DSK_2():
    "DSK-2: with markdown, .md is associated too"
    for tmp, commands in install(markdown=True):
        entry = read(os.path.join(tmp, 'applications', 'miniword.desktop'))
        assert 'MimeType=application/x-miniword;text/markdown;\n' in entry
        assert ['xdg-mime', 'default', 'miniword.desktop',
                'text/markdown'] in commands


def test_DSK_3():
    "DSK-3: uninstall removes what install wrote"
    for tmp, commands in install():
        desktop.uninstall(data_dir=tmp, run=commands.append)
        for path in (('applications', 'miniword.desktop'),
                     ('mime', 'packages', 'miniword.xml'),
                     ('icons', 'hicolor', 'scalable', 'apps',
                      'miniword.svg')):
            assert not os.path.exists(os.path.join(tmp, *path)), path
