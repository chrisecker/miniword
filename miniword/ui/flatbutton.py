import wx
from .colours import colours
from .icons import themed_icon


class FlatButton(wx.Control):
    pressed = False  # drawn pressed (see FlatToggle)
    event_type = wx.wxEVT_BUTTON

    def __init__(self, parent, label, size=None, bordered=False, icon=None):
        """icon: an SVG in icons/, drawn in the text colour."""
        if size is None:
            size = (-1, parent.FromDIP(24))
        super().__init__(parent, size=size, style=wx.BORDER_NONE)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.label    = label
        self.bordered = bordered
        self.icon     = icon
        self.state    = 'normal'
        self.init_colors()
        self.Bind(wx.EVT_PAINT,        self.on_paint)
        self.Bind(wx.EVT_ENTER_WINDOW, lambda e: self.set_state('hover'))
        self.Bind(wx.EVT_LEAVE_WINDOW, lambda e: self.set_state('normal'))
        self.Bind(wx.EVT_LEFT_DOWN,    lambda e: self.set_state('press'))
        self.Bind(wx.EVT_LEFT_UP,      self.on_release)

    def init_colors(self):
        colours.set(self, 'colour_normal_bg',       'ButtonNormal')
        colours.set(self, 'colour_normal_fg',       'WINDOWTEXT')
        colours.set(self, 'colour_hover_bg',        'ButtonHover')
        colours.set(self, 'colour_hover_fg',        'WINDOWTEXT')
        colours.set(self, 'colour_press_bg',        'ButtonPress')
        colours.set(self, 'colour_press_fg',        'WINDOWTEXT')
        colours.set(self, 'colour_disabled_bg',     'BTNFACE')
        colours.set(self, 'colour_disabled_fg',     'GRAYTEXT')
        colours.set(self, 'colour_border',          'ButtonBorder')
        colours.set(self, 'colour_border_disabled', 'ButtonBorderDisabled')

    def Enable(self, enable=True):
        result = super().Enable(enable)
        self.Refresh()
        return result

    def set_state(self, state):
        if not self.IsEnabled():
            return
        self.state = state
        self.Refresh()

    def on_release(self, event):
        self.set_state('hover')
        evt = wx.CommandEvent(self.event_type, self.GetId())
        evt.SetEventObject(self)
        evt.SetInt(self.pressed)
        self.GetEventHandler().ProcessEvent(evt)
        self.set_state('normal')

    def DoGetBestSize(self):
        dc = wx.ClientDC(self)
        dc.SetFont(self.GetFont())
        _, th = dc.GetTextExtent("Ag")
        w, h = self.GetSize()
        return wx.Size(w if w > 0 else self.FromDIP(24), th + self.FromDIP(6))

    def on_paint(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        if not self.IsEnabled():
            bg     = self.colour_disabled_bg
            fg     = self.colour_disabled_fg
            border = self.colour_border_disabled
        else:
            state  = 'press' if self.pressed else self.state
            bg     = getattr(self, f'colour_{state}_bg')
            fg     = getattr(self, f'colour_{state}_fg')
            border = self.colour_border
        dc.SetBackground(wx.Brush(bg))
        dc.Clear()
        w, h = self.GetSize()
        if self.bordered:
            dc.SetPen(wx.Pen(border))
            dc.SetBrush(wx.TRANSPARENT_BRUSH)
            dc.DrawRectangle(0, 0, w, h)
        if self.icon:
            bitmap = themed_icon(self.icon, fg).GetBitmapFor(self)
            bw, bh = bitmap.GetLogicalSize()
            dc.DrawBitmap(bitmap, int(w - bw) // 2, int(h - bh) // 2, True)
            return
        dc.SetFont(self.GetFont())
        dc.SetTextForeground(fg)
        tw, th = dc.GetTextExtent(self.label)
        dc.DrawText(self.label, (w - tw) // 2, (h - th) // 2)


class FlatToggle(FlatButton):
    """A flat button that stays pressed; sends EVT_TOGGLEBUTTON."""
    event_type = wx.wxEVT_TOGGLEBUTTON

    def GetValue(self):
        return self.pressed

    def SetValue(self, value):
        self.pressed = bool(value)
        self.Refresh()

    def on_release(self, event):
        self.SetValue(not self.pressed)
        super().on_release(event)


class ResetButton(FlatButton):
    """Small ✕ button — visible when a value has been modified, blank otherwise."""
    callback = None

    def __init__(self, parent, properties=()):
        sz = parent.FromDIP(wx.Size(24, 24))
        super().__init__(parent, label="", size=sz)
        colours.set(self, 'colour_normal_bg', 'BTNFACE')
        colours.set(self, 'colour_hover_bg',  'BTNFACE')
        colours.set(self, 'colour_press_bg',  'BTNFACE')
        colours.set(self, 'colour_normal_fg', 'WarningRed')
        colours.set(self, 'colour_hover_fg',  'Highlight')
        colours.set(self, 'colour_press_fg',  'Highlight')
        self.properties = properties
        self.SetToolTip("Remove local change")
        self.Bind(wx.EVT_BUTTON, self._on_button)

    def _on_button(self, event):
        if self.callback and self.label:
            self.callback(*self.properties)

    def set_x(self, visible: bool):
        if visible == bool(self.label):
            return
        self.label = "✕" if visible else ""
        self.Refresh()
