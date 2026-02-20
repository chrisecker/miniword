
import wx
from .inspector import InspectorPanel
from .documentview import DocumentView

ICON_SIZE   = 32
ICON_BAR_W  = 44
RIGHTPANEL_W = 360


# ---------------------------------------------------------------------------
# Icon bar
# ---------------------------------------------------------------------------

class IconBar(wx.Panel):
    """Thin vertical toolbar. Buttons toggle the inspector panel."""

    def __init__(self, parent, on_toggle):
        super().__init__(parent, size=(ICON_BAR_W, -1))
        self.SetBackgroundColour(wx.Colour(230, 230, 230))
        self.on_toggle = on_toggle
        self._active: str | None = None  # currently active icon key

        self._buttons: dict[str, wx.BitmapButton] = {}
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.AddSpacer(8)

        for key, label, tooltip in [
            ("style", "S",  "Style Inspector"),
            ("page",  "P",  "Page Inspector"),
        ]:
            btn = self._make_button(key, label, tooltip)
            self._buttons[key] = btn
            sizer.Add(btn, 0, wx.ALIGN_CENTRE_HORIZONTAL | wx.BOTTOM, 6)

        self.SetSizer(sizer)

    def _make_button(self, key: str, label: str, tooltip: str) -> wx.BitmapButton:
        bmp = self._render_icon(label, active=False)
        btn = wx.BitmapButton(self, bitmap=bmp, size=(ICON_SIZE, ICON_SIZE),
                              style=wx.BORDER_NONE)
        btn.SetToolTip(tooltip)
        btn.Bind(wx.EVT_BUTTON, lambda e, k=key: self._on_click(k))
        return btn

    def _on_click(self, key: str):
        # Second click on active button → close panel
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
    def _render_icon(label: str, active: bool) -> wx.Bitmap:
        """Draw a simple square icon with a letter."""
        size = ICON_SIZE
        bmp  = wx.Bitmap(size, size)
        dc   = wx.MemoryDC(bmp)

        bg = wx.Colour(90, 130, 200) if active else wx.Colour(200, 200, 200)
        dc.SetBackground(wx.Brush(bg))
        dc.Clear()

        fg = wx.WHITE if active else wx.Colour(60, 60, 60)
        font = wx.Font(13, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL,
                       wx.FONTWEIGHT_BOLD)
        dc.SetFont(font)
        dc.SetTextForeground(fg)
        tw, th = dc.GetTextExtent(label)
        dc.DrawText(label, (size - tw) // 2, (size - th) // 2)
        dc.SelectObject(wx.NullBitmap)
        return bmp


# ---------------------------------------------------------------------------
# Right panel
# ---------------------------------------------------------------------------


class RightPanel(wx.Panel):
    """Right-hand inspector. Content switches based on active mode."""

    def __init__(self, parent, textview, document):
        super().__init__(parent, size=(RIGHTPANEL_W, -1))
        self.SetBackgroundColour(wx.Colour(248, 248, 248))

        outer  = wx.BoxSizer(wx.VERTICAL)

        self._title = wx.StaticText(self, label="Style")
        title_font = self._title.GetFont()
        title_font.SetWeight(wx.FONTWEIGHT_BOLD)
        self._title.SetFont(title_font)

        self._content = InspectorPanel(self, textview, document.basestyles)
        self._content.SetBackgroundColour(wx.Colour(248, 248, 248))
        
        outer.Add(self._title,   0, wx.ALL, 10)
        outer.Add(self._content, 1, wx.EXPAND | wx.ALL, 2)

        self._title.Hide()
        self.SetSizer(outer)


    def set_mode(self, mode: str | None):
        labels = {"style": "Style Inspector", "page": "Page Inspector"}
        self._title.SetLabel(labels.get(mode, ""))


# ---------------------------------------------------------------------------
# Editor area
# ---------------------------------------------------------------------------

class EditorPanel(wx.Panel):

    def __init__(self, parent, document):
        super().__init__(parent)
        self.SetBackgroundColour(wx.Colour(180, 180, 180))  # grey "desktop"

        self._page  = DocumentView(self, document)
        
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(self._page, 1, wx.EXPAND | wx.ALL, 0)
        self.SetSizer(outer)



# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainFrame(wx.Frame):
    def __init__(self, document):
        self.document = document
        super().__init__(None, title="Writer — Mockup", size=(1200, 680))
        self.SetMinSize((640, 480))

        self._build_menu()
        self._build_layout()
        self.Centre()

    # ------------------------------------------------------------------
    # Menu
    # ------------------------------------------------------------------

    def _build_menu(self):
        bar = wx.MenuBar()

        file_menu = wx.Menu()
        file_menu.Append(wx.ID_NEW,   "&New\tCtrl+N")
        file_menu.Append(wx.ID_OPEN,  "&Open…\tCtrl+O")
        file_menu.Append(wx.ID_SAVE,  "&Save\tCtrl+S")
        file_menu.Append(wx.ID_SAVEAS,"Save &As…\tCtrl+Shift+S")
        file_menu.AppendSeparator()
        file_menu.Append(wx.ID_EXIT,  "E&xit\tAlt+F4")

        edit_menu = wx.Menu()
        edit_menu.Append(wx.ID_UNDO,      "&Undo\tCtrl+Z")
        edit_menu.Append(wx.ID_REDO,      "&Redo\tCtrl+Y")
        edit_menu.AppendSeparator()
        edit_menu.Append(wx.ID_CUT,       "Cu&t\tCtrl+X")
        edit_menu.Append(wx.ID_COPY,      "&Copy\tCtrl+C")
        edit_menu.Append(wx.ID_PASTE,     "&Paste\tCtrl+V")
        edit_menu.AppendSeparator()
        edit_menu.Append(wx.ID_SELECTALL, "Select &All\tCtrl+A")
        edit_menu.Append(wx.ID_FIND,      "&Find…\tCtrl+F")

        tools_menu = wx.Menu()
        tools_menu.Append(wx.ID_ANY, "&Spelling…")
        tools_menu.Append(wx.ID_ANY, "Word &Count")
        tools_menu.AppendSeparator()
        tools_menu.Append(wx.ID_PREFERENCES, "&Preferences…")

        bar.Append(file_menu,  "&File")
        bar.Append(edit_menu,  "&Edit")
        bar.Append(tools_menu, "&Tools")
        self.SetMenuBar(bar)

        self.Bind(wx.EVT_MENU, lambda _: self.Close(), id=wx.ID_EXIT)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_layout(self):
        root = wx.BoxSizer(wx.HORIZONTAL)

        self._editor    = EditorPanel(self, self.document)
        self._icon_bar  = IconBar(self, on_toggle=self._on_inspector_toggle)
        self._inspector = RightPanel(self, self._editor._page, self.document)
        self._inspector.Hide()

        root.Add(self._editor,    1, wx.EXPAND)
        root.Add(self._inspector, 0, wx.EXPAND)
        root.Add(self._icon_bar,  0, wx.EXPAND)

        self.SetSizer(root)

    def _on_inspector_toggle(self, mode: str | None):
        if mode is None:
            self._inspector.Hide()
        else:
            self._inspector.set_mode(mode)
            self._inspector.Show()
        self.Layout()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def demo_00():
    from einstein import get_einstein_model

    from .document import Document
    from .styles import stylesheet
    
    app = wx.App(True)
    doc = Document()
    doc.textmodel = get_einstein_model()
    doc.basestyles = stylesheet # XXX Setting of stylesheets is not implemented yet
    
    frame = MainFrame(doc)
    frame.Show()
    if 1:
        view = frame._editor._page
        inspector = frame._inspector._content
        from .wxtextview import testing
        l = locals()
        l.update(globals())
        testing.pyshell(l)
    app.MainLoop()

