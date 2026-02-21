import wx
from .textmodel.viewbase import ViewBase
from .inspector import InspectorPanel
from .documentview import DocumentView

ICON_SIZE    = 32
ICON_BAR_W   = 44
SIDE_PANEL_W = 360


# ---------------------------------------------------------------------------
# Icon bar
# ---------------------------------------------------------------------------

class IconBar(wx.Panel):
    """Thin vertical toolbar. Buttons toggle the side panels."""

    def __init__(self, parent, on_toggle, buttons=None):
        super().__init__(parent, size=(ICON_BAR_W, -1))
        self.SetBackgroundColour(wx.Colour(230, 230, 230))
        self.on_toggle = on_toggle
        self._active: str | None = None

        self._buttons: dict[str, wx.BitmapButton] = {}
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.AddSpacer(8)

        # Default buttons
        if buttons is None:
            buttons = [
                ("style", "S", "Style Inspector"),
                ("page",  "P", "Document Settings"),
            ]

        for key, label, tooltip in buttons:
            btn = self._make_button(key, label, tooltip)
            self._buttons[key] = btn
            sizer.Add(btn, 0, wx.ALIGN_CENTRE_HORIZONTAL | wx.BOTTOM, 6)

        self.SetSizer(sizer)

    def _make_button(self, key, label, tooltip):
        bmp = self._render_icon(label, active=False)
        btn = wx.BitmapButton(
            self,
            bitmap=bmp,
            size=(ICON_SIZE, ICON_SIZE),
            style=wx.BORDER_NONE,
        )
        btn.SetToolTip(tooltip)
        btn.Bind(wx.EVT_BUTTON, lambda e, k=key: self._on_click(k))
        return btn

    def _on_click(self, key):
        if self._active == key:
            self._active = None
        else:
            self._active = key

        self._refresh_icons()
        self.on_toggle(self._active)

    def _refresh_icons(self):
        for key, btn in self._buttons.items():
            label = "S" if key == "style" else "P"
            bmp = self._render_icon(label, active=(key == self._active))
            btn.SetBitmap(bmp)

    @staticmethod
    def _render_icon(label, active):
        size = ICON_SIZE
        bmp = wx.Bitmap(size, size)
        dc = wx.MemoryDC(bmp)

        bg = wx.Colour(90, 130, 200) if active else wx.Colour(200, 200, 200)
        dc.SetBackground(wx.Brush(bg))
        dc.Clear()

        fg = wx.WHITE if active else wx.Colour(60, 60, 60)
        font = wx.Font(13, wx.FONTFAMILY_DEFAULT,
                       wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        dc.SetFont(font)
        dc.SetTextForeground(fg)

        tw, th = dc.GetTextExtent(label)
        dc.DrawText(label, (size - tw) // 2, (size - th) // 2)

        dc.SelectObject(wx.NullBitmap)
        return bmp


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
            return

        self._book.SetSelection(self._pages[key])
        labels = {
            "style": "Style Inspector",
            "page":  "Document Settings",
        }
        self._title.SetLabel(labels.get(key, ""))
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
        self._right_panel.add_page("style", self.inspector)
        self._right_panel.add_page("page", self.document_settings)

        # Left panel example page (optional)
        # self._left_panel.add_page("left_plugin", SomePanel(self._left_panel))

        # Icon bars
        self._left_icon_bar = IconBar(self, lambda key: self._left_panel.show_page(key))
        self._right_icon_bar = IconBar(self, lambda key: self._right_panel.show_page(key))

        # Layout: LeftIcon | LeftPanel | Editor | RightPanel | RightIcon
        root.Add(self._left_icon_bar, 0, wx.EXPAND)
        root.Add(self._left_panel, 0, wx.EXPAND)
        root.Add(self.textview, 1, wx.EXPAND)
        root.Add(self._right_panel, 0, wx.EXPAND)
        root.Add(self._right_icon_bar, 0, wx.EXPAND)

        self.SetSizer(root)

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
