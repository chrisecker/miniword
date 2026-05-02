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

