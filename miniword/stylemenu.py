"""
Style selection dropdown widget.

Classes:
    StyleDropdown  – main control (base class)
    StylePopup     – floating list panel
    BasestyleDropdown / ListstyleDropdown – concrete subclasses
"""

import re
import wx
from typing import Optional
from dataclasses import dataclass, field
from .textmodel.viewbase import ViewBase


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
    size = int(style["font_size"])
    return wx.Font(
        min(max(8, size), 26), wx.FONTFAMILY_ROMAN, slant, weight,
        style["underline"], style["font_family"],
    )


PADDING_LEFT  = 8
TRIANGLE_AREA = 30


# ---------------------------------------------------------------------------
# Popup panel
# ---------------------------------------------------------------------------

class StylePopup(wx.PopupWindow):
    """Floating list that shows all available styles."""

    def __init__(self, parent: "StyleDropdown"):
        super().__init__(parent, flags=wx.BORDER_SIMPLE)
        self.dropdown = parent

        self.styles: tuple[str, ...] = ()
        self._labels: list[str] = []
        self._item_rects: list[tuple[int, int]] = []  # (y, height) per entry

        self.hover_item: Optional[int] = None
        self.triangle_hover: bool = False

        self.panel = wx.Panel(self)
        self.panel.SetBackgroundColour(wx.WHITE)

        self.panel.Bind(wx.EVT_PAINT,        self._on_paint)
        self.panel.Bind(wx.EVT_MOTION,       self._on_mouse_move)
        self.panel.Bind(wx.EVT_LEFT_DOWN,    self._on_left_down)
        self.panel.Bind(wx.EVT_LEAVE_WINDOW, self._on_leave)
        self.panel.Bind(wx.EVT_MENU,         self._on_menu)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def SetStyles(self, styles):
        self.styles  = tuple(styles)
        self._labels = [self.dropdown.GetItemLabel(s) for s in self.styles]
        self._item_rects = self._compute_rects()

    def Popup(self):
        dd = self.dropdown
        w  = dd.GetSize().width
        h  = self._total_height() + 2   # +2 for border

        self.panel.SetSize(w, h)
        self.SetSize(w, h)
        self.Move(dd.ClientToScreen(wx.Point(0, dd.GetSize().height)))
        self.Show()
        self.panel.SetFocus()
        wx.GetApp().Bind(wx.EVT_LEFT_DOWN, self._on_global_click)

    def Hide(self):
        if self.IsShown():
            wx.GetApp().Unbind(wx.EVT_LEFT_DOWN, handler=self._on_global_click)
        super().Hide()

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------

    def _compute_rects(self) -> list[tuple[int, int]]:
        dc = wx.MemoryDC()
        dc.SelectObject(wx.NullBitmap)
        rects: list[tuple[int, int]] = []
        y = 0
        for name in self.styles:
            _, h = self.Parent.GetItemExtent(name, dc)
            rects.append((y, h))
            y += h
        return rects

    def _total_height(self) -> int:
        if not self._item_rects:
            return 0
        last_y, last_h = self._item_rects[-1]
        return last_y + last_h

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _on_paint(self, _evt):
        dc = wx.BufferedPaintDC(self.panel)
        dc.SetBackground(wx.Brush(wx.WHITE))
        dc.Clear()

        w, _ = self.panel.GetSize()

        for i, (name, label) in enumerate(zip(self.styles, self._labels)):
            item_y, item_h = self._item_rects[i]

            if i == self.hover_item:
                dc.SetBrush(wx.Brush(wx.Colour(235, 235, 235)))
                dc.SetPen(wx.TRANSPARENT_PEN)
                dc.DrawRectangle(0, item_y, w, item_h)

            self.Parent.DrawItem(name, dc, PADDING_LEFT, item_y, item_h)

            if i == self.hover_item:
                self._draw_triangle(dc, w, item_y, item_h)

    def _draw_triangle(self, dc: wx.DC, panel_w: int, item_y: int, item_h: int):
        color = wx.Colour(30, 30, 30)
        cx = panel_w - TRIANGLE_AREA // 2
        cy = item_y + item_h // 2

        if self.triangle_hover:
            dc.SetBrush(wx.Brush(wx.Colour(180, 210, 255)))
            dc.SetPen(wx.TRANSPARENT_PEN)
            #dc.SetPen(wx.Pen(wx.Colour(120, 160, 220)))
            dc.DrawCircle(cx, cy, 9)

        pts = [wx.Point(cx - 3, cy - 5), wx.Point(cx - 3, cy + 5), wx.Point(cx + 4, cy)]
        dc.SetBrush(wx.Brush(color))
        dc.SetPen(wx.Pen(color))
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
        return x >= w - TRIANGLE_AREA

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_global_click(self, evt):
        if self.IsShown() and not self.GetScreenRect().Contains(wx.GetMousePosition()):
            self.Hide()
        evt.Skip()

    def _on_mouse_move(self, evt: wx.MouseEvent):
        x, y = evt.GetPosition()
        new_hover = self._item_at(y)
        new_tri   = self._is_over_triangle(x) if new_hover is not None else False

        if new_hover != self.hover_item or new_tri != self.triangle_hover:
            self.hover_item     = new_hover
            self.triangle_hover = new_tri
            self.panel.Refresh()

        self.panel.SetCursor(wx.Cursor(wx.CURSOR_HAND if new_tri else wx.CURSOR_ARROW))

    def _on_leave(self, _evt):
        self.hover_item     = None
        self.triangle_hover = False
        self.panel.Refresh()

    def _on_left_down(self, evt: wx.MouseEvent):
        x, y = evt.GetPosition()
        idx = self._item_at(y)
        if idx is not None:                         # FIX: was `idx >= 0` which raises on None
            if self._is_over_triangle(x):
                return self._show_context_menu(idx)
            self.dropdown.Choose(idx)
        self.Hide()

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def _show_context_menu(self, idx: int):
        style = self.styles[idx]
        label = self.Parent.GetItemLabel(style)
        self._clicked_style = style

        menu = wx.Menu()
        self._menu_ids: list[int] = []

        def add(text: str):
            item_id = menu.Append(wx.ID_ANY, text).GetId()
            self._menu_ids.append(item_id)

        add("Create new paragraph style from selection")
        add("Redefine style from selection")
        add("Revert to original style")
        menu.AppendSeparator()
        add(f"Select all uses of \"{label}\"")
        menu.AppendSeparator()
        add("Rename style")
        add("Delete style")

        role_map = {"Title": "Title", "Heading 1": "H1", "Heading 2": "H2"}
        role = role_map.get(label, "?")
        add(f"Assign role ({role})")

        w, _ = self.panel.GetSize()
        item_y, item_h = self._item_rects[idx]
        screen_pos = self.panel.ClientToScreen(wx.Point(w - TRIANGLE_AREA, item_y + item_h))
        self.panel.PopupMenu(menu, self.panel.ScreenToClient(screen_pos))
        menu.Destroy()
        self.Hide()

    def _on_menu(self, event):
        try:
            i = self._menu_ids.index(event.GetId())
        except ValueError:
            return
        actions = {
            0: lambda: self.Parent.CreateNewStyle(self._clicked_style),
            1: lambda: self.Parent.UpdateStyle(self._clicked_style),
            2: lambda: self.Parent.RevertStyle(self._clicked_style),
        }
        action = actions.get(i)
        if action:
            action()


