# -*- coding: utf-8 -*-

"""
Tests for the folder the file dialogs start in: the folder of the last
document opened or saved, while the app runs. IDs DIR-n.

Run with: python runtests.py miniword/tests/test_folders.py
"""

import os
import tempfile

from .guitest import app


def test_DIR_1():
    "DIR-1: the folder of a remembered file is the last folder"
    from ..ui import mainwindow as mw
    mw.remember_dir(os.path.join('some', 'folder', 'a.txl'))
    assert mw.last_dir() == os.path.abspath(os.path.join('some', 'folder'))


def test_DIR_2():
    "DIR-2: saving remembers the folder; a new document starts there"
    from ..core.document import Document
    from ..ui import mainwindow as mw
    app()
    with tempfile.TemporaryDirectory() as tmp:
        frame = mw.MainFrame(Document())
        other = mw.MainFrame(Document())  # not saved
        try:
            path = os.path.join(tmp, 'doc.txl')
            frame._current_path = path
            frame._do_save(path)
            assert mw.last_dir() == tmp
            assert other._dialog_dir() == tmp
        finally:
            for f in (frame, other):
                f.DestroyChildren()
                f.Destroy()
