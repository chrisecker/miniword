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
    The display is rounded; the exact value is kept as long as the
    displayed text isn't edited.
    """
    units = {}
    display_unit = ""

    def __init__(self, parent, display_unit=None):
        super().__init__(parent)
        if display_unit is not None:
            self.display_unit = display_unit
        self._last = None   # the exact value
        self._shown = None  # the text we displayed for it

        dip = self.FromDIP
        self.text = wx.TextCtrl(self, value=f"10 {self.display_unit}",
                                style=wx.TE_PROCESS_ENTER | wx.TE_RIGHT)
        self.text.SetMinSize((dip(80), -1))
        h = self.text.GetBestSize().height
        btn_w = dip(14)
        btn_up = muted_button(self, "▲", size=(btn_w, h))
        btn_dn = muted_button(self, "▼", size=(btn_w, h))
        btn_up.SetMinSize((btn_w, h))
        btn_dn.SetMinSize((btn_w, h))

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.Add(btn_up, 0, wx.EXPAND|wx.LEFT, dip(10))
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
            self._show(self._last)

    def _show(self, value):
        self._shown = self._format(value)
        self.text.SetValue(self._shown)

    def _parse(self, text):
        value, unit = _parse(text, self.units, self.display_unit)
        self.display_unit = unit
        return value

    def _format(self, canonical):
        factor = self.units[self.display_unit]
        value = round(canonical / factor, 2) or 0.0  # no "-0"
        return f"{value:g} {self.display_unit}"

    def _commit(self):
        text = self.text.GetValue()
        if not text or text == self._shown:
            return  # not edited: keep the exact value
        try:
            v = self._parse(text)
        except ValueError:
            wx.Bell()
            return
        self._shown = text
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
            if text == self._shown and self._last is not None:
                canonical = self._last  # exact, not the rounded display
            else:
                canonical = self._parse(text) if text else 0.0
        except ValueError:
            return
        canonical += delta * self.units[self.display_unit]
        self._last = canonical
        self._show(canonical)
        wx.PostEvent(self, UnitChangedEvent(value=canonical, text=self._shown,
                                            source=self))

    def SetValue(self, value):
        if value is None:
            self.text.SetValue("")
            self._last = self._shown = None
            return
        self._last = value
        self._show(value)

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


def _input(cls=None):
    """A LengthInput (or cls) in a frame, and the list of committed
    values it reports."""
    global _app
    if wx.App.Get() is None:
        _app = wx.App(False)  # keep a reference
    frame = wx.Frame(None)
    entry = cls(frame) if cls else LengthInput(frame, category="typographic")
    events = []
    entry.Bind(EVT_UNIT_CHANGED, lambda e: events.append(e.value))
    return frame, entry, events


def _flush():
    wx.GetApp().ProcessPendingEvents()


MM = 72.0 / 25.4


def test_00():
    "the display is rounded to 2 decimals, trailing zeros left out"
    frame, entry, events = _input()
    try:
        entry.SetValue(4.23333 * MM)
        assert entry.text.GetValue() == "4.23 mm"
        entry.SetValue(1.0)  # 1 pt
        assert entry.text.GetValue() == "0.35 mm"
        entry.SetValue(10 * MM)
        assert entry.text.GetValue() == "10 mm"
    finally:
        frame.Destroy()


def test_01():
    "committing an unchanged display keeps the exact value"
    frame, entry, events = _input()
    try:
        entry.SetValue(4.23333 * MM)
        entry._commit()  # e.g. focus in and out, or Enter
        _flush()
        assert events == []
        assert entry.GetValue() == 4.23333 * MM
    finally:
        frame.Destroy()


def test_02():
    "a typed value is taken exactly"
    frame, entry, events = _input()
    try:
        entry.SetValue(4.23333 * MM)
        entry.text.SetValue("4.23456 mm")
        entry._commit()
        _flush()
        assert events == [4.23456 * MM]
        assert entry.GetValue() == 4.23456 * MM
    finally:
        frame.Destroy()


def test_03():
    "the arrows step from the exact value"
    frame, entry, events = _input()
    try:
        entry.SetValue(4.23333 * MM)
        entry._change_value(+1)
        _flush()
        assert abs(entry.GetValue() - 5.23333 * MM) < 1e-9
        assert entry.text.GetValue() == "5.23 mm"
        assert len(events) == 1
    finally:
        frame.Destroy()


def test_04():
    "switching the unit only changes the display"
    frame, entry, events = _input()
    try:
        entry.SetValue(4.23333 * MM)
        entry.set_display_unit("pt")
        assert entry.text.GetValue() == "12 pt"
        entry._commit()
        _flush()
        assert events == [] and entry.GetValue() == 4.23333 * MM
    finally:
        frame.Destroy()


def test_05():
    "percent values are rounded the same way"
    frame, entry, events = _input(FractionInput)
    try:
        entry.SetValue(1.15)
        assert entry.text.GetValue() == "115 %"
        entry.SetValue(1 / 3)
        assert entry.text.GetValue() == "33.33 %"
        entry._commit()
        _flush()
        assert events == [] and entry.GetValue() == 1 / 3
    finally:
        frame.Destroy()
