# -*- coding: utf-8 -*-

"""
Tests for character format shortcuts: Ctrl+B bold, Ctrl+I italic,
Ctrl+U underline.
IDs KEY-n.

Run with: python runtests.py miniword/tests/test_shortcuts.py
"""

from contextlib import contextmanager

import wx

from .guitest import app


@contextmanager
def canvas_with(text):
    """(canvas, model, editor) for text."""
    from ..core.document import Document
    from ..layout.cairodevice import CairoDevice
    from ..layout.pagebuilder import PageBuilder
    from ..layout.rowfactory import Factory
    from ..texteditor.editor import Editor
    from ..texteditor.textcanvas import TextCanvas
    app()
    frame = wx.Frame(None)
    try:
        document = Document()
        model = document.textmodel
        model.insert_text(0, text)
        builder = PageBuilder(
            model, Factory(document.basestyles, device=CairoDevice()))
        builder.settings = document.settings
        builder.rebuild()
        editor = Editor(model)
        canvas = TextCanvas(frame, model, builder, editor)
        editor.canvas = canvas
        yield canvas, model, editor
    finally:
        frame.Destroy()


def press(canvas, key):
    """Ctrl+key (a letter) as the canvas gets it."""
    event = wx.KeyEvent(wx.wxEVT_CHAR)
    event.SetKeyCode(ord(key.upper()) - ord('A') + 1)  # Ctrl+A = 1 ...
    event.SetControlDown(True)
    canvas.builder.assure_finished()  # the app paints between key presses
    canvas.on_char(event)


def test_KEY_1():
    "KEY-1: Ctrl+I switches italic of the selection on and off"
    with canvas_with('Ein Wal') as (canvas, model, editor):
        editor.selection = (4, 7)
        press(canvas, 'i')
        assert model.get_style(4).get('italic') is True
        assert not model.get_style(0).get('italic')
        press(canvas, 'i')
        assert not model.get_style(4).get('italic')
        editor.undo()
        assert model.get_style(4).get('italic') is True


def test_KEY_2():
    "KEY-2: Ctrl+U underlines; without a selection the next input"
    with canvas_with('Wal') as (canvas, model, editor):
        editor.selection = (0, 3)
        press(canvas, 'u')
        assert model.get_style(1).get('underline') is True
        editor.selection = (3, 3)
        editor.index = 3
        press(canvas, 'u')  # off for what comes next
        press(canvas, 'i')
        editor.insert_text('e')
        style = model.get_style(3)
        assert style.get('italic') is True and not style.get('underline')


def test_KEY_3():
    "KEY-3: Ctrl+B switches bold"
    with canvas_with('Wal') as (canvas, model, editor):
        editor.selection = (0, 3)
        press(canvas, 'b')
        assert model.get_style(1).get('bold') is True
        press(canvas, 'b')
        assert not model.get_style(1).get('bold')
