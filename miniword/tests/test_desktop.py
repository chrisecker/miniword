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


def install():
    """(data folder, commands run) of an install into a temporary
    folder; the folder is removed on exit of the generator."""
    commands = []
    with tempfile.TemporaryDirectory() as tmp:
        desktop.install(data_dir=tmp, run=commands.append,
                        argv0=sys.executable)
        yield tmp, commands


def read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def test_DSK_1():
    "DSK-1: install writes desktop entry, file type and icon; sets .txl"
    for tmp, commands in install():
        entry = read(os.path.join(tmp, 'applications', 'miniword.desktop'))
        assert 'Exec=' + sys.executable + ' %f\n' in entry
        assert 'MimeType=%s\n' % desktop.MIME_TYPES in entry
        mime = read(os.path.join(tmp, 'mime', 'packages', 'miniword.xml'))
        assert 'type="application/x-miniword"' in mime
        assert 'pattern="*.txl"' in mime
        assert '<icon name="miniword"/>' in mime
        assert '<generic-icon name="miniword"/>' in mime
        assert os.path.exists(os.path.join(
            tmp, 'icons', 'hicolor', 'scalable', 'apps', 'miniword.svg'))
        assert ['update-mime-database', os.path.join(tmp, 'mime')] \
            in commands
        assert ['update-desktop-database',
                os.path.join(tmp, 'applications')] in commands
        assert ['xdg-mime', 'default', 'miniword.desktop',
                'application/x-miniword'] in commands


def test_DSK_2():
    "DSK-2: .md and .txt are offered (Open with), not made the default"
    for tmp, commands in install():
        entry = read(os.path.join(tmp, 'applications', 'miniword.desktop'))
        assert 'text/markdown;' in entry and 'text/plain;' in entry
        defaults = [c for c in commands if c[:2] == ['xdg-mime', 'default']]
        assert defaults == [['xdg-mime', 'default', 'miniword.desktop',
                             'application/x-miniword']]


def test_DSK_3():
    "DSK-3: uninstall removes what install wrote"
    for tmp, commands in install():
        desktop.uninstall(data_dir=tmp, run=commands.append)
        for path in (('applications', 'miniword.desktop'),
                     ('mime', 'packages', 'miniword.xml'),
                     ('icons', 'hicolor', 'scalable', 'apps',
                      'miniword.svg')):
            assert not os.path.exists(os.path.join(tmp, *path)), path


def test_DSK_4():
    "DSK-4: the launcher if started by one, else python -m miniword"
    assert desktop.command(sys.executable) == sys.executable
    main = os.path.join(os.path.dirname(desktop.__file__), '__main__.py')
    assert desktop.command(main) == sys.executable + ' -m miniword'
    assert desktop.command('-c') == sys.executable + ' -m miniword'
