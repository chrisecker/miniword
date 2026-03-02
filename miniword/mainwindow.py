import wx
from .textmodel.viewbase import ViewBase
from .inspector import InspectorPanel
from .settingsinspector import SettingsInspector
from .documentview import DocumentView
from .ui.sidepanel import SidePanel, IconBar


# ---------------------------------------------------------------------------
# Progress dialog
# ---------------------------------------------------------------------------

class _LayoutProgressDlg(wx.Dialog):
    def __init__(self, parent, total_chars):
        wx.Dialog.__init__(self, parent, title="Laying out document",
                           style=wx.CAPTION)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.label = wx.StaticText(self, label="Processing page 1…")
        sizer.Add(self.label, 0, wx.ALL, 12)
        self.gauge = wx.Gauge(self, range=max(total_chars, 1), size=(300, 16))
        sizer.Add(self.gauge, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 12)
        self.SetSizerAndFit(sizer)
        self.CentreOnParent()

    def update(self, n_pages, n_chars, total_chars):
        if n_pages is not None:
            self.label.SetLabel("Processing page %d…" % n_pages)
        self.gauge.SetValue(min(n_chars, total_chars))


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainFrame(wx.Frame, ViewBase):

    _progress_dlg = None

    def __init__(self, document):
        self.document = document
        wx.Frame.__init__(self, None, title="Writer", size=(1400, 700))
        ViewBase.__init__(self)
        
        self.SetMinSize((800, 480))
        self._build_menu()
        self._build_layout()
        self._update_title()
        self.Centre()

    def _build_menu(self):
        bar = wx.MenuBar()
        file_menu = wx.Menu()
        file_menu.Append(wx.ID_NEW,     "&New\tCtrl+N")
        file_menu.Append(wx.ID_OPEN,    "&Open\tCtrl+O")
        file_menu.Append(wx.ID_SAVE,    "&Save\tCtrl+S")
        file_menu.Append(wx.ID_SAVEAS,  "Save &As…\tCtrl+Shift+S")
        file_menu.AppendSeparator()
        self._id_export_pdf = wx.NewIdRef()
        file_menu.Append(self._id_export_pdf, "Export as &PDF…\tCtrl+Shift+E")
        file_menu.AppendSeparator()
        file_menu.Append(wx.ID_EXIT,    "E&xit\tAlt+F4")
        bar.Append(file_menu, "&File")
        self.SetMenuBar(bar)
        self.Bind(wx.EVT_MENU, self._on_new,    id=wx.ID_NEW)
        self.Bind(wx.EVT_MENU, self._on_open,   id=wx.ID_OPEN)
        self.Bind(wx.EVT_MENU, self._on_save,   id=wx.ID_SAVE)
        self.Bind(wx.EVT_MENU, self._on_saveas, id=wx.ID_SAVEAS)
        self.Bind(wx.EVT_MENU, self._on_export_pdf, id=self._id_export_pdf)
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
        self.textview.add_view(self)   # receive undo_changed for dirty indicator

        # Side panels
        self._left_panel = SidePanel(self)
        self._right_panel = SidePanel(self)

        # Inspectors for right panel
        self.inspector = InspectorPanel(self._right_panel, self.textview, self.document.basestyles)
        self.document_settings = SettingsInspector(self._right_panel, self.document)
        self._right_panel.add_page("format", self.inspector)
        self._right_panel.add_page("settings", self.document_settings)

        # Left panel example page (optional)
        # self._left_panel.add_page("left_plugin", SomePanel(self._left_panel))

        from .searchtool import SearchPanel
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

    def _update_title(self):
        import os
        path = getattr(self, '_current_path', None)
        name = os.path.basename(path) if path else "Untitled"
        dirty = hasattr(self, 'textview') and self.textview.undocount() > 0
        suffix = ' *' if dirty else ''
        self.SetTitle("Writer — " + name + suffix)

    def _on_new(self, event):
        from .document import Document
        frame = MainFrame(Document())
        frame.Show()

    def _on_open(self, event):
        with wx.FileDialog(
            self, "Open TXL file",
            wildcard="TXL files (*.txl)|*.txl|All files (*.*)|*.*",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            path = dlg.GetPath()
        from .document import Document
        doc = Document.load(path)
        frame = MainFrame(doc)
        frame._current_path = path
        frame._update_title()
        frame.Show()

    def _on_save(self, event):
        if not getattr(self, '_current_path', None):
            self._on_saveas(event)
            return
        self.document.save(self._current_path)
        self.textview.clear_undo()
        self._update_title()

    def _on_saveas(self, event):
        with wx.FileDialog(
            self, "Save TXL file",
            wildcard="TXL files (*.txl)|*.txl|All files (*.*)|*.*",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        ) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            path = dlg.GetPath()
        self._current_path = path
        self.document.save(path)
        self.textview.clear_undo()
        self._update_title()

    def _on_export_pdf(self, event):
        with wx.FileDialog(
            self, "Export as PDF",
            wildcard="PDF files (*.pdf)|*.pdf|All files (*.*)|*.*",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        ) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            path = dlg.GetPath()
        self.textview.export_pdf(path)

    def _replace_document(self, doc):
        self.document = doc
        self.textview.document = doc   # must be set before set_model → create_builder
        self.textview.set_model(doc.textmodel)
        self.textview.index = 0        # reset cursor; old position may be out of range
        self.textview.add_model(doc.charstyles)
        self.textview.add_model(doc.liststyles)
        self.textview.add_model(doc.basestyles)
        self.textview.add_model(doc)
        self.inspector.basestyles = doc.basestyles
        self.inspector.basestyle.set_stylesheet(doc.basestyles)
        self.document_settings.model = doc
        self.document_settings._refresh()

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
        self._update_title()

    def undo_changed(self, *args):
        wx.CallAfter(self._update_undo_ui)

    def layout_progress_start(self, view):
        if view.builder.layout.is_finished:
            return
        total_chars = len(view.model) + 1
        self._progress_dlg = _LayoutProgressDlg(self, total_chars)
        self._progress_dlg.ShowModal()
        self._progress_dlg.Destroy()
        self._progress_dlg = None

    def layout_progress(self, view, n_pages, n_chars, total_chars):
        if n_chars >= total_chars:
            if self._progress_dlg:
                self._progress_dlg.EndModal(0)
            return
        if self._progress_dlg:
            self._progress_dlg.update(n_pages, n_chars, total_chars)

        

def demo_00():
    from einstein import get_einstein_model
    from .document import Document
    from .styles import testsheet

    app = wx.App(True)
    doc = Document()
    doc.textmodel = get_einstein_model()
    for name, style in testsheet.items():
        doc.basestyles.set(name, style)
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
    from moby import get_moby_styled
    from .document import Document
    from .styles import testsheet

    textmodel = get_moby_styled()


    app = wx.App(True)
    doc = Document()
    doc.textmodel = textmodel
    for name, style in testsheet.items():
        doc.basestyles.set(name, style)
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
