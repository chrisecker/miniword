"""
Style selection widget.

Classes:
    StyleSelector  – main control (base class)
    StyleList      – floating list panel
    BasestyleSelector / ListstyleSelector – concrete subclasses
"""

import re
import wx
from typing import Optional
from dataclasses import dataclass, field
from ..textmodel.viewbase import ViewBase
from ..core.styles import PARAGRAPH_ONLY_KEYS
# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def mk_label(base: str, existing: list[str]) -> str:
    """Return a copy label that does not clash with *existing* labels.

    'List'      -> 'List (1)'
    'List (1)'  -> 'List (2)'  (if 'List (2)' is free)
    """
    m = re.match(r"^(.*?)(?:\s*\((\d+)\))?$", base)
    stem = m.group(1).rstrip()
    counter = (int(m.group(2)) if m.group(2) else 0) + 1
    while True:
        candidate = f"{stem} ({counter})"
        if candidate not in existing:
            return candidate
        counter += 1


def get_font(style: dict) -> wx.Font:
    weight = wx.FONTWEIGHT_BOLD if style.get("bold") else wx.FONTWEIGHT_NORMAL
    slant  = wx.FONTSTYLE_ITALIC if style.get("italic") else wx.FONTSTYLE_NORMAL
    size   = min(max(8.0, float(style["font_size"])), 26.0)
    info   = wx.FontInfo(size).FaceName(style["font_family"])
    if style.get("bold"):
        info = info.Bold()
    if style.get("italic"):
        info = info.Italic()
    if style["underline"]:
        info = info.Underlined()
    return wx.Font(info)


PADDING_LEFT  = 8
TRIANGLE_AREA = 30
PLUS_HEIGHT   = 28
POPUP_EXTRA_W = 40

SEL_NORMAL   = wx.Colour(255, 255, 255)
SEL_HOVER    = wx.Colour(232, 232, 228)
SEL_OPEN     = wx.Colour(225, 235, 252)
SEL_BORDER   = wx.Colour(195, 195, 190)
SEL_BORDER_H = wx.Colour(120, 120, 120)
SEL_BORDER_O = wx.Colour(0,   100, 200)
SEL_ARROW    = wx.Colour(80,  80,  80)
SEL_MODIFIED = wx.Colour(200, 60,  0)
LIST_BG      = wx.Colour(255, 255, 255)
LIST_HOVER   = wx.Colour(222, 222, 218)
LIST_BORDER  = wx.Colour(140, 140, 135)
LIST_SEP     = wx.Colour(180, 180, 175)
LIST_TEXT    = wx.Colour(60,  60,  60)
LIST_TRI     = wx.Colour(30,  30,  30)
LIST_TRI_H   = wx.Colour(180, 210, 255)



# ---------------------------------------------------------------------------
# Popup panel
# ---------------------------------------------------------------------------

