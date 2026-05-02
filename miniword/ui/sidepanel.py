import wx
from pathlib import Path

PANEL_W    = 300
STRIP_W    = 52
ICON_H     = 48

BG_CANVAS  = wx.Colour(228, 228, 224)
BG_STRIP   = wx.Colour(242, 242, 238)
BG_PANEL   = wx.Colour(250, 250, 248)
COL_BORDER = wx.Colour(205, 205, 200)
COL_ACTIVE = wx.Colour(222, 222, 218)
COL_HOVER  = wx.Colour(234, 234, 230)

_ICONS_DIR = Path(__file__).resolve().parent.parent / "icons"


def _svg_bundle(name):
    return wx.BitmapBundle.FromSVGFile(str(_ICONS_DIR / name), (24, 24))


class IconButton(wx.Panel):

    def __init__(self, parent, key, label, callback):
        super().__init__(parent)
        dip = self.FromDIP
        size = dip(wx.Size(STRIP_W, ICON_H))
        self.SetMinSize(size)
        self.SetMaxSize(size)
        self.SetSize(size)
        self.callback = callback
        self.active   = False
        self.hover    = False
        self.SetToolTip(label)
        self._bmp = _svg_bundle(f'{key}.svg')
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
        dc.SetPen(wx.Pen(COL_BORDER, 1))
        dc.DrawLine(0, 0, 0, h)
        bmp = self._bmp.GetBitmap(self.FromDIP(wx.Size(24, 24)))
        bw, bh = bmp.GetSize()
        dc.DrawBitmap(bmp, (w - bw) // 2, (h - bh) // 2)


class RightStrip(wx.Panel):
    """Vertical icon strip on the right edge. entries: list of (key, label)."""

    def __init__(self, parent, entries, on_toggle):
        super().__init__(parent)
        dip = self.FromDIP
        self.SetMinSize((dip(STRIP_W), -1))
        self.SetMaxSize((dip(STRIP_W), -1))
        self.SetBackgroundColour(BG_STRIP)
        self.on_toggle   = on_toggle
        self.active_btn  = None
        self._key_to_btn = {}

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.AddSpacer(dip(4))
        for key, lbl in entries:
            btn = IconButton(self, key, lbl, self._click)
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
