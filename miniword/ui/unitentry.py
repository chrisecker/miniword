import re
import wx
from wx.lib.newevent import NewEvent
from .design import muted_button


UnitChangedEvent, EVT_UNIT_CHANGED = NewEvent()


def _parse(text, units, display_unit):
    """Parse 'value [unit]' string. Returns canonical value or raises ValueError."""
    m = re.match(r'^([+-]?\d+(?:\.\d+)?)\s*(\S+)?$', text.strip())
    if not m:
        raise ValueError
    unit = (m.group(2) or display_unit).lower()
    if unit not in units:
        raise ValueError(f"Unknown unit: {unit!r}")
    return float(m.group(1)) * units[unit]


class UnitInput(wx.Panel):
    """Base class for unit-aware spin inputs.

    Subclasses define:
        units        — {unit_name: factor}  where canonical = display_value * factor.
                       The internal (canonical) unit has factor 1.0 implicitly.
        display_unit — preferred display unit; user-changeable in the future.

    SetValue/GetValue and event.value are always in canonical units.
    """
    units = {}
    display_unit = ""

    def __init__(self, parent, display_unit=None):
        super().__init__(parent)
        if display_unit is not None:
            self.display_unit = display_unit
        self._last = None

        self.text = wx.TextCtrl(self, value=f"10 {self.display_unit}",
                                style=wx.TE_PROCESS_ENTER | wx.TE_RIGHT)
        self.text.SetMinSize((100, -1))
        btn_up = muted_button(self, "▲", size=(14, -1))
        btn_dn = muted_button(self, "▼", size=(14, -1))
        btn_up.SetMinSize((14, -1))
        btn_dn.SetMinSize((14, -1))

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.Add(btn_up, 0, wx.EXPAND|wx.LEFT, 10)
        btn_sizer.Add(btn_dn, 0, wx.EXPAND)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self.text, 1, wx.EXPAND)
        sizer.Add(btn_sizer, 0, wx.EXPAND)
        self.SetSizer(sizer)

        btn_up.Bind(wx.EVT_BUTTON, self._on_up)
        btn_dn.Bind(wx.EVT_BUTTON, self._on_down)
        self.text.Bind(wx.EVT_TEXT_ENTER, self._on_commit)
        self.text.Bind(wx.EVT_KILL_FOCUS,  self._on_commit)

    def _parse(self, text):
        return _parse(text, self.units, self.display_unit)

    def _format(self, canonical):
        factor = self.units[self.display_unit]
        return f"{canonical / factor:g} {self.display_unit}"

    def _commit(self):
        text = self.text.GetValue()
        if not text:
            return
        try:
            v = self._parse(text)
        except ValueError:
            wx.Bell()
            return
        if v != self._last:
            self._last = v
            wx.PostEvent(self, UnitChangedEvent(value=v, text=text, source=self))

    def _on_commit(self, event):
        self._commit()
        event.Skip()

    def _on_up(self, event):
        self._change_value(+1)

    def _on_down(self, event):
        self._change_value(-1)

    def _change_value(self, delta):
        text = self.text.GetValue().strip()
        factor = self.units[self.display_unit]
        try:
            canonical = self._parse(text) if text else 0.0
        except ValueError:
            return
        canonical += delta * factor
        self.text.SetValue(self._format(canonical))
        self._commit()

    def SetValue(self, value):
        if value is None:
            self.text.SetValue("")
            self._last = None
            return
        self._last = value
        self.text.SetValue(self._format(value))

    def GetValue(self):
        return self._last


class LengthInput(UnitInput):
    """UnitInput for physical lengths. Canonical unit: pt (factor 1.0)."""
    units = {"pt": 1.0, "mm": 72.0 / 25.4, "cm": 72.0 / 2.54, "inch": 72.0, "in": 72.0}
    display_unit = "mm"


class FractionInput(UnitInput):
    """UnitInput for ratios expressed as percent. Canonical unit: ratio (1.0 = 100%)."""
    units = {"%": 0.01}
    display_unit = "%"


def demo_00():
    app = wx.App()
    frame = wx.Frame(None, title="UnitInput Demo", size=(300, 120))
    panel = wx.Panel(frame)
    length = LengthInput(panel, display_unit="mm")
    fraction = FractionInput(panel)
    sizer = wx.BoxSizer(wx.VERTICAL)
    sizer.Add(length,   0, wx.ALL | wx.EXPAND, 10)
    sizer.Add(fraction, 0, wx.ALL | wx.EXPAND, 10)
    panel.SetSizer(sizer)
    frame.Show()
    app.MainLoop()