class StyleList(wx.PopupTransientWindow):
    """Floating list that shows all available styles."""

    def __init__(self, parent: "StyleSelector"):
        super().__init__(parent, wx.BORDER_NONE)
        self.dropdown = parent

        self.styles: tuple[str, ...] = ()
        self._labels: list[str] = []
        self._item_rects: list[tuple[int, int]] = []  # (y, height) per entry

        self.hover_item: Optional[int] = None
        self.triangle_hover: bool = False

        self.panel = wx.Panel(self)
        self.panel.SetBackgroundColour(LIST_BG)

        self.panel.Bind(wx.EVT_PAINT,        self.on_paint)
        self.panel.Bind(wx.EVT_MOTION,       self.on_mouse_move)
        self.panel.Bind(wx.EVT_LEFT_DOWN,    self.on_left_down)
        self.panel.Bind(wx.EVT_LEAVE_WINDOW, self.on_leave)
        self.panel.Bind(wx.EVT_MENU,         self.on_menu)
        self.Bind(wx.EVT_SHOW, self.on_show)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def SetStyles(self, styles):
        self.styles  = tuple(styles)
        self._labels = [self.dropdown.GetItemLabel(s) for s in self.styles]
        self._item_rects = self._compute_rects()

    def Popup(self):
        dip = self.FromDIP
        dd = self.dropdown
        extra_w = dip(POPUP_EXTRA_W)
        w = dd.GetSize().width + extra_w
        h = self._total_height() + 2   # +2 for border

        self.panel.SetSize(w, h)
        self.SetSize(w, h)
        self.Move(dd.ClientToScreen(wx.Point(-extra_w, dd.GetSize().height)))
        super().Popup()
        self.panel.SetFocus()

    def on_show(self, evt):
        if not evt.IsShown():
            self.dropdown.Refresh()
        evt.Skip()

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------

    def _compute_rects(self) -> list[tuple[int, int]]:
        dc = wx.ClientDC(self.Parent)
        plus_h = self.FromDIP(PLUS_HEIGHT)
        rects: list[tuple[int, int]] = [(0, plus_h)]  # index 0 = "+" item
        y = plus_h
        for name in self.styles:
            _, h = self.Parent.GetItemExtent(name, dc)
            rects.append((y, h))
            y += h
        return rects

    def _total_height(self) -> int:
        if not self._item_rects:
            return PLUS_HEIGHT
        last_y, last_h = self._item_rects[-1]
        return last_y + last_h

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def on_paint(self, _evt):
        dc = wx.BufferedPaintDC(self.panel)
        dc.SetBackground(wx.Brush(LIST_BG))
        dc.Clear()

        w, h = self.panel.GetSize()
        dip = self.FromDIP
        pad = dip(PADDING_LEFT)
        plus_y, plus_h = self._item_rects[0]
        if self.hover_item == 0:
            dc.SetBrush(wx.Brush(LIST_HOVER))
            dc.SetPen(wx.TRANSPARENT_PEN)
            dc.DrawRectangle(0, plus_y, w, plus_h)
        dc.SetFont(wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT))
        dc.SetTextForeground(LIST_TEXT)
        dc.DrawText("+ Create new style from selection",
                    pad, plus_y + (plus_h - dc.GetCharHeight()) // 2)

        dc.SetPen(wx.Pen(LIST_SEP))
        dc.DrawLine(0, plus_y + plus_h - 1, w, plus_y + plus_h - 1)

        for i, (name, label) in enumerate(zip(self.styles, self._labels)):
            item_y, item_h = self._item_rects[i + 1]
            if i + 1 == self.hover_item:
                dc.SetBrush(wx.Brush(LIST_HOVER))
                dc.SetPen(wx.TRANSPARENT_PEN)
                dc.DrawRectangle(0, item_y, w, item_h)
            self.Parent.DrawItem(name, dc, pad, item_y, item_h)
            if i + 1 == self.hover_item:
                self._draw_triangle(dc, w, item_y, item_h)

        dc.SetBrush(wx.TRANSPARENT_BRUSH)
        dc.SetPen(wx.Pen(LIST_BORDER))
        dc.DrawRectangle(0, 0, w, h)

    def _draw_triangle(self, dc: wx.DC, panel_w: int, item_y: int, item_h: int):
        dip = self.FromDIP
        cx = panel_w - dip(TRIANGLE_AREA) // 2
        cy = item_y + item_h // 2

        if self.triangle_hover:
            dc.SetBrush(wx.Brush(LIST_TRI_H))
            dc.SetPen(wx.TRANSPARENT_PEN)
            dc.DrawCircle(cx, cy, min(item_h // 2 - 1, dip(13)))

        pts = [wx.Point(cx - dip(3), cy - dip(5)),
               wx.Point(cx - dip(3), cy + dip(5)),
               wx.Point(cx + dip(4), cy)]
        dc.SetBrush(wx.Brush(LIST_TRI))
        dc.SetPen(wx.Pen(LIST_TRI))
        dc.DrawPolygon(pts)

    # ------------------------------------------------------------------
    # Hit testing
    # ------------------------------------------------------------------

    def _item_at(self, y: int) -> Optional[int]:
        for i, (iy, ih) in enumerate(self._item_rects):
            if iy <= y < iy + ih:
                return i
        return None

    def _is_over_triangle(self, x: int) -> bool:
        w, _ = self.panel.GetSize()
        return x >= w - self.FromDIP(TRIANGLE_AREA)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def on_mouse_move(self, evt: wx.MouseEvent):
        x, y = evt.GetPosition()
        new_hover = self._item_at(y)
        new_tri   = self._is_over_triangle(x) if new_hover and new_hover > 0 else False

        if new_hover != self.hover_item or new_tri != self.triangle_hover:
            self.hover_item     = new_hover
            self.triangle_hover = new_tri
            self.panel.Refresh()

        self.panel.SetCursor(wx.Cursor(wx.CURSOR_HAND if new_tri else wx.CURSOR_ARROW))

    def on_leave(self, _evt):
        self.hover_item     = None
        self.triangle_hover = False
        self.panel.Refresh()

    def on_left_down(self, evt: wx.MouseEvent):
        x, y = evt.GetPosition()
        idx = self._item_at(y)
        if idx == 0:
            key = self.dropdown.GetSelectedKey() or self.styles[0]
            self.Dismiss()
            self.dropdown.CreateNewStyle(key)
        elif idx is not None:
            if self._is_over_triangle(x):
                return self._show_context_menu(idx - 1)
            self.dropdown.Choose(idx - 1)
            self.Dismiss()

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def _show_context_menu(self, idx: int):
        style = self.styles[idx]
        label = self.Parent.GetItemLabel(style)
        self._clicked_style = style
        is_protected = style in self.Parent.protected

        menu = wx.Menu()
        self._menu_ids: list[int] = []

        def add(text: str, enabled: bool = True):
            item = menu.Append(wx.ID_ANY, text)
            self._menu_ids.append(item.GetId())
            if not enabled:
                menu.Enable(item.GetId(), False)

        add("Redefine style from selection",  not is_protected)
        add("Revert to original style",       not is_protected)
        menu.AppendSeparator()
        add("Rename style",                   not is_protected)
        add("Delete style",                   not is_protected)

        w, _ = self.panel.GetSize()
        item_y, item_h = self._item_rects[idx]
        screen_pos = self.panel.ClientToScreen(wx.Point(w - self.FromDIP(TRIANGLE_AREA), item_y + item_h))
        self.panel.PopupMenu(menu, self.panel.ScreenToClient(screen_pos))
        menu.Destroy()
        self.Dismiss()

    def on_menu(self, event):
        try:
            i = self._menu_ids.index(event.GetId())
        except ValueError:
            return
        actions = {
            0: lambda: self.Parent.UpdateStyle(self._clicked_style),
            1: lambda: self.Parent.RevertStyle(self._clicked_style),
            2: lambda: self.Parent.RenameStyle(self._clicked_style),
            3: lambda: self.Parent.DeleteStyle(self._clicked_style),
        }
        action = actions.get(i)
        if action:
            action()


# ---------------------------------------------------------------------------
# Main control
# ---------------------------------------------------------------------------

class StyleSelector(wx.Control, ViewBase):
    """
    Base dropdown for style selection.

    Subclasses may override ``GetItemLabel``, ``GetItemFont``, and
    ``DrawItem`` to customise appearance per style.
    """

    def __init__(self, parent, **kwargs):
        ViewBase.__init__(self)
        wx.Control.__init__(self, parent, style=wx.NO_BORDER, **kwargs)

        self.selection: int = 0
        self.styles: tuple[str, ...] = ()
        self.properties: dict = {}
        self.overrides: set   = set()
        self.modified: bool   = False
        self._popup: Optional[StyleList] = None

        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_PAINT,        self.on_paint)
        self.Bind(wx.EVT_LEFT_DOWN,    self.on_click)
        self.Bind(wx.EVT_ENTER_WINDOW, lambda _: self.Refresh())
        self.Bind(wx.EVT_LEAVE_WINDOW, lambda _: self.Refresh())

    stylesheet = None
    protected: frozenset = frozenset()
    on_redefine_style = None  # callable(name, new_style, overrides)
    on_create_style   = None  # callable(new_name, new_style, overrides)
    on_revert_style   = None  # callable(overrides)
    on_rename_style   = None  # callable(name, new_label)
    on_delete_style   = None  # callable(name)

    def set_stylesheet(self, stylesheet):
        if self.stylesheet is not None:
            self.remove_model(self.stylesheet)
        self.stylesheet = stylesheet
        self.set_model(stylesheet)
        self.styles = stylesheet.keys()

    def set_properties(self, name: Optional[str], properties: dict, overrides: set):
        self.properties = properties
        # Strip paragraph-only keys: they must not trigger the modified flag
        # and must not be cleared when reverting to base style.
        self.overrides  = {k for k in overrides if k not in PARAGRAPH_ONLY_KEYS}

        if name is None or name not in self.styles:
            # Ambiguous selection (multiple paragraphs with different styles)
            # or style not defined in this stylesheet yet.
            self.selection = -1
            self.modified  = False
            self.Refresh()
            return                              # NOTE: UpdateSelection is intentionally skipped

        i = self.styles.index(name)
        self.selection = i                      # set directly to avoid spurious EVT_CHOICE
        self.modified  = any(k in self.overrides for k in self.stylesheet.get(name).keys())
        self.UpdateSelection()
        self.Refresh()

    def model_changed(self, *args):
        self.styles = self.stylesheet.keys()
        self.Refresh()

    def SetSelection(self, idx: int):
        self.selection = idx
        self.Refresh()
        
    def Choose(self, idx: int):
        self.SetSelection(idx)
        evt = wx.CommandEvent(wx.EVT_CHOICE.typeId, self.GetId())
        evt.SetInt(idx)
        evt.SetString(self.styles[idx])
        self.GetEventHandler().ProcessEvent(evt)

    def GetSelectedKey(self):
        idx = self.selection
        if idx < 0:
            return
        return self.styles[idx]

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def on_paint(self, _evt):
        dc = wx.AutoBufferedPaintDC(self)
        w, h = self.GetClientSize()
        dip = self.FromDIP

        is_open  = self._popup is not None and self._popup.IsShown()
        is_hover = self.GetScreenRect().Contains(wx.GetMousePosition())
        if is_open:
            bg, border = SEL_OPEN, SEL_BORDER_O
        elif is_hover:
            bg, border = SEL_HOVER, SEL_BORDER_H
        else:
            bg, border = SEL_NORMAL, SEL_BORDER

        dc.SetBackground(wx.Brush(bg))
        dc.Clear()
        dc.SetBrush(wx.Brush(bg))
        dc.SetPen(wx.Pen(border))
        dc.DrawRoundedRectangle(0, 0, w, h, dip(3))

        if self.styles and 0 <= self.selection < len(self.styles):
            self.DrawItem(self.styles[self.selection], dc, dip(PADDING_LEFT), 0, h)

        cx, cy = w - dip(14), h // 2
        arrow = SEL_MODIFIED if self.modified else SEL_ARROW
        dc.SetBrush(wx.Brush(arrow))
        dc.SetPen(wx.Pen(arrow))
        dc.DrawPolygon([wx.Point(cx - dip(6), cy - dip(3)),
                        wx.Point(cx + dip(6), cy - dip(3)),
                        wx.Point(cx, cy + dip(3))])

    def on_click(self, _evt):
        if self._popup and self._popup.IsShown():
            self._popup.Dismiss()
            return
        self._popup = StyleList(self)
        self._popup.SetStyles(self.styles)
        self._popup.Popup()
        self.Refresh()

    # ------------------------------------------------------------------
    # Style operations
    # ------------------------------------------------------------------

    def CreateNewStyle(self, name: str):
        label = self.GetItemLabel(name)
        new_style = self.stylesheet.get(name).copy()
        for key, value in self.properties.items():
            if key in new_style and value is not None and key not in PARAGRAPH_ONLY_KEYS:
                new_style[key] = value

        # Pick an unused internal key.
        i = 0
        while True:
            new_name = f"style{i}"
            if not self.stylesheet.contains(new_name):
                break
            i += 1

        existing_labels = [self.GetItemLabel(k) for k in self.styles]
        new_style["name"] = mk_label(label, existing_labels)

        if self.on_create_style:
            # Delegate stylesheet.set() to the callback so it can wrap both
            # the stylesheet change and the text-model change in one atomic().
            self.on_create_style(new_name, new_style, self.overrides)
        else:
            self.stylesheet.set(new_name, new_style)
        self.SetSelection(len(self.stylesheet.keys()) - 1)

    def UpdateStyle(self, name: str):
        new_style = self.stylesheet.get(name).copy()
        for key, value in self.properties.items():
            if key in new_style and value is not None and key not in PARAGRAPH_ONLY_KEYS:
                new_style[key] = value

        if self.on_redefine_style:
            # Delegate stylesheet.set() to the callback so it can wrap both
            # the stylesheet change and the text-model change in one atomic().
            self.on_redefine_style(name, new_style, self.overrides)
        else:
            self.stylesheet.set(name, new_style)

    def RevertStyle(self, name: str):
        if self.on_revert_style:
            self.on_revert_style(self.overrides)

    def RenameStyle(self, name: str):
        current_label = self.GetItemLabel(name)
        new_label = wx.GetTextFromUser(
            "New style name:", "Rename Style", current_label, self)
        if new_label and new_label != current_label:
            if self.on_rename_style:
                self.on_rename_style(name, new_label)

    def DeleteStyle(self, name: str):
        if name in self.protected:
            return
        if self.on_delete_style:
            self.on_delete_style(name)

    # ------------------------------------------------------------------
    # Overridable interface
    # ------------------------------------------------------------------

    def UpdateSelection(self):
        """Called after properties and overrides are updated."""
        pass

    def GetItemLabel(self, name: str) -> str:
        return name

    def GetItemFont(self, name: str) -> wx.Font:
        return wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)

    def GetItemExtent(self, name: str, dc: wx.DC) -> tuple[int, int]:
        dc.SetFont(self.GetItemFont(name))
        tw, th = dc.GetTextExtent(self.GetItemLabel(name))
        return tw, int(th * 1.7)

    def DrawItem(self, name: str, dc: wx.DC, x: int, y: int, box_h: int):
        dc.SetFont(self.GetItemFont(name))
        label = self.GetItemLabel(name)
        _, th = dc.GetTextExtent(label)
        dc.DrawText(label, x, y + (box_h - th) // 2)


# ---------------------------------------------------------------------------
# Concrete subclasses
# ---------------------------------------------------------------------------

class BasestyleSelector(StyleSelector):
    protected = frozenset({'normal'})

    def UpdateSelection(self):
        name = self.properties.get("base", "normal")
        self.SetSelection(self.styles.index(name))

    def GetItemLabel(self, name: str) -> str:
        return self.stylesheet.get(name).get("name", name)

    def GetItemFont(self, name: str) -> wx.Font:
        return get_font(self.stylesheet.get(name))

    def DrawItem(self, name: str, dc: wx.DC, x: int, y: int, box_h: int):
        style = self.stylesheet.get(name)
        dc.SetFont(self.GetItemFont(name))
        dc.SetTextForeground(style["color"])
        label = self.GetItemLabel(name)
        _, th = dc.GetTextExtent(label)
        dc.DrawText(label, x, y + (box_h - th) // 2)


class ListstyleSelector(StyleSelector):
    def GetItemLabel(self, name: str) -> str:
        return self.stylesheet.get(name).get("name", name)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_00():
    "mk_label"
    assert mk_label("List", [])           == "List (1)"
    assert mk_label("List", ["List (1)"]) == "List (2)"
    assert mk_label("List (1)", [])       == "List (2)"


def test_01():
    "BasestyleSelector – modified flag"
    app = wx.App(False)
    frame = wx.Frame(None)
    dropdown = BasestyleSelector(frame)
    from ..core.styles import testsheet as stylesheet
    dropdown.set_stylesheet(stylesheet)

    dropdown.set_properties("h1", {}, {})
    assert dropdown.modified == False
    assert dropdown.selection >= 0

    dropdown.set_properties("h1", {}, {"font_size": 1})
    assert dropdown.modified == True

    dropdown.set_properties("h1", {}, {"x": 1})   # irrelevant key
    assert dropdown.modified == False

    dropdown.set_properties(None, {}, {"x": 1})   # ambiguous selection
    assert dropdown.modified == False
    assert dropdown.selection == -1


def test_02():
    "CreateNewStyle"
    app = wx.App(False)
    frame = wx.Frame(None)
    dropdown = BasestyleSelector(frame)
    from ..core.styles import testsheet as stylesheet
    dropdown.set_stylesheet(stylesheet)
    dropdown.set_properties("h1", {"font_size": 1}, {})
    n = len(stylesheet.keys())
    dropdown.CreateNewStyle("h1")
    assert len(stylesheet.keys()) == n + 1


def test_04():
    "DeleteStyle – blocks 'normal', fires callback for other styles"
    app = wx.App(False)
    frame = wx.Frame(None)
    dropdown = BasestyleSelector(frame)
    from ..core.styles import testsheet as stylesheet
    dropdown.set_stylesheet(stylesheet)
    called = []
    dropdown.on_delete_style = lambda name: called.append(name)

    dropdown.DeleteStyle('normal')   # protected — must not fire
    assert called == []

    dropdown.DeleteStyle('h1')
    assert called == ['h1']


def test_03():
    "UpdateStyle"
    app = wx.App(False)
    frame = wx.Frame(None)
    dropdown = BasestyleSelector(frame)
    from ..core.styles import testsheet as stylesheet
    dropdown.set_stylesheet(stylesheet)
    dropdown.set_properties("h1", {"font_size": 1}, {})
    dropdown.UpdateStyle("h1")
    assert stylesheet.get("h1")["font_size"] == 1


# ---------------------------------------------------------------------------
# Demos
# ---------------------------------------------------------------------------

def demo_00():
    "BasestyleSelector"
    app = wx.App(True)
    frame = wx.Frame(None)
    frame.Centre()
    frame.Show()
    dropdown = BasestyleSelector(frame)
    from ..core.styles import testsheet as stylesheet
    dropdown.set_stylesheet(stylesheet)
    dropdown.SetSelection(2)
    from . import testing
    testing.pyshell({**locals(), **globals()})
    app.MainLoop()


def demo_01():
    "ListstyleSelector"
    from ..core.stylesheet import StyleSheet
    liststyles = StyleSheet()
    liststyles.set("numbers", {"name": "1, 2, 3"})
    liststyles.set("letters", {"name": "a, b, c"})
    liststyles.set("roman",   {"name": "I, II, III"})

    app = wx.App(True)
    frame = wx.Frame(None)
    frame.Centre()
    frame.Show()
    dropdown = ListstyleSelector(frame)
    dropdown.set_stylesheet(liststyles)
    dropdown.SetSelection(2)
    app.MainLoop()


