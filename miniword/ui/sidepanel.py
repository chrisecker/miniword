import wx
from ..core.respath import package_dir
from ..textmodel.viewbase import ViewBase
from .colours import colours

PANEL_W    = 300
STRIP_W    = 52
ICON_H     = 48

_ICONS_DIR = package_dir() / "icons"



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
        icon_px = self.FromDIP(24)
        self._bmp = wx.BitmapBundle.FromSVGFile(
            str(_ICONS_DIR / f'{key}.svg'), wx.Size(icon_px, icon_px))
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
        gc = wx.SystemSettings.GetColour
        btnface = gc(wx.SYS_COLOUR_BTNFACE)
        bg = btnface.ChangeLightness(92) if self.active else (
             btnface.ChangeLightness(97) if self.hover else btnface)
        dc = wx.PaintDC(self)
        w, h = self.GetClientSize()
        dc.SetBackground(wx.Brush(bg))
        dc.Clear()
        dc.SetPen(wx.Pen(gc(wx.SYS_COLOUR_BTNSHADOW), 1))
        dc.DrawLine(0, 0, 0, h)
        icon_px = self.FromDIP(24)
        bmp = self._bmp.GetBitmap(wx.Size(icon_px, icon_px))
        dc.DrawBitmap(bmp, (w - icon_px) // 2, (h - icon_px) // 2)


class RightStrip(wx.Panel):
    """Vertical icon strip on the right edge. entries: list of (key, label)."""

    def __init__(self, parent, entries, on_toggle):
        super().__init__(parent)
        dip = self.FromDIP
        self.SetMinSize((dip(STRIP_W), -1))
        self.SetMaxSize((dip(STRIP_W), -1))
        colours.set(self, 'BackgroundColour', 'BTNFACE')
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
        dc.SetPen(wx.Pen(wx.SystemSettings.GetColour(wx.SYS_COLOUR_BTNSHADOW), 1))
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


class SidePanel(wx.Panel, ViewBase):
    visible = False
    delay = 20 # Update is delayed by this time (milli seconds)
    
    def __init__(self, parent):
        wx.Panel.__init__(self, parent)
        ViewBase.__init__(self)
        self._timer = wx.Timer(self)
        self.Bind(wx.EVT_SHOW, self.on_show)
        self.Bind(wx.EVT_TIMER, lambda _: self.update())

    def on_show(self, event):
        if not self:
            return
        self.update_visible()
        event.Skip()
        
    def dpi_changed(self):
        # Called from parent widget
        self.DestroyChildren()
        self.create()
        self.Layout()
        self.update_visible()

    def update_visible(self):
        """Update the visibility flag."""
        # Called from parent widget or from on_show
        self.visible = self.IsShownOnScreen()
        if self.visible:
            self.update()

    def queue_update(self):
        # can be called when lazy updates are needed (e.g. for model changes)
        self._timer.StartOnce(self.delay)

    def model_changed(self, model):
        if self.visible:
            self.queue_update()

    ### Derived classes need to implement the following methods
    def create(self):
        pass

    def update(self):
        pass
    
