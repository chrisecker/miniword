import wx
from typing import Callable, List, Tuple

from ..icons import icon as load_icon


SIDE_PANEL_W = 360
ICON_BAR_W = 48
ICON_SIZE = 20

BAR_BG       = wx.Colour(245, 245, 245)
COLOR_NORMAL = wx.Colour(90, 90, 90)
COLOR_HOVER  = wx.Colour(30, 144, 255)
COLOR_ACTIVE = wx.Colour(0, 122, 204)


class IconBar(wx.Panel):
    """
    Custom drawn vertical toolbar with SVG icons.
    Active indicator can be on left or right.

    entries: list of (key, iconname, tooltip)
    on_toggle: called with the active key or None when toggled off
    """

    def __init__(
        self, parent: wx.Window,
        on_toggle: Callable[[str | None], None],
        entries: List[Tuple[str, str, str]],
        side: str = 'left'
    ):
        super().__init__(parent, size=(ICON_BAR_W, -1))

        self.entries = entries
        self.side = side
        self.on_toggle = on_toggle

        self._active: str | None = None
        self._hover: str | None = None

        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetBackgroundColour(BAR_BG)

        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_click)
        self.Bind(wx.EVT_MOTION, self._on_motion)
        self.Bind(wx.EVT_LEAVE_WINDOW, self._on_leave)

        self._button_rects: dict[str, wx.Rect] = {}
        self._recalculate_rects()

        self.Bind(wx.EVT_SIZE, lambda e: (self._recalculate_rects(), e.Skip()))

    def _recalculate_rects(self):
        y = 8
        self._button_rects.clear()
        for key, _, _ in self.entries:
            rect = wx.Rect(0, y, ICON_BAR_W, ICON_SIZE + 8)
            self._button_rects[key] = rect
            y += ICON_SIZE + 8
        self.Refresh()

    def _on_click(self, event: wx.MouseEvent):
        pos = event.GetPosition()
        for key, rect in self._button_rects.items():
            if rect.Contains(pos):
                self._active = None if self._active == key else key
                self.on_toggle(self._active)
                self.Refresh()
                break

    def _on_motion(self, event: wx.MouseEvent):
        pos = event.GetPosition()
        hover_changed = False
        for key, rect in self._button_rects.items():
            if rect.Contains(pos):
                if self._hover != key:
                    self._hover = key
                    hover_changed = True
                break
        else:
            if self._hover is not None:
                self._hover = None
                hover_changed = True
        if hover_changed:
            self.Refresh()

    def _on_leave(self, event: wx.MouseEvent):
        if self._hover is not None:
            self._hover = None
            self.Refresh()

    def _on_paint(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        dc.Clear()
        size = self.GetClientSize()

        dc.SetBrush(wx.Brush(BAR_BG))
        dc.SetPen(wx.TRANSPARENT_PEN)
        dc.DrawRectangle(0, 0, size.width, size.height)

        for key, iconname, tooltip in self.entries:
            rect = self._button_rects[key]
            x = (ICON_BAR_W - ICON_SIZE) // 2
            y = rect.y

            if key == self._active:
                dc.SetBrush(wx.Brush(COLOR_ACTIVE))
                dc.SetPen(wx.TRANSPARENT_PEN)
                if self.side == 'left':
                    dc.DrawRectangle(0, rect.y, 4, rect.height)
                else:
                    dc.DrawRectangle(ICON_BAR_W - 4, rect.y, 4, rect.height)

            iconname = iconname.replace(".svg", "")
            if key == self._active:
                state_suffix = '_active.svg'
            elif key == self._hover:
                state_suffix = '_hover.svg'
            else:
                state_suffix = '.svg'

            bundle = load_icon(iconname + state_suffix, size=(ICON_SIZE, ICON_SIZE))
            bmp = bundle.GetBitmapFor(self)
            dc.DrawBitmap(bmp, x, y, True)


class SidePanel(wx.Panel):
    """A panel that can hold multiple plugin pages (left or right sidebar)."""

    def __init__(self, parent, width=SIDE_PANEL_W):
        super().__init__(parent, size=(width, -1))
        self.SetBackgroundColour(wx.Colour(248, 248, 248))

        outer = wx.BoxSizer(wx.VERTICAL)
        self._title = wx.StaticText(self, label="")
        font = self._title.GetFont()
        font.SetWeight(wx.FONTWEIGHT_BOLD)
        self._title.SetFont(font)

        self._book = wx.Simplebook(self)
        self._pages: dict[str, int] = {}

        outer.Add(self._title, 0, wx.ALL, 10)
        outer.Add(self._book, 1, wx.EXPAND | wx.ALL, 2)
        self.SetSizer(outer)
        self.Hide()

    def add_page(self, key: str, panel: wx.Panel):
        idx = self._book.GetPageCount()
        self._book.AddPage(panel, "")
        self._pages[key] = idx

    def show_page(self, key: str | None):
        if key is None:
            self.Hide()
            return
        if key not in self._pages:
            raise KeyError("Unknown page key: %r" % key)
        self._book.SetSelection(self._pages[key])
        self.Show()