# ---------------------------------------------------------------------------
# Main control
# ---------------------------------------------------------------------------

class StyleDropdown(wx.Control, ViewBase):
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
        self.overrides: dict  = {}
        self.modified: bool   = False
        self._popup: Optional[StylePopup] = None
        self._hover: bool     = False

        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_PAINT,        self._on_paint)
        self.Bind(wx.EVT_LEFT_DOWN,    self._on_click)
        self.Bind(wx.EVT_ENTER_WINDOW, lambda _: self._set_hover(True))
        self.Bind(wx.EVT_LEAVE_WINDOW, lambda _: self._set_hover(False))

    stylesheet = None
    on_redefine_style = None  # callable(name, new_style, overrides)
    on_create_style   = None  # callable(new_name, new_style, overrides)
    on_revert_style   = None  # callable(overrides)

    def set_stylesheet(self, stylesheet):
        if self.stylesheet is not None:
            self.remove_model(self.stylesheet)
        self.stylesheet = stylesheet
        self.set_model(stylesheet)
        self.styles = stylesheet.keys()

    def set_properties(self, name: Optional[str], properties: dict, overrides: dict):
        self.properties = properties
        self.overrides  = overrides

        if name is None:
            # Ambiguous selection (multiple paragraphs with different styles).
            self.selection = -1
            self.modified  = False
            self.Refresh()
            return                              # NOTE: UpdateSelection is intentionally skipped

        i = self.styles.index(name)
        self.selection = i                      # set directly to avoid spurious EVT_CHOICE
        self.modified  = any(k in overrides for k in self.stylesheet.get(name).keys())
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

    def _set_hover(self, state: bool):
        self._hover = state
        self.Refresh()

    def _on_paint(self, _evt):
        dc = wx.AutoBufferedPaintDC(self)
        w, h = self.GetClientSize()

        bg = wx.Colour(240, 240, 240) if self._hover else wx.WHITE
        dc.SetBrush(wx.Brush(bg))
        dc.SetPen(wx.Pen(wx.Colour(150, 150, 150)))
        dc.DrawRoundedRectangle(0, 0, w, h, 3)

        if self.styles and 0 <= self.selection < len(self.styles):
            self.DrawItem(self.styles[self.selection], dc, 8, 0, h)

        # Small dropdown arrow
        cx, cy = w - 14, h // 2
        color = wx.Colour("red") if self.modified else wx.Colour(80, 80, 80)
        dc.SetBrush(wx.Brush(color))
        dc.SetPen(wx.Pen(color))
        dc.DrawPolygon([wx.Point(cx - 6, cy - 3), wx.Point(cx + 6, cy - 3),
                        wx.Point(cx, cy + 3)])

    def _on_click(self, _evt):
        if self._popup and self._popup.IsShown():
            self._popup.Hide()
            return
        self._popup = StylePopup(self)
        self._popup.SetStyles(self.styles)
        self._popup.Popup()

    # ------------------------------------------------------------------
    # Style operations
    # ------------------------------------------------------------------

    def CreateNewStyle(self, name: str):
        label = self.GetItemLabel(name)
        new_style = self.stylesheet.get(name).copy()
        for key, value in self.properties.items():
            if key in new_style and value is not None:
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
            if key in new_style and value is not None:
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

