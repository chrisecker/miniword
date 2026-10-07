# -*- coding: utf-8 -*-

"""A bar above the page with a message, a button and a close button,
like Word's message bar (e.g. 'Load external images')."""

import wx


class MessageBar(wx.Panel):
    def __init__(self, parent, on_change):
        """on_change(): called when the bar is shown or hidden (the window
        lays itself out anew)."""
        wx.Panel.__init__(self, parent)
        self.SetBackgroundColour(
            wx.SystemSettings.GetColour(wx.SYS_COLOUR_INFOBK))
        self.on_change = on_change
        self.action = None
        self.text = wx.StaticText(self)
        self.text.SetForegroundColour(
            wx.SystemSettings.GetColour(wx.SYS_COLOUR_INFOTEXT))
        self.button = wx.Button(self)
        self.button.Bind(wx.EVT_BUTTON, lambda e: self.action())
        close = wx.Button(self, label='×', style=wx.BU_EXACTFIT)
        close.SetToolTip("Close")
        close.Bind(wx.EVT_BUTTON, lambda e: self.close())
        border = self.FromDIP(6)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self.text, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALL, border)
        sizer.Add(self.button, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, border)
        sizer.Add(close, 0, wx.ALIGN_CENTER_VERTICAL | wx.ALL, border)
        self.SetSizer(sizer)
        self.Hide()

    def show(self, message, label=None, action=None):
        """Show message; with label a button that calls action()."""
        self.text.SetLabel(message)
        self.button.SetLabel(label or '')
        self.button.Show(bool(label))
        self.action = action
        self.Show()
        self.Layout()
        self.on_change()

    def close(self):
        self.Hide()
        self.on_change()
