import sys
import wx
import wx.lib.newevent


ValueChangeEvent, EVT_SPIN_VALUE = wx.lib.newevent.NewCommandEvent()


class SpinCtrl3(wx.Panel):
    def __init__(self, parent, initial=None, min=0.0, max=100.0, inc=0.1, digits=2):
        super().__init__(parent)

        self.min_val = min
        self.max_val = max
        self.inc = inc
        self.digits = digits
        self._value = initial

        sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.text = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.spin = wx.SpinButton(self, style=wx.SP_VERTICAL)
        self.spin.SetRange(-10000, 10000)
        self._last_spin = self.spin.GetValue()

        sizer.Add(self.text, 1, wx.EXPAND)
        sizer.Add(self.spin, 0, wx.EXPAND)
        self.SetSizer(sizer)

        self._update_ui()

        self.text.Bind(wx.EVT_TEXT_ENTER, self._on_text_enter)
        self.text.Bind(wx.EVT_KILL_FOCUS, self._on_text_enter)
        self.spin.Bind(wx.EVT_SPIN, self._on_spin)

    def _update_ui(self):
        if self._value is None:
            self.text.SetValue("")
        else:
            fmt = "{:." + str(self.digits) + "f}"
            self.text.SetValue(fmt.format(self._value))

    def SetValue(self, val):
        """Set a float value or None."""
        self._value = val
        self._update_ui()

    def GetValue(self):
        return self._value

    def _on_text_enter(self, event):
        raw = self.text.GetValue().strip()
        if raw == "":
            self._value = None
        else:
            try:
                val = float(raw.replace(",", "."))
                self._value = max(self.min_val, min(self.max_val, val))
            except ValueError:
                pass
        self._update_ui()
        event.Skip()

    def _on_spin(self, event):
        pos = event.GetPosition()
        step = self.inc if pos > self._last_spin else -self.inc
        self._last_spin = pos

        if self._value is None:
            self._value = self.min_val
        else:
            self._value = max(self.min_val, min(self.max_val, self._value + step))

        self._update_ui()
        self._post_event()

    def _post_event(self):
        evt = ValueChangeEvent(self.GetId(), Value=self.GetValue())
        self.GetEventHandler().ProcessEvent(evt)


class ColourButton(wx.Button):
    """Colour picker button with three-state support (None = mixed)."""
    callback = None

    def __init__(self, parent, size=None):
        if size is None:
            size = parent.FromDIP(wx.Size(100, 30))
        super().__init__(parent, label="", size=size)
        self._colour = None
        self.Bind(wx.EVT_BUTTON, self.on_click)
        self.Bind(wx.EVT_SIZE, lambda e: (e.Skip(), self.update_bitmap()))
        self.update_bitmap()

    def on_click(self, event):
        cd = wx.ColourData()
        cd.SetColour(self._colour)
        dlg = wx.ColourDialog(self, cd)
        if dlg.ShowModal() == wx.ID_OK:
            self.set_colour(dlg.GetColourData().GetColour())
            if self.callback:
                self.callback()
        dlg.Destroy()

    def set_colour(self, colour):
        self._colour = colour
        self.update_bitmap()

    def get_colour(self):
        return wx.Colour(self._colour).GetAsString()

    def update_bitmap(self):
        w, h = self.GetSize()
        if w < 1 or h < 1:
            return
        bmp = wx.Bitmap(w, h)
        dc = wx.MemoryDC(bmp)

        if sys.platform == 'win32':
            # Fill corners with panel background so rounded corners look clean.
            dc.SetBackground(wx.Brush(self.GetParent().GetBackgroundColour()))
            dc.Clear()
            gc = wx.GCDC(dc)
            gc.SetPen(wx.Pen(wx.Colour(160, 160, 160), 1))
            r = 3
            if self._colour is None:
                # White base + hatch overlay to signal "mixed"
                gc.SetBrush(wx.WHITE_BRUSH)
                gc.DrawRoundedRectangle(1, 1, w - 2, h - 2, r)
                gc.SetPen(wx.TRANSPARENT_PEN)
                gc.SetBrush(wx.Brush(wx.Colour(160, 160, 160),
                                     wx.BRUSHSTYLE_BDIAGONAL_HATCH))
                gc.DrawRoundedRectangle(1, 1, w - 2, h - 2, r)
            else:
                gc.SetBrush(wx.Brush(self._colour))
                gc.DrawRoundedRectangle(1, 1, w - 2, h - 2, r)
            gc = None
        else:
            if self._colour is None:
                dc.SetBackground(wx.WHITE_BRUSH)
                dc.Clear()
                brush = wx.Brush(wx.BLACK, wx.BRUSHSTYLE_BDIAGONAL_HATCH)
            else:
                brush = wx.Brush(self._colour)
            dc.SetPen(wx.TRANSPARENT_PEN)
            dc.SetBrush(brush)
            dc.DrawRectangle(0, 0, w, h)

        dc.SelectObject(wx.NullBitmap)
        self.SetBitmap(bmp)