class BasestyleDropdown(StyleDropdown):
    def UpdateSelection(self):
        name = self.properties.get("base", "normal")
        self.SetSelection(self.styles.index(name))

    def GetItemLabel(self, name: str) -> str:
        return self.stylesheet.get(name)["name"]

    def GetItemFont(self, name: str) -> wx.Font:
        return get_font(self.stylesheet.get(name))

    def DrawItem(self, name: str, dc: wx.DC, x: int, y: int, box_h: int):
        style = self.stylesheet.get(name)
        dc.SetFont(self.GetItemFont(name))
        dc.SetTextForeground(style["color"])
        label = self.GetItemLabel(name)
        _, th = dc.GetTextExtent(label)
        dc.DrawText(label, x, y + (box_h - th) // 2)


class ListstyleDropdown(StyleDropdown):
    def GetItemLabel(self, name: str) -> str:
        return self.stylesheet.get(name)["name"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_00():
    "mk_label"
    assert mk_label("List", [])           == "List (1)"
    assert mk_label("List", ["List (1)"]) == "List (2)"
    assert mk_label("List (1)", [])       == "List (2)"


def test_01():
    "BasestyleDropdown – modified flag"
    app = wx.App(False)
    frame = wx.Frame(None)
    dropdown = BasestyleDropdown(frame)
    from .styles import stylesheet
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
    dropdown = BasestyleDropdown(frame)
    from .styles import stylesheet
    dropdown.set_stylesheet(stylesheet)
    dropdown.set_properties("h1", {"font_size": 1}, {})
    n = len(stylesheet.keys())
    dropdown.CreateNewStyle("h1")
    assert len(stylesheet.keys()) == n + 1


def test_03():
    "UpdateStyle"
    app = wx.App(False)
    frame = wx.Frame(None)
    dropdown = BasestyleDropdown(frame)
    from .styles import stylesheet
    dropdown.set_stylesheet(stylesheet)
    dropdown.set_properties("h1", {"font_size": 1}, {})
    dropdown.UpdateStyle("h1")
    assert stylesheet.get("h1")["font_size"] == 1


# ---------------------------------------------------------------------------
# Demos
# ---------------------------------------------------------------------------

def demo_00():
    "BasestyleDropdown"
    app = wx.App(True)
    frame = wx.Frame(None)
    frame.Centre()
    frame.Show()
    dropdown = BasestyleDropdown(frame)
    from .styles import stylesheet
    dropdown.set_stylesheet(stylesheet)
    dropdown.SetSelection(2)
    from .wxtextview import testing
    testing.pyshell({**locals(), **globals()})
    app.MainLoop()


def demo_01():
    "ListstyleDropdown"
    from .stylesheet import StyleSheet
    liststyles = StyleSheet()
    liststyles.set("numbers", {"name": "1, 2, 3"})
    liststyles.set("letters", {"name": "a, b, c"})
    liststyles.set("roman",   {"name": "I, II, III"})

    app = wx.App(True)
    frame = wx.Frame(None)
    frame.Centre()
    frame.Show()
    dropdown = ListstyleDropdown(frame)
    dropdown.set_stylesheet(liststyles)
    dropdown.SetSelection(2)
    app.MainLoop()


