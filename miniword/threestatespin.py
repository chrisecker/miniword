import wx


ValueChangeEvent, EVT_SPIN_VALUE = wx.lib.newevent.NewCommandEvent()

class SpinCtrl3(wx.Panel):
    def __init__(self, parent, initial=None, min=0.0, max=100.0, inc=0.1, digits=2):
        super().__init__(parent)
        
        self.min_val = min
        self.max_val = max
        self.inc = inc
        self.digits = digits
        self._value = initial # internal float value or None

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        self.text = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.spin = wx.SpinButton(self, style=wx.SP_VERTICAL)
        self.spin.SetRange(-10000, 10000)
        self._last_spin = self.spin.GetValue()

        sizer.Add(self.text, 1, wx.EXPAND)
        sizer.Add(self.spin, 0, wx.EXPAND)
        self.SetSizer(sizer)

        self._update_ui()

        # Events
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
                pass # ignore invalid entries
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

