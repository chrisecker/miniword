import wx

PANEL_W    = 300
STRIP_W    = 52
ICON_H     = 56

BG_CANVAS  = wx.Colour(228, 228, 224)
BG_STRIP   = wx.Colour(242, 242, 238)
BG_PANEL   = wx.Colour(250, 250, 248)
COL_BORDER = wx.Colour(205, 205, 200)
COL_TEXT   = wx.Colour(38,  38,  36)
COL_MUTED  = wx.Colour(110, 110, 106)
COL_ACTIVE = wx.Colour(222, 222, 218)
COL_HOVER  = wx.Colour(234, 234, 230)




class IconButton(wx.Panel):
    """
    Two fixed zones:
      upper 38px → symbol  (font 16, vertically centred)
      lower 18px → label   (font 7,  vertically centred)
    """
    SIZE = (STRIP_W, ICON_H)

    def __init__(self, parent, symbol, label, callback):
        super().__init__(parent, size=self.SIZE)
        self.symbol   = symbol
        self.label    = label[:6]
        self.callback = callback
        self.active   = False
        self.hover    = False
        self.SetMinSize(self.SIZE)
        self.SetMaxSize(self.SIZE)
        self.SetToolTip(label)
        self.Bind(wx.EVT_PAINT,        self._paint)
        self.Bind(wx.EVT_LEFT_UP,      lambda e: self.callback(self))
        self.Bind(wx.EVT_ENTER_WINDOW, lambda e: self._set_hover(True))
        self.Bind(wx.EVT_LEAVE_WINDOW, lambda e: self._set_hover(False))

    def _set_hover(self, v):
        self.hover = v
        self.Refresh()

    def set_active(self, v):
        self.active = v
        self.Refresh()

    def _paint(self, _):
        dc = wx.PaintDC(self)
        w, h = self.GetClientSize()
        bg = COL_ACTIVE if self.active else (COL_HOVER if self.hover else BG_STRIP)
        dc.SetBackground(wx.Brush(bg))
        dc.Clear()
        SYM_H = 38
        LBL_H = h - SYM_H
        f_sym = wx.Font(16, wx.FONTFAMILY_DEFAULT,
                        wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        dc.SetFont(f_sym)
        dc.SetTextForeground(COL_TEXT if self.active else wx.Colour(80, 80, 76))
        sw, sh = dc.GetTextExtent(self.symbol)
        dc.DrawText(self.symbol, (w - sw) // 2, (SYM_H - sh) // 2)
        f_lbl = wx.Font(7, wx.FONTFAMILY_DEFAULT,
                        wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
        dc.SetFont(f_lbl)
        dc.SetTextForeground(COL_MUTED)
        lw, lh = dc.GetTextExtent(self.label)
        dc.DrawText(self.label, (w - lw) // 2, SYM_H + (LBL_H - lh) // 2)


class RightStrip(wx.Panel):
    """
    Vertical icon strip on the right edge.
    entries: list of (key, symbol, label)
    on_toggle: called with key or None when toggled off
    """

    def __init__(self, parent, entries, on_toggle):
        super().__init__(parent, size=(STRIP_W, -1))
        self.SetBackgroundColour(BG_STRIP)
        self.SetMinSize((STRIP_W, -1))
        self.SetMaxSize((STRIP_W, -1))
        self.on_toggle   = on_toggle
        self.active_btn  = None
        self._key_to_btn = {}

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.AddSpacer(4)
        for key, sym, lbl in entries:
            btn = IconButton(self, sym, lbl, self._click)
            btn._key = key
            self._key_to_btn[key] = btn
            sizer.Add(btn, 0)
        sizer.AddStretchSpacer()
        self.SetSizer(sizer)
        self.Bind(wx.EVT_PAINT, self._paint)

    def _paint(self, _):
        dc = wx.PaintDC(self)
        h  = self.GetClientSize()[1]
        dc.SetPen(wx.Pen(COL_BORDER, 1))
        dc.DrawLine(0, 0, 0, h)

    def _click(self, btn):
        if self.active_btn is btn:
            btn.set_active(False)
            self.active_btn = None
            self.on_toggle(None)
        else:
            if self.active_btn:
                self.active_btn.set_active(False)
            btn.set_active(True)
            self.active_btn = btn
            self.on_toggle(btn._key)

    def activate(self, key):
        btn = self._key_to_btn.get(key)
        if btn and btn is not self.active_btn:
            if self.active_btn:
                self.active_btn.set_active(False)
            btn.set_active(True)
            self.active_btn = btn

    def deactivate(self):
        if self.active_btn:
            self.active_btn.set_active(False)
            self.active_btn = None


class SearchBar(wx.Panel):
    """Floating search bar shown at the bottom of the canvas (Ctrl+F)."""

    def __init__(self, parent, on_close):
        super().__init__(parent, style=wx.BORDER_NONE)
        self.on_close = on_close
        self.SetBackgroundColour(wx.Colour(255, 255, 253))
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.field = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER, size=(220, -1))
        close_btn = wx.Button(self, label="✕", size=(24, 24), style=wx.BORDER_NONE)
        close_btn.SetBackgroundColour(wx.Colour(255, 255, 253))
        close_btn.Bind(wx.EVT_BUTTON, lambda e: self.on_close())
        self.field.Bind(wx.EVT_KEY_DOWN, self._on_key)
        sizer.Add(wx.StaticText(self, label="Search:"), 0,
                  wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 8)
        sizer.Add(self.field, 1, wx.ALIGN_CENTER_VERTICAL | wx.ALL, 4)
        sizer.Add(close_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 4)
        self.SetSizer(sizer)
        self.Bind(wx.EVT_PAINT, self._paint)

    def _paint(self, _):
        dc = wx.PaintDC(self)
        w  = self.GetClientSize()[0]
        dc.SetPen(wx.Pen(COL_BORDER, 1))
        dc.DrawLine(0, 0, w, 0)

    def _on_key(self, event):
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.on_close()
        else:
            event.Skip()

    def focus(self):
        self.field.SetFocus()
        self.field.SelectAll()
