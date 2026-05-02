import wx

class FlatButton(wx.Control):
    def __init__(self, parent, label, size=None):
        if size is None:
            size = (-1, parent.FromDIP(24))
        super().__init__(parent, size=size, style=wx.BORDER_NONE)
        
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        
        self.label = label
        self.state = 'normal'
        self.init_colors()

        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_ENTER_WINDOW, lambda e: self.set_state('hover'))
        self.Bind(wx.EVT_LEAVE_WINDOW, lambda e: self.set_state('normal'))
        self.Bind(wx.EVT_LEFT_DOWN,    lambda e: self.set_state('press'))
        self.Bind(wx.EVT_LEFT_UP,      self.on_release)        

    def init_colors(self):
        bg = wx.SystemSettings.GetColour(wx.SYS_COLOUR_BTNFACE)
        txt = wx.SystemSettings.GetColour(wx.SYS_COLOUR_WINDOWTEXT)
        self.colors = {'normal': (bg, txt), 'hover': (bg, txt), 'press': (bg, txt)}

    def set_state(self, state):
        self.state = state
        self.Refresh()

    def on_release(self, event):
        self.set_state('hover')
        evt = wx.CommandEvent(wx.wxEVT_BUTTON, self.GetId())
        self.GetEventHandler().ProcessEvent(evt)
        
    def DoGetBestSize(self):
        dc = wx.ClientDC(self)
        dc.SetFont(self.GetFont())
        _, th = dc.GetTextExtent("Ag")
        w, h = self.GetSize()
        return wx.Size(w if w > 0 else self.FromDIP(24), th + self.FromDIP(6))

    def on_paint(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        bg, fg = self.colors[self.state]
        dc.SetBackground(wx.Brush(bg))
        dc.Clear()
        dc.SetFont(self.GetFont())
        dc.SetTextForeground(fg)
        w, h = self.GetSize()
        tw, th = dc.GetTextExtent(self.label)
        dc.DrawText(self.label, (w - tw) // 2, (h - th) // 2)


class ResetButton(FlatButton):
    """Small ✕ button — visible when a value has been modified, blank otherwise."""
    callback = None

    def __init__(self, parent, properties=()):
        sz = parent.FromDIP(wx.Size(24, 24))
        super().__init__(parent, label="", size=sz)
        _bg = wx.Colour(245, 245, 245)
        self.properties = properties
        self.colors = {
            'normal': (_bg, wx.Colour(200, 0, 0)),
            'hover':  (_bg, wx.Colour(233, 84, 32)),
            'press':  (_bg, wx.Colour(233, 84, 32)),
        }
        self.SetToolTip("Remove local change")
        self.Bind(wx.EVT_BUTTON, self._on_button)

    def _on_button(self, event):
        if self.callback and self.label:
            self.callback(*self.properties)

    def set_x(self, visible: bool):
        if visible == bool(self.label):
            return
        self.label = "\u2715" if visible else ""
        self.Refresh()

