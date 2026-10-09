# -*- coding: utf-8 -*-

"""Helpers for tests of wx panels: build a panel in a frame, and click,
choose or type like a user."""

from contextlib import contextmanager
from types import SimpleNamespace

import wx

_app = None


def app():
    """The wx.App, created if there is none yet (and kept alive)."""
    global _app
    if wx.App.Get() is None:
        _app = wx.App(False)
    return wx.App.Get()


@contextmanager
def style_inspector(text="Eins\nZwei", size=wx.DefaultSize):
    """(inspector, model, editor): a StyleInspector for text, in a
    frame of size."""
    from ..core.stylesheet import StyleSheet, testsheet
    from ..texteditor.editor import Editor
    from ..textmodel.textmodel import TextModel
    from ..ui.styleinspector import StyleInspector
    app()
    frame = wx.Frame(None, size=size)
    try:
        # a copy: the inspector observes it, also after being destroyed
        sheet = StyleSheet()
        for key, style in testsheet.items():
            sheet.set(key, style)
        model = TextModel(text)
        editor = Editor(model)
        # mk_style takes the stylesheet from the canvas' builder
        editor.canvas = SimpleNamespace(
            builder=SimpleNamespace(stylesheet=sheet),
            reset_blink=lambda: None, adjust_viewport=lambda: None,
            refresh=lambda: None)
        inspector = StyleInspector(frame, editor, sheet)
        inspector.update()
        yield inspector, model, editor
    finally:
        frame.Destroy()


@contextmanager
def settings_inspector():
    """(inspector, document, editor): a SettingsInspector for a new
    Document."""
    from ..core.document import Document
    from ..texteditor.editor import Editor
    from ..ui.settingsinspector import SettingsInspector
    app()
    frame = wx.Frame(None, size=(330, 900))
    try:
        document = Document()
        editor = Editor(document.textmodel)
        yield SettingsInspector(frame, document, editor), document, editor
    finally:
        frame.Destroy()


def close(frame):
    """Destroy a main frame in a test (no event loop, no on_close):
    release it first - else the layout's pending timer would fire later,
    in another test, on the destroyed canvas, and the file history would
    keep its menu - then free the windows at once (Destroy alone only
    schedules it; Windows has a limit of window handles)."""
    frame.release()
    frame.DestroyChildren()
    frame.Destroy()


def mouse(canvas, x, y):
    """A mouse event at (x, y) (content coordinates) for the canvas's
    handlers, e.g. canvas.on_leftdown(mouse(canvas, x, y))."""
    ox, oy = canvas.content_offset()
    scale = canvas.scale
    event = wx.MouseEvent(wx.wxEVT_LEFT_DOWN)
    event.SetPosition(wx.Point(canvas.CalcScrolledPosition(
        round(x * scale) + ox, round(y * scale) + oy)))
    return event


def double_click(canvas, x, y):
    """A double click at (x, y): its first click, then the double."""
    event = mouse(canvas, x, y)
    canvas.on_leftdown(event)
    canvas.on_leftdclick(event)


def click(control, value=None):
    """Set a check box or toggle button (to value) and send its event."""
    if value is not None:
        control.SetValue(value)
    from ..ui.flatbutton import FlatToggle
    kind = wx.wxEVT_TOGGLEBUTTON \
        if isinstance(control, (wx.ToggleButton, FlatToggle)) \
        else wx.wxEVT_CHECKBOX
    _send(control, kind, int(control.GetValue()))


def click_button(button):
    """Press a button (also a flat button) and send its event."""
    _send(button, wx.wxEVT_BUTTON)


def choose(choice, label):
    """Select label in a wx.Choice and send its event."""
    choice.SetSelection(choice.FindString(label))
    _send(choice, wx.wxEVT_CHOICE)


def enter(textctrl, text):
    """Type text into a text control and press Enter."""
    textctrl.SetValue(text)
    _send(textctrl, wx.wxEVT_TEXT_ENTER)


def _send(control, kind, value=0):
    event = wx.CommandEvent(kind, control.GetId())
    event.SetEventObject(control)
    event.SetInt(value)
    control.ProcessWindowEvent(event)
