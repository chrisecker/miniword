import wx
from typing import Callable, List, Tuple
from .textmodel.viewbase import ViewBase
from .inspector import InspectorPanel
from .documentview import DocumentView
from . import icons

SIDE_PANEL_W = 360
ICON_BAR_W = 48
ICON_SIZE = 20

BAR_BG = wx.Colour(245, 245, 245)
ACTIVE_COLOR = wx.Colour(60, 120, 200)


# Farben
COLOR_NORMAL = wx.Colour(90, 90, 90)       # #5A5A5A
COLOR_HOVER  = wx.Colour(30, 144, 255)     # #1E90FF
COLOR_ACTIVE = wx.Colour(0, 122, 204)      # #007ACC

class IconBar(wx.Panel):
    """
    Custom drawn vertical toolbar with SVG icons.
    Active indicator can be on left or right.
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

        # Berechne Button-Rects für Klick/MouseOver
        self._button_rects: dict[str, wx.Rect] = {}
        self._recalculate_rects()

        self.Bind(wx.EVT_SIZE, lambda e: (self._recalculate_rects(), e.Skip()))

    # ------------------------------------------------------------
    # Layout / Button Rects
    # ------------------------------------------------------------
    def _recalculate_rects(self):
        y = 8
        self._button_rects.clear()
        for key, _, _ in self.entries:
            rect = wx.Rect(0, y, ICON_BAR_W, ICON_SIZE + 8)  # 8px Abstand unten
            self._button_rects[key] = rect
            y += ICON_SIZE + 8
        self.Refresh()

    # ------------------------------------------------------------
    # Mouse Events
    # ------------------------------------------------------------
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

    # ------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------
    def _on_paint(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        dc.Clear()
        size = self.GetClientSize()

        # Hintergrund
        dc.SetBrush(wx.Brush(BAR_BG))
        dc.SetPen(wx.TRANSPARENT_PEN)
        dc.DrawRectangle(0, 0, size.width, size.height)

        # Draw each icon
        for key, iconname, tooltip in self.entries:
            rect = self._button_rects[key]
            x = (ICON_BAR_W - ICON_SIZE) // 2
            y = rect.y

            # Active indicator
            if key == self._active:
                dc.SetBrush(wx.Brush(COLOR_ACTIVE))
                dc.SetPen(wx.TRANSPARENT_PEN)
                if self.side == 'left':
                    dc.DrawRectangle(0, rect.y, 4, rect.height)
                else:
                    dc.DrawRectangle(ICON_BAR_W - 4, rect.y, 4, rect.height)

            # Icon zeichnen (SVG als BitmapBundle laden)
            # Wir nehmen einfach icons.icon(iconname+state) konvention
            iconname = iconname.replace(".svg", "")
            state_suffix = ''
            if key == self._active:
                state_suffix = '_active.svg'
            elif key == self._hover:
                state_suffix = '_hover.svg'
            else:
                state_suffix = '.svg'

            bundle = icons.icon(iconname + state_suffix, size=(ICON_SIZE, ICON_SIZE))
            bmp = bundle.GetBitmapFor(self)
            dc.DrawBitmap(bmp, x, y, True)

            
# ---------------------------------------------------------------------------
# Document Settings Inspector (Mockup)
# ---------------------------------------------------------------------------

class DocumentSettingsInspector(wx.Panel):
    """Panel with document settings like page size, margins, etc."""

    def __init__(self, parent):
        super().__init__(parent)
        self.SetBackgroundColour(wx.Colour(248, 248, 248))

        outer = wx.BoxSizer(wx.VERTICAL)
        scrolled = wx.ScrolledWindow(self, style=wx.VSCROLL)
        scrolled.SetScrollRate(0, 10)

        form = wx.BoxSizer(wx.VERTICAL)

        # Page size
        box_page = wx.StaticBoxSizer(wx.VERTICAL, scrolled, "Page Size")
        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(scrolled, label="Format"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        self.choice_format = wx.Choice(scrolled, choices=["A4", "A5", "Letter", "Legal", "Custom"])
        self.choice_format.SetSelection(0)
        row.Add(self.choice_format, 1)
        box_page.Add(row, 0, wx.EXPAND | wx.ALL, 6)

        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(scrolled, label="Orientation"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        self.choice_orientation = wx.Choice(scrolled, choices=["Portrait", "Landscape"])
        self.choice_orientation.SetSelection(0)
        row.Add(self.choice_orientation, 1)
        box_page.Add(row, 0, wx.EXPAND | wx.ALL, 6)
        form.Add(box_page, 0, wx.EXPAND | wx.ALL, 8)

        # Margins
        box_margins = wx.StaticBoxSizer(wx.VERTICAL, scrolled, "Margins (mm)")
        grid = wx.FlexGridSizer(2, 4, 6, 6)
        labels = ["Top", "Bottom", "Left", "Right"]
        self.margin_ctrls = {}
        for label in labels:
            grid.Add(wx.StaticText(scrolled, label=label), 0, wx.ALIGN_CENTER_VERTICAL)
            ctrl = wx.SpinCtrlDouble(scrolled, min=0, max=100, inc=1, initial=25)
            ctrl.SetDigits(1)
            self.margin_ctrls[label.lower()] = ctrl
            grid.Add(ctrl, 1, wx.EXPAND)
        grid.AddGrowableCol(1)
        grid.AddGrowableCol(3)
        box_margins.Add(grid, 1, wx.EXPAND | wx.ALL, 6)
        form.Add(box_margins, 0, wx.EXPAND | wx.ALL, 8)

        # Header/Footer
        box_header = wx.StaticBoxSizer(wx.VERTICAL, scrolled, "Header / Footer")
        self.chk_header = wx.CheckBox(scrolled, label="Enable Header")
        self.chk_footer = wx.CheckBox(scrolled, label="Enable Footer")
        box_header.Add(self.chk_header, 0, wx.ALL, 4)
        box_header.Add(self.chk_footer, 0, wx.ALL, 4)
        form.Add(box_header, 0, wx.EXPAND | wx.ALL, 8)

        # Metadata
        box_meta = wx.StaticBoxSizer(wx.VERTICAL, scrolled, "Document Info")
        meta = wx.FlexGridSizer(2, 2, 6, 6)
        meta.Add(wx.StaticText(scrolled, label="Title"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.txt_title = wx.TextCtrl(scrolled)
        meta.Add(self.txt_title, 1, wx.EXPAND)
        meta.Add(wx.StaticText(scrolled, label="Author"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.txt_author = wx.TextCtrl(scrolled)
        meta.Add(self.txt_author, 1, wx.EXPAND)
        meta.AddGrowableCol(1)
        box_meta.Add(meta, 1, wx.EXPAND | wx.ALL, 6)
        form.Add(box_meta, 0, wx.EXPAND | wx.ALL, 8)

        form.AddStretchSpacer()
        scrolled.SetSizer(form)
        outer.Add(scrolled, 1, wx.EXPAND)
        self.SetSizer(outer)


# ---------------------------------------------------------------------------
# Generic Side Panel (Left or Right)
# ---------------------------------------------------------------------------

class SidePanel(wx.Panel):
    """A panel that can hold multiple plugin pages, like RightPanel or LeftPanel."""

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
            print("key:", key)
            print("pages:", self._pages)
            assert False
            return

        self._book.SetSelection(self._pages[key])
        self.Show()


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainFrame(wx.Frame, ViewBase):

    def __init__(self, document):
        self.document = document
        wx.Frame.__init__(self, None, title="Writer", size=(1400, 700))
        ViewBase.__init__(self)
        
        self.SetMinSize((800, 480))
        self._build_menu()
        self._build_layout()
        self.Centre()

    def _build_menu(self):
        bar = wx.MenuBar()
        file_menu = wx.Menu()
        file_menu.Append(wx.ID_EXIT, "E&xit\tAlt+F4")
        bar.Append(file_menu, "&File")
        self.SetMenuBar(bar)
        self.Bind(wx.EVT_MENU, lambda _: self.Close(), id=wx.ID_EXIT)
        # --- Edit ---
        edit_menu = wx.Menu()
        self.undo_item = edit_menu.Append(wx.ID_UNDO, "&Undo\tCtrl+Z")
        self.redo_item = edit_menu.Append(wx.ID_REDO, "&Redo\tCtrl+Y")
        edit_menu.AppendSeparator()
        edit_menu.Append(wx.ID_CUT, "Cu&t\tCtrl+X")
        edit_menu.Append(wx.ID_COPY, "&Copy\tCtrl+C")
        edit_menu.Append(wx.ID_PASTE, "&Paste\tCtrl+V")
        bar.Append(edit_menu, "&Edit")

    def _build_layout(self):
        root = wx.BoxSizer(wx.HORIZONTAL)

        # Editor
        self.textview = DocumentView(self, self.document)
        self.textview.SetBackgroundColour("light grey")

        # Side panels
        self._left_panel = SidePanel(self)
        self._right_panel = SidePanel(self)

        # Inspectors for right panel
        self.inspector = InspectorPanel(self._right_panel, self.textview, self.document.basestyles)
        self.document_settings = DocumentSettingsInspector(self._right_panel)
        self._right_panel.add_page("format", self.inspector)
        self._right_panel.add_page("settings", self.document_settings)

        # Left panel example page (optional)
        # self._left_panel.add_page("left_plugin", SomePanel(self._left_panel))

        from .search import SearchPanel
        self._left_panel.add_page("search", SearchPanel(self._left_panel, self.textview))
        self._left_icon_bar = IconBar(
            self,
            self.show_left_panel,
            [("search", "search.svg", "Search")],
            side = 'left'            
        )
        # Icon bars
        #self._left_icon_bar = IconBar(self, self.show_left_panel)
        self._right_icon_bar = IconBar(
            self,
            self.show_right_panel,
            [("format", "style.svg", "Paragraph format"),
             ("settings", "settings.svg", "Document settings")],
            side = 'right'            
        )

        # Layout: LeftIcon | LeftPanel | Editor | RightPanel | RightIcon
        root.Add(self._left_icon_bar, 0, wx.EXPAND)
        root.Add(self._left_panel, 0, wx.EXPAND)
        root.Add(self.textview, 1, wx.EXPAND)
        root.Add(self._right_panel, 0, wx.EXPAND)
        root.Add(self._right_icon_bar, 0, wx.EXPAND)

        self.SetSizer(root)

    def show_right_panel(self, key):
        print("showing right: ", key)
        self._right_panel.show_page(key)
        self.Layout()

    def show_left_panel(self, key):
        print("show left:", key)
        self._left_panel.show_page(key)
        self.Layout()
        
    def _update_undo_ui(self):
        if not hasattr(self, "textview"): return
        self.undo_item.Enable(self.textview.undocount() > 0)
        self.redo_item.Enable(self.textview.redocount() > 0)

    def undo_changed(self, *args):
        wx.CallAfter(self._update_undo_ui)

        

def demo_00():
    from einstein import get_einstein_model
    from .document import Document
    from .styles import stylesheet

    app = wx.App(True)
    doc = Document()
    doc.textmodel = get_einstein_model()
    doc.basestyles = stylesheet
    frame = MainFrame(doc)
    frame.Show()

    if 1:
        view = frame.textview
        inspector = frame.inspector
        
        from .wxtextview import testing
        l = locals()
        l.update(globals())
        testing.pyshell(l)

    app.MainLoop()
    

def demo_01():
    from moby import get_moby_model
    from .document import Document
    from .styles import stylesheet

    app = wx.App(True)
    doc = Document()
    doc.textmodel = get_moby_model()
    doc.basestyles = stylesheet
    frame = MainFrame(doc)
    frame.Show()

    if 1:
        view = frame.textview
        inspector = frame.inspector
        
        from .wxtextview import testing
        l = locals()
        l.update(globals())
        testing.pyshell(l)

    app.MainLoop()
