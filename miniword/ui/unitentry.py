import re
import weakref
import wx
from wx.lib.newevent import NewEvent
from .design import muted_button


UnitChangedEvent, EVT_UNIT_CHANGED = NewEvent()


def _parse(text, units, display_unit):
    """Parse 'value [unit]' string. Returns (canonical_value, unit_used) or raises ValueError."""
    m = re.match(r'^([+-]?\d+(?:\.\d+)?)\s*(\S+)?$', text.strip())
    if not m:
        raise ValueError
    unit = (m.group(2) or display_unit).lower()
    if unit not in units:
        raise ValueError(f"Unknown unit: {unit!r}")
    return float(m.group(1)) * units[unit], unit


class UnitPrefs:
    """Model: per-category unit preferences. Views (LengthInput) register by category.

    Categories: "layout" (margins, paper) and "typographic" (spacing, indents).
    """

    def __init__(self, layout="mm", typographic="mm"):
        self._units = {"layout": layout, "typographic": typographic}
        self._views = {}  # {category: [weakref]}

    def get_unit(self, category):
        return self._units.get(category, "mm")

    def set_unit(self, category, unit):
        self._units[category] = unit
        self._notify(category)

    def register(self, view, category):
        self._views.setdefault(category, []).append(weakref.ref(view))

    def _notify(self, category):
        alive = []
        for ref in self._views.get(category, []):
            view = ref()
            if view is None:
                continue
            try:
                view.set_display_unit(self._units[category])
                alive.append(ref)
            except RuntimeError:
                pass  # wx C++ object was destroyed
        self._views[category] = alive


class UnitInput(wx.Panel):
    """Base class for unit-aware spin inputs.

    Subclasses define:
        units        — {unit_name: factor}  where canonical = display_value * factor.
        display_unit — default display unit; overridden by UnitPrefs if set.

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
        h = self.text.GetBestSize().height
        btn_up = muted_button(self, "▲", size=(14, h))
        btn_dn = muted_button(self, "▼", size=(14, h))
        btn_up.SetMinSize((14, h))
        btn_dn.SetMinSize((14, h))

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

    def set_display_unit(self, unit):
        self.display_unit = unit
        if self._last is not None:
            self.text.SetValue(self._format(self._last))

    def _parse(self, text):
        value, unit = _parse(text, self.units, self.display_unit)
        self.display_unit = unit
        return value

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
        try:
            canonical = self._parse(text) if text else 0.0
        except ValueError:
            return
        factor = self.units[self.display_unit]
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
    """UnitInput for physical lengths. Canonical unit: pt (factor 1.0).

    Each instance belongs to a category ("layout" or "typographic") and
    registers with LengthInput.prefs (a UnitPrefs instance) if set.
    Set LengthInput.prefs at app startup before creating any widgets.
    """
    units = {"pt": 1.0, "mm": 72.0 / 25.4, "cm": 72.0 / 2.54, "inch": 72.0, "in": 72.0}
    display_unit = "mm"
    prefs = None

    def __init__(self, parent, category="layout"):
        self._category = category
        unit = self.prefs.get_unit(category) if self.prefs else self.display_unit
        super().__init__(parent, display_unit=unit)
        if self.prefs is not None:
            self.prefs.register(self, category)
        self.text.Bind(wx.EVT_CONTEXT_MENU, self._on_context_menu)

    def _on_context_menu(self, event):
        menu = wx.Menu()
        ids = {}
        for unit in self.units:
            if unit == "in":
                continue  # skip alias
            item = menu.AppendRadioItem(wx.ID_ANY, unit)
            ids[item.GetId()] = unit
            if unit == self.display_unit:
                item.Check(True)

        def on_select(e):
            unit = ids.get(e.GetId())
            if unit:
                if self.prefs is not None:
                    from ..core.config import get_config
                    self.prefs.set_unit(self._category, unit)
                    get_config().set(f"{self._category}_unit", unit)
                else:
                    self.set_display_unit(unit)

        menu.Bind(wx.EVT_MENU, on_select)
        self.text.PopupMenu(menu)
        menu.Destroy()


class FractionInput(UnitInput):
    """UnitInput for ratios expressed as percent. Canonical unit: ratio (1.0 = 100%)."""
    units = {"%": 0.01}
    display_unit = "%"


def demo_00():
    app = wx.App()
    frame = wx.Frame(None, title="UnitInput Demo", size=(300, 120))
    panel = wx.Panel(frame)
    length = LengthInput(panel, category="layout")
    fraction = FractionInput(panel)
    sizer = wx.BoxSizer(wx.VERTICAL)
    sizer.Add(length,   0, wx.ALL | wx.EXPAND, 10)
    sizer.Add(fraction, 0, wx.ALL | wx.EXPAND, 10)
    panel.SetSizer(sizer)
    frame.Show()
    app.MainLoop()
