import wx
from .textmodel.viewbase import ViewBase
from .inspector import InspectorPanel
from .settingsinspector import SettingsInspector
from .documentview import DocumentView
from .image import Image, ImageInspector
from .ui.sidepanel import RightStrip, SearchBar, STRIP_W, PANEL_W, BG_CANVAS, BG_PANEL


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
        file_menu.Append(wx.ID_NEW,    "&New\tCtrl+N")
        file_menu.Append(wx.ID_OPEN,   "&Open\tCtrl+O")
        file_menu.Append(wx.ID_SAVE,   "&Save\tCtrl+S")
        file_menu.Append(wx.ID_SAVEAS, "Save &As…\tCtrl+Shift+S")
        file_menu.AppendSeparator()
        self._id_export_pdf = wx.NewIdRef()
        file_menu.Append(self._id_export_pdf, "Export as &PDF…\tCtrl+Shift+E")
        file_menu.AppendSeparator()
        file_menu.Append(wx.ID_CLOSE, "&Close Window\tCtrl+W")
        file_menu.Append(wx.ID_EXIT,  "E&xit\tCtrl+Q")
        bar.Append(file_menu, "&File")
        self.Bind(wx.EVT_MENU, self._on_new,        id=wx.ID_NEW)
        self.Bind(wx.EVT_MENU, self._on_open,       id=wx.ID_OPEN)
        self.Bind(wx.EVT_MENU, self._on_save,       id=wx.ID_SAVE)
        self.Bind(wx.EVT_MENU, self._on_saveas,     id=wx.ID_SAVEAS)
        self.Bind(wx.EVT_MENU, self._on_export_pdf, id=self._id_export_pdf)
        self.Bind(wx.EVT_MENU, lambda _: self.Close(), id=wx.ID_CLOSE)
        self.Bind(wx.EVT_MENU, lambda _: wx.GetApp().ExitMainLoop(), id=wx.ID_EXIT)

        edit_menu = wx.Menu()
        self.undo_item = edit_menu.Append(wx.ID_UNDO, "&Undo\tCtrl+Z")
        self.redo_item = edit_menu.Append(wx.ID_REDO, "&Redo\tCtrl+Y")
        edit_menu.AppendSeparator()
        edit_menu.Append(wx.ID_CUT,   "Cu&t\tCtrl+X")
        edit_menu.Append(wx.ID_COPY,  "&Copy\tCtrl+C")
        edit_menu.Append(wx.ID_PASTE, "&Paste\tCtrl+V")
        edit_menu.AppendSeparator()
        edit_menu.Append(wx.ID_FIND,    "&Find && Replace…\tCtrl+F")
        bar.Append(edit_menu, "&Edit")
        self.Bind(wx.EVT_MENU, lambda _: self.textview.cut(),   id=wx.ID_CUT)
        self.Bind(wx.EVT_MENU, lambda _: self.textview.copy(),  id=wx.ID_COPY)
        self.Bind(wx.EVT_MENU, lambda _: self.textview.paste(), id=wx.ID_PASTE)
        self.Bind(wx.EVT_MENU, self._on_find, id=wx.ID_FIND)

        self._id_zoom_fit_w = wx.NewIdRef()
        self._id_zoom_fit_p = wx.NewIdRef()
        view_menu = wx.Menu()
        view_menu.Append(wx.ID_ZOOM_IN,       "Zoom &In\tCtrl++")
        view_menu.Append(wx.ID_ZOOM_OUT,      "Zoom &Out\tCtrl+-")
        view_menu.Append(wx.ID_ZOOM_100,      "&Actual Size\tCtrl+0")
        view_menu.Append(self._id_zoom_fit_w, "Fit to &Text Width\tCtrl+1")
        view_menu.Append(self._id_zoom_fit_p, "Fit to &Page\tCtrl+2")
        view_menu.AppendSeparator()
        self._mi_panel = view_menu.AppendCheckItem(wx.ID_ANY, "Inspector\tCtrl+I")
        bar.Append(view_menu, "&View")
        self.Bind(wx.EVT_MENU, lambda _: self._zoom_step(1.15),  id=wx.ID_ZOOM_IN)
        self.Bind(wx.EVT_MENU, lambda _: self._zoom_step(1/1.15), id=wx.ID_ZOOM_OUT)
        self.Bind(wx.EVT_MENU, lambda _: self.textview.set_zoom(1.0), id=wx.ID_ZOOM_100)
        self.Bind(wx.EVT_MENU, lambda _: self._zoom_fit_width(),  id=self._id_zoom_fit_w)
        self.Bind(wx.EVT_MENU, lambda _: self._zoom_fit_page(),   id=self._id_zoom_fit_p)
        self.Bind(wx.EVT_MENU, self._on_menu_inspector, self._mi_panel)

        bar.Append(wx.Menu(), "&Help")
        self.SetMenuBar(bar)

    def _build_layout(self):
        self._base = wx.Panel(self)
        self._base.SetBackgroundColour(BG_CANVAS)
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(self._base, 1, wx.EXPAND)
        self.SetSizer(outer)

        self.textview = DocumentView(self._base, self.document)
        self.textview.SetBackgroundColour(BG_CANVAS)
        self.textview.add_view(self)

        # Inspector container
        self._inspector_book = wx.Simplebook(self._base)
        self._inspector_book.SetBackgroundColour(BG_PANEL)
        self._inspector_pages = {}

        self.inspector = InspectorPanel(
            self._inspector_book, self.textview, self.document.basestyles)
        self.document_settings = SettingsInspector(
            self._inspector_book, self.document)
        self.image_inspector = ImageInspector(
            self._inspector_book, self._on_image_insert, self._on_image_change)
        self.image_inspector.blobs = self.document.blobs

        from .searchtool import SearchPanel
        self._search_panel = SearchPanel(self._inspector_book, self.textview)

        for key, panel in [
            ("format",   self.inspector),
            ("settings", self.document_settings),
            ("image",    self.image_inspector),
            ("search",   self._search_panel),
        ]:
            idx = self._inspector_book.GetPageCount()
            self._inspector_book.AddPage(panel, "")
            self._inspector_pages[key] = idx

        self._inspector_book.Hide()
        self._panel_key = None

        self._strip = RightStrip(self._base, [
            ("format",   "Aa", "Styles"),
            ("search",   "⌕",  "Search"),
            ("image",    "⬜",  "Image"),
            ("settings", "≡",  "Settings"),
        ], self._on_panel_toggle)

        self._search_bar = SearchBar(self._base, self._close_search)
        self._search_bar.Hide()

        self._base.Bind(wx.EVT_SIZE, lambda e: (e.Skip(), self._layout()))
        wx.CallAfter(self._layout)

    def _on_panel_toggle(self, key):
        if key is None:
            self._panel_key = None
            self._inspector_book.Hide()
            self._mi_panel.Check(False)
        else:
            self._panel_key = key
            self._inspector_book.SetSelection(self._inspector_pages[key])
            self._inspector_book.Show()
            self._inspector_book.Raise()
            self._mi_panel.Check(True)
        self._layout()

    def _on_menu_inspector(self, _):
        if self._mi_panel.IsChecked():
            self._panel_key = "format"
            self._inspector_book.SetSelection(self._inspector_pages["format"])
            self._inspector_book.Show()
            self._inspector_book.Raise()
            self._strip.activate("format")
        else:
            self._panel_key = None
            self._inspector_book.Hide()
            self._strip.deactivate()
        self._layout()

    def _on_find(self, _):
        self.show_right_panel("search")

    def _zoom_step(self, factor):
        tv = self.textview
        new_zoom = max(tv.min_zoom, min(tv.max_zoom, tv.get_zoom() * factor))
        tv.set_zoom(new_zoom)

    def _zoom_fit_width(self):
        layout = self.textview.layout
        cw = self.textview.GetClientSize()[0]
        if layout.width > 0 and cw > 0:
            self.textview.set_zoom(cw / layout.width)

    def _zoom_fit_page(self):
        tv = self.textview
        layout = tv.layout
        cw, ch = tv.GetClientSize()
        if layout.width <= 0 or cw <= 0 or ch <= 0:
            return
        rx, ry = getattr(tv, '_scrollrate', (10, 10))
        _, sy = tv.GetViewStart()
        scroll_y = sy * ry / tv.get_zoom()
        page_h = layout.height  # fallback
        for _p1, _p2, _px, py, page in layout.iter_boxes(0, 0, 0):
            if py + page.height + page.depth >= scroll_y:
                page_h = page.height + page.depth
                break
        if page_h > 0:
            tv.set_zoom(min(cw / layout.width, ch / page_h))

    def _close_search(self):
        self._search_bar.Hide()
        self._layout()

    def _layout(self):
        w, h = self._base.GetClientSize()
        if w <= 0 or h <= 0:
            return
        search_h = 34 if self._search_bar.IsShown() else 0
        canvas_h = h - search_h
        canvas_w = w - STRIP_W

        panel_w = PANEL_W if self._panel_key is not None else 0
        text_w  = canvas_w - panel_w

        self.textview.SetPosition((0, 0))
        self.textview.SetSize((text_w, canvas_h))

        self._strip.SetPosition((w - STRIP_W, 0))
        self._strip.SetSize((STRIP_W, h))

        if self._panel_key is not None:
            self._inspector_book.SetPosition((text_w, 0))
            self._inspector_book.SetSize((PANEL_W, canvas_h))

        if self._search_bar.IsShown():
            self._search_bar.SetPosition((0, canvas_h))
            self._search_bar.SetSize((canvas_w, search_h))
            self._search_bar.Raise()

        self._base.Refresh()

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
        self.textview.document = doc
        self.textview.set_model(doc.textmodel)
        self.textview.index = 0
        self.textview.add_model(doc.charstyles)
        self.textview.add_model(doc.liststyles)
        self.textview.add_model(doc.basestyles)
        self.textview.add_model(doc)
        self.inspector.basestyles = doc.basestyles
        self.inspector.basestyle.set_stylesheet(doc.basestyles)
        self.document_settings.model = doc
        self.document_settings._refresh()
        self.image_inspector.blobs = doc.blobs
        self.image_inspector.clear()

    def show_right_panel(self, key):
        self._strip.activate(key)
        self._on_panel_toggle(key)

    def show_left_panel(self, key):
        self.show_right_panel(key)

    def _update_undo_ui(self):
        if not hasattr(self, "textview"):
            return
        self.undo_item.Enable(self.textview.undocount() > 0)
        self.redo_item.Enable(self.textview.redocount() > 0)
        self._update_title()

    def undo_changed(self, *args):
        wx.CallAfter(self._update_undo_ui)

    def index_changed(self, *args):
        wx.CallAfter(self._update_image_inspector)

    def _update_image_inspector(self):
        if not hasattr(self, 'textview'):
            return
        from .textmodel.textmodel import _get_texel
        index = self.textview.index
        model = self.textview.model
        try:
            texel = _get_texel(model.get_xtexel(), index)
        except (IndexError, AttributeError):
            texel = None
        if isinstance(texel, Image):
            self.image_inspector.refresh(texel, index)
            self.show_right_panel("image")
        else:
            self.image_inspector.clear()

    def _on_image_insert(self, blob_id):
        from .textmodel.texeltree import grouped
        from .pagegen import restartmemo_from_settings
        model = self.textview.model
        index = self.textview.index
        scale = 1.0
        blob = self.document.blobs.get(blob_id)
        load_image = getattr(self.textview.builder.device, 'load_image', None)
        if blob and load_image:
            _, src_w, src_h = load_image(blob)
            if src_w > 0:
                memo = restartmemo_from_settings(self.document.settings)
                avail_w = memo.geometry[0] - memo.border[1] - memo.border[3]
                if src_w > avail_w:
                    scale = avail_w / src_w
        img = Image(blob_id, scale)
        tmp = model.create_textmodel()
        tmp.texel = grouped([img])
        self.textview.insert(index, tmp)

    def _on_image_change(self, index, blob_id, scale, crop):
        from .textmodel.texeltree import grouped
        model = self.textview.model
        img = Image(blob_id, scale, crop)
        tmp = model.create_textmodel()
        tmp.texel = grouped([img])
        with self.textview.atomic():
            model.remove(index, index + 1)
            model.insert(index, tmp)

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
