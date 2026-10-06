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
            builder=SimpleNamespace(stylesheet=sheet))
        inspector = StyleInspector(frame, editor, sheet)
        inspector.update()
        yield inspector, model, editor
    finally:
        frame.Destroy()


@contextmanager
def settings_inspector():
    """(inspector, document): a SettingsInspector for a new Document."""
    from ..core.document import Document
    from ..ui.settingsinspector import SettingsInspector
    app()
    frame = wx.Frame(None, size=(330, 900))
    try:
        document = Document()
        yield SettingsInspector(frame, document), document
    finally:
        frame.Destroy()


def click(control, value=None):
    """Set a check box or toggle button (to value) and send its event."""
    if value is not None:
        control.SetValue(value)
    kind = wx.wxEVT_TOGGLEBUTTON if isinstance(control, wx.ToggleButton) \
        else wx.wxEVT_CHECKBOX
    _send(control, kind, int(control.GetValue()))


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
