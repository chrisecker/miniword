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


def test_KEY_4():
    "KEY-4: a Format menu with Bold, Italic, Underline and their shortcuts"
    from ..core.document import Document
    from ..ui.mainwindow import MainFrame
    app()
    frame = MainFrame(Document())
    try:
        bar = frame.GetMenuBar()
        menu = bar.GetMenu(bar.FindMenu('Format'))
        labels = [item.GetItemLabel() for item in menu.GetMenuItems()]
        assert labels == ['&Bold\tCtrl+B', '&Italic\tCtrl+I',
                          '&Underline\tCtrl+U', '',
                          'Increase &Indent\tAlt+Right',
                          '&Decrease Indent\tAlt+Left',
                          'Next &List Type\tCtrl+T',
                          'Next &Paragraph Style\tAlt+T']
        model = frame.document.textmodel
        model.insert_text(0, 'Wal')
        frame.editor.selection = (0, 3)
        frame.canvas.builder.assure_finished()
        bold = menu.GetMenuItems()[0]
        frame.ProcessEvent(wx.CommandEvent(wx.wxEVT_MENU, bold.GetId()))
        assert model.get_style(1).get('bold') is True
    finally:
        frame.Destroy()


def menu_item(frame, menu_name, label):
    bar = frame.GetMenuBar()
    menu = bar.GetMenu(bar.FindMenu(menu_name))
    return next(i for i in menu.GetMenuItems()
                if i.GetItemLabel().split('\t')[0] == label)


def test_KEY_5():
    "KEY-5: indent, list type and moving paragraphs from the menus"
    from ..core.document import Document
    from ..ui.mainwindow import MainFrame
    app()
    frame = MainFrame(Document())
    try:
        model = frame.document.textmodel
        model.insert_text(0, 'eins\nzwei\n')

        def choose(menu, label):
            frame.canvas.builder.assure_finished()
            item = menu_item(frame, menu, label)
            frame.ProcessEvent(wx.CommandEvent(wx.wxEVT_MENU, item.GetId()))
        frame.editor.index = 0
        choose('Format', 'Increase &Indent')
        assert model.get_indent(0) == 1
        choose('Format', 'Next &List Type')
        assert model.get_parstyle(0).get('paragraph_type') == 'list'
        choose('Edit', 'Move Paragraph &Down')
        assert model.get_text() == 'zwei\neins\n'
        assert menu_item(frame, 'Edit', 'Move Paragraph &Up').GetItemLabel() \
            == 'Move Paragraph &Up\tAlt+Up'
    finally:
        frame.Destroy()


def test_KEY_6():
    "KEY-6: without a selection, inside a word: the whole word"
    with canvas_with('Ein Wal hier') as (canvas, model, editor):
        editor.index = 5  # W|al
        press(canvas, 'b')
        assert [bool(model.get_style(i).get('bold')) for i in range(12)] \
            == [False] * 4 + [True] * 3 + [False] * 5
        assert editor.index == 5 and not editor.has_selection()
        editor.undo()
        assert not model.get_style(5).get('bold')


def test_KEY_7():
    "KEY-7: at a word's start or end, or between words: the next input"
    for index in (4, 7, 3):  # |Wal, Wal|, Ein| (before a space)
        with canvas_with('Ein Wal hier') as (canvas, model, editor):
            editor.index = index
            press(canvas, 'i')
            assert not any(model.get_style(i).get('italic')
                           for i in range(12)), index
            assert editor.current_style.get('italic') is True, index


def test_KEY_8():
    "KEY-8: the style inspector also formats the word at the cursor"
    from .guitest import style_inspector
    with style_inspector('Ein Wal hier') as (inspector, model, editor):
        editor.index = 5
        inspector.set_char_properties(color='#ff0000')
        assert model.get_style(5).get('color') == '#ff0000'
        assert model.get_style(4).get('color') == '#ff0000'
        assert model.get_style(2).get('color') != '#ff0000'
        inspector.clear_char_properties('color')
        assert model.get_style(5).get('color') != '#ff0000'
