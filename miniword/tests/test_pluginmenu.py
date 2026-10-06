# -*- coding: utf-8 -*-

"""
Tests for plugin menus (ui/mainwindow.plugin_menu): entries, separators,
submenus and greying out. IDs PM-n.

Run with: python runtests.py miniword/tests/test_pluginmenu.py
"""

import wx

from .guitest import app


def menu_for(items):
    """(frame, menu) for items."""
    from ..ui.mainwindow import plugin_menu
    app()
    frame = wx.Frame(None)
    return frame, plugin_menu(frame, items)


def test_PM_1():
    "PM-1: entries, a separator and a submenu"
    calls = []
    frame, menu = menu_for([
        ("A", lambda f: calls.append('a')),
        None,
        ("Sub", [("B", lambda f: calls.append('b'))])])
    try:
        items = menu.GetMenuItems()
        assert [i.GetItemLabelText() for i in items] == ["A", "", "Sub"]
        assert items[1].IsSeparator()
        sub = items[2].GetSubMenu()
        b = sub.GetMenuItems()[0]
        frame.ProcessEvent(wx.CommandEvent(wx.wxEVT_MENU, b.GetId()))
        assert calls == ['b']
    finally:
        frame.Destroy()


def test_PM_2():
    "PM-2: an entry with enabled(frame) is greyed out on update"
    state = {'on': False}
    frame, menu = menu_for([("A", lambda f: None,
                             lambda f: state['on'])])
    try:
        item = menu.GetMenuItems()[0]
        event = wx.UpdateUIEvent(item.GetId())
        frame.ProcessEvent(event)
        assert event.GetSetEnabled() and not event.GetEnabled()
        state['on'] = True
        event = wx.UpdateUIEvent(item.GetId())
        frame.ProcessEvent(event)
        assert event.GetEnabled()
    finally:
        frame.Destroy()
