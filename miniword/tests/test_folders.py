# -*- coding: utf-8 -*-

"""
Tests for the folder the file dialogs start in: the folder of the last
document opened or saved, while the app runs (IDs DIR-n); and for the
file history when a window's menu goes away (IDs WIN-n).

Run with: python runtests.py miniword/tests/test_folders.py
"""

import os
import tempfile

from .guitest import app, close


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
            close(frame)
            close(other)


def test_WIN_1():
    "WIN-1: a rebuilt menu (DPI change) leaves the file history"
    from ..core.document import Document
    from ..ui import mainwindow as mw
    app()
    frame = mw.MainFrame(Document())
    try:
        old = frame._recent_menu
        frame._build_menu()
        menus = mw.get_file_history().GetMenus()
        assert old not in menus and frame._recent_menu in menus
    finally:
        close(frame)


def test_WIN_2():
    "WIN-2: release (on closing) stops the layout and leaves the history"
    from ..core.document import Document
    from ..ui import mainwindow as mw
    app()
    frame = mw.MainFrame(Document())
    try:
        frame.canvas.builder.schedule()
        frame.release()
        assert frame._recent_menu not in mw.get_file_history().GetMenus()
        assert frame.canvas.builder._scheduled is None
    finally:
        close(frame)
