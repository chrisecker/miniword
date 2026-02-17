import wx
from wx.lib.newevent import NewEvent


UnitChangedEvent, EVT_UNIT_CHANGED = NewEvent()

class UnitInput(wx.Panel):
    _last_pt = None
    def __init__(self, parent, default_unit="mm"):
        super().__init__(parent)

        self.default_unit = default_unit

        self.text = wx.TextCtrl(self, value=f"10 {default_unit}",
                                style=wx.TE_PROCESS_ENTER)
        self.spin = wx.SpinButton(self, style=wx.SP_VERTICAL)

        self.spin.SetRange(-100000, 100000)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self.text, 1, wx.EXPAND)
        sizer.Add(self.spin, 0)
        self.SetSizer(sizer)

        self.spin.Bind(wx.EVT_SPIN_UP, self.on_up)
        self.spin.Bind(wx.EVT_SPIN_DOWN, self.on_down)

        self.text.Bind(wx.EVT_TEXT_ENTER, self.on_commit)
        self.text.Bind(wx.EVT_KILL_FOCUS, self.on_commit)

    def commit(self):
        text = self.text.GetValue()
        if not text:
            return
        try:
            pt = parse_measure(text, self.default_unit)
        except ValueError:
            wx.Bell()

        if pt != self._last_pt:
            self._last_pt = pt
            evt = UnitChangedEvent(
                value_pt=pt,
                text=text,
                source=self
            )
            wx.PostEvent(self, evt)
            self._last_pt = pt
        
    def on_commit(self, event):
        self.commit()
        event.Skip()

    def on_up(self, event):
        self._change_value(+1)

    def on_down(self, event):
        self._change_value(-1)

    def _change_value(self, delta):
        text = self.text.GetValue().strip()
        if not text:
            pt = 0
        else:
            try:
                pt = parse_measure(text, self.default_unit)
            except ValueError:
                return

        # zurück in aktuelle Einheit
        factor = UNIT_TO_PT[self.default_unit]
        value = pt / factor + delta

        self.text.SetValue(f"{value:g} {self.default_unit}")
        self.commit()

    def SetValue(self, value):
        #print("unit_entry - set value:", value)
        if value is None:
            self.text.SetValue("")
            self._last_pt = None
            return
        factor = UNIT_TO_PT[self.default_unit]
        value = value / factor
        self.text.SetValue(f"{value:g} {self.default_unit}")
        self._last_pt = value

    def GetValue(self):
        return self._last_pt
        


import re

UNIT_TO_PT = {
    "pt": 1.0,
    "mm": 72.0 / 25.4,
    "cm": 72.0 / 2.54,
    "inch": 72.0,
    "in": 72.0,
}

UNIT_PATTERN = re.compile(
    r"""
    ^\s*
    (?P<value>[+-]?\d+(?:\.\d+)?)
    \s*
    (?P<unit>pt|mm|cm|inch|in)?
    \s*$
    """,
    re.VERBOSE | re.IGNORECASE
)


def parse_measure(text, default_unit="pt"):
    m = UNIT_PATTERN.match(text)
    if not m:
        raise ValueError("Ungültiges Maß")

    value = float(m.group("value"))
    unit = (m.group("unit") or default_unit).lower()

    return value * UNIT_TO_PT[unit]


class MyFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title="Unit Input")

        panel = wx.Panel(self)
        unit_input = UnitInput(panel, default_unit="mm")

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(unit_input, 0, wx.ALL | wx.EXPAND, 10)
        panel.SetSizer(sizer)

        self.Show()

def demo_00():
    app = wx.App(redirect=False)
    f = MyFrame()
    app.MainLoop()
