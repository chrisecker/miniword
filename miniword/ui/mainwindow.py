import os
import sys
import wx
from ..textmodel.viewbase import ViewBase
from .styleinspector import StyleInspector
from .settingsinspector import SettingsInspector
from ..texteditor.editor import TestEditor
from ..texteditor.textcanvas import TextCanvas
from ..layout.pagebuilder import PageBuilder
from ..layout.factory import Factory
from ..layout.cairodevice import CairoDevice
from ..core.styles import testsheet
from ..tables.table_panel import TablePanel
from .sidepanel import RightStrip, STRIP_W, PANEL_W
from .colours import colours
from .icons import ICONS_DIR
from .outlinepanel import OutlinePanel
from .searchtool import SearchPanel

from ..images import image_controllers  # registers controllers
from ..tables import table_controllers  # registers controllers



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


file_history = None


def get_file_history():
    global file_history
    if file_history is None:
        file_history = wx.FileHistory(9)
        config = wx.FileConfig(localFilename=_config_path())
        file_history.Load(config)
    return file_history


def save_file_history():
    config = wx.FileConfig(localFilename=_config_path())
    file_history.Save(config)
    config.Flush()


def _miniword_dir():
    if sys.platform == 'win32':
        base = os.environ.get('APPDATA', os.path.expanduser('~'))
    elif sys.platform == 'darwin':
        base = os.path.expanduser('~/Library/Application Support')
    else:
        base = os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
    return os.path.join(base, 'miniword')


def _config_path():
    d = _miniword_dir()
    os.makedirs(d, exist_ok=True)
    os.makedirs(os.path.join(d, "plugins"), exist_ok=True)
    return os.path.join(d, "config.ini")


def load_plugins():
    """Load plugins from an ordered list of directories; first file wins per name.

    Search order: user config dir, then built-in miniword/plugins/.
    Returns (tools_items, all_mods):
      tools_items: [(name, mod), ...] for modules with a run() function
      all_mods:    all successfully loaded modules
    """
    import glob
    import importlib.util

    _builtin = os.path.normpath(
        os.path.join(os.path.dirname(__file__), '..', 'plugins'))
    plugin_dirs = [os.path.join(_miniword_dir(), "plugins"), _builtin]

    seen = set()
    paths = []
    for d in plugin_dirs:
        for path in sorted(glob.glob(os.path.join(d, "*.py"))):
            name = os.path.basename(path)
            if name not in seen:
                seen.add(name)
                paths.append(path)

    tools_items = []
    all_mods = []
    for path in paths:
        try:
            mod_name = f"_mw_plugin_{os.path.splitext(os.path.basename(path))[0]}"
            if mod_name in sys.modules:
                mod = sys.modules[mod_name]
            else:
                spec = importlib.util.spec_from_file_location(mod_name, path)
                mod  = importlib.util.module_from_spec(spec)
                sys.modules[mod_name] = mod
                spec.loader.exec_module(mod)
        except Exception as e:
            print(f"Plugin error ({os.path.basename(path)}): {e}")
            continue
        all_mods.append(mod)
        if hasattr(mod, 'run'):
            tools_items.append((getattr(mod, 'name', os.path.basename(path)), mod))
    return tools_items, all_mods


# ---------------------------------------------------------------------------
# Preferences dialog
# ---------------------------------------------------------------------------

_UNIT_CHOICES = ["mm", "cm", "inch", "pt"]
_UNIT_LABELS  = {"layout": "Layout (margins, paper)", "typographic": "Typographic (spacing, indents)"}


class _PreferencesDialog(wx.Dialog):
    def __init__(self, parent, prefs, config):
        super().__init__(parent, title="Preferences", style=wx.DEFAULT_DIALOG_STYLE)
        self._prefs  = prefs
        self._config = config

        grid = wx.FlexGridSizer(cols=2, vgap=8, hgap=12)
        grid.AddGrowableCol(1)

        self._choices = {}
        for category, label in _UNIT_LABELS.items():
            grid.Add(wx.StaticText(self, label=label), 0, wx.ALIGN_CENTER_VERTICAL)
            ch = wx.Choice(self, choices=_UNIT_CHOICES)
            current = prefs.get_unit(category)
            if current in _UNIT_CHOICES:
                ch.SetSelection(_UNIT_CHOICES.index(current))
            grid.Add(ch, 0, wx.EXPAND)
            self._choices[category] = ch

        btn_sizer = self.CreateButtonSizer(wx.OK | wx.CANCEL)
        self.Bind(wx.EVT_BUTTON, self._on_ok, id=wx.ID_OK)

        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(grid,       0, wx.ALL | wx.EXPAND, 16)
        outer.Add(btn_sizer,  0, wx.ALIGN_RIGHT | wx.ALL, 8)
        self.SetSizerAndFit(outer)
        self.CentreOnParent()

    def _on_ok(self, event):
        for category, ch in self._choices.items():
            unit = _UNIT_CHOICES[ch.GetSelection()]
            self._prefs.set_unit(category, unit)
            self._config.set(f"{category}_unit", unit)
        event.Skip()


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class _FileDropTarget(wx.FileDropTarget):
    def __init__(self, frame):
        super().__init__()
        self._frame = frame

    def OnDropFiles(self, x, y, paths):
        from ..io import importexport
        for path in paths:
            try:
                doc = importexport.open_file(path)
            except Exception as e:
                wx.MessageBox(str(e), "Open", wx.OK | wx.ICON_ERROR, self._frame)
                continue
            frame = MainFrame(doc)
            frame._current_path = path
            frame._update_title()
            frame.Show()
            get_file_history().AddFileToHistory(path)
            save_file_history()
        return True


class MainFrame(wx.Frame, ViewBase):

    _progress_dlg = None
    _current_path = None

    def __init__(self, document):
        self.document = document
        wx.Frame.__init__(self, None, title="MiniWord")
        ViewBase.__init__(self)

        self.SetSize(self.FromDIP(wx.Size(1400, 700)))
        self.SetMinSize(self.FromDIP(wx.Size(800, 480)))
        logo_svg = str(ICONS_DIR / "miniword.svg")
        bundle = wx.IconBundle()
        for size in (16, 32, 48, 64):
            bmp = wx.BitmapBundle.FromSVGFile(logo_svg, (size, size))
            bundle.AddIcon(wx.Icon(bmp.GetBitmap(wx.Size(size, size))))
        self.SetIcons(bundle)
        self.SetName("miniword")
        self._build_menu()
        self._load_plugins()
        self._build_layout()
        self._update_title()
        self.Centre()
        self.SetDropTarget(_FileDropTarget(self))

    def _load_plugins(self):
        self._plugin_tools, self._plugin_mods = load_plugins()
        self._register_plugin_menus()

    def _register_plugin_menus(self):
        bar = self.GetMenuBar()
        if self._plugin_tools:
            tools_menu = wx.Menu()
            bar.Insert(bar.GetMenuCount() - 1, tools_menu, "&Tools")
            for name, mod in self._plugin_tools:
                item_id = wx.NewIdRef()
                tools_menu.Append(item_id, name)
                self.Bind(wx.EVT_MENU, lambda evt, m=mod: m.run(self), id=item_id)
        for mod in self._plugin_mods:
            if not hasattr(mod, 'get_menus'):
                continue
            for menu_name, items in mod.get_menus(self.document):
                menu = wx.Menu()
                bar.Insert(bar.GetMenuCount() - 1, menu, menu_name)
                for label, handler in items:
                    item_id = wx.NewIdRef()
                    menu.Append(item_id, label)
                    self.Bind(wx.EVT_MENU, lambda evt, h=handler: h(self), id=item_id)

    def _build_menu(self):
        bar = wx.MenuBar()

        file_menu = wx.Menu()
        file_menu.Append(wx.ID_NEW,    "&New\tCtrl+N")
        file_menu.Append(wx.ID_OPEN,   "&Open\tCtrl+O")
        self._recent_menu = wx.Menu()
        file_menu.AppendSubMenu(self._recent_menu, "Open &Recent")
        fh = get_file_history()
        fh.UseMenu(self._recent_menu)
        fh.AddFilesToMenu(self._recent_menu)
        self.Bind(wx.EVT_MENU_RANGE, self._on_recent_file,
                  id=wx.ID_FILE1, id2=wx.ID_FILE9)
        self._id_import = wx.NewIdRef()
        file_menu.Append(self._id_import, "&Import…")
        file_menu.AppendSeparator()
        file_menu.Append(wx.ID_SAVE,   "&Save\tCtrl+S")
        file_menu.Append(wx.ID_SAVEAS, "Save &As…\tCtrl+Shift+S")
        self._id_reload = wx.NewIdRef()
        self._mi_reload = file_menu.Append(self._id_reload, "&Reload\tCtrl+R")
        file_menu.AppendSeparator()
        self._id_export_pdf = wx.NewIdRef()
        file_menu.Append(self._id_export_pdf, "Export as &PDF…\tCtrl+Shift+E")
        self._id_export = wx.NewIdRef()
        file_menu.Append(self._id_export, "E&xport…")
        file_menu.Append(wx.ID_PRINT, "&Print…\tCtrl+P")
        file_menu.AppendSeparator()
        file_menu.Append(wx.ID_CLOSE, "&Close Window\tCtrl+W")
        file_menu.Append(wx.ID_EXIT,  "E&xit\tCtrl+Q")
        bar.Append(file_menu, "&File")
        self.Bind(wx.EVT_MENU, self._on_new,        id=wx.ID_NEW)
        self.Bind(wx.EVT_MENU, self._on_open,       id=wx.ID_OPEN)
        self.Bind(wx.EVT_MENU, self._on_import,     id=self._id_import)
        self.Bind(wx.EVT_MENU, self._on_save,       id=wx.ID_SAVE)
        self.Bind(wx.EVT_MENU, self._on_saveas,     id=wx.ID_SAVEAS)
        self.Bind(wx.EVT_MENU, self._on_reload,     id=self._id_reload)
        self.Bind(wx.EVT_MENU, self._on_export_pdf, id=self._id_export_pdf)
        self.Bind(wx.EVT_MENU, self._on_export,     id=self._id_export)
        self.Bind(wx.EVT_MENU, self._on_print,      id=wx.ID_PRINT)
        self.Bind(wx.EVT_MENU, lambda _: self.Close(), id=wx.ID_CLOSE)
        self.Bind(wx.EVT_MENU, lambda _: self.Close(), id=wx.ID_EXIT)
        self.Bind(wx.EVT_CLOSE, self._on_close)

        edit_menu = wx.Menu()
        self.undo_item = edit_menu.Append(wx.ID_UNDO, "&Undo\tCtrl+Z")
        self.redo_item = edit_menu.Append(wx.ID_REDO, "&Redo\tCtrl+Y")
        edit_menu.AppendSeparator()
        edit_menu.Append(wx.ID_CUT,   "Cu&t\tCtrl+X")
        edit_menu.Append(wx.ID_COPY,  "&Copy\tCtrl+C")
        edit_menu.Append(wx.ID_PASTE, "&Paste\tCtrl+V")
        edit_menu.AppendSeparator()
        edit_menu.Append(wx.ID_FIND,    "&Find && Replace…\tCtrl+F")
        edit_menu.AppendSeparator()
        edit_menu.Append(wx.ID_PREFERENCES, "&Preferences…")
        bar.Append(edit_menu, "&Edit")
        self.Bind(wx.EVT_MENU, lambda _: self.editor.undo(),  id=wx.ID_UNDO)
        self.Bind(wx.EVT_MENU, lambda _: self.editor.redo(),  id=wx.ID_REDO)
        self.Bind(wx.EVT_MENU, lambda _: self.editor.controller.handle_action('cut', False),   id=wx.ID_CUT)
        self.Bind(wx.EVT_MENU, lambda _: self.editor.controller.handle_action('copy', False),  id=wx.ID_COPY)
        self.Bind(wx.EVT_MENU, lambda _: self.editor.controller.handle_action('paste', False), id=wx.ID_PASTE)
        self.Bind(wx.EVT_MENU, self._on_find,        id=wx.ID_FIND)
        self.Bind(wx.EVT_MENU, self._on_preferences, id=wx.ID_PREFERENCES)

        self._id_zoom_fit_w = wx.NewIdRef()
        self._id_zoom_fit_p = wx.NewIdRef()
        view_menu = wx.Menu()
        view_menu.Append(wx.ID_ZOOM_IN,       "Zoom &In\tCtrl++")
        view_menu.Append(wx.ID_ZOOM_OUT,      "Zoom &Out\tCtrl+-")
        view_menu.Append(wx.ID_ZOOM_100,      "&Actual Size\tCtrl+0")
        view_menu.Append(self._id_zoom_fit_w, "Fit to &Text Width\tCtrl+1")
        view_menu.Append(self._id_zoom_fit_p, "Fit to &Page\tCtrl+2")
        view_menu.AppendSeparator()
        self._mi_panel     = view_menu.AppendCheckItem(wx.ID_ANY, "Inspector\tCtrl+I")
        self._mi_two_page  = view_menu.AppendCheckItem(wx.ID_ANY, "Two-page view")
        bar.Append(view_menu, "&View")
        self.Bind(wx.EVT_MENU, lambda _: self.canvas.step_zoom(self.canvas.zoom_factor),       id=wx.ID_ZOOM_IN)
        self.Bind(wx.EVT_MENU, lambda _: self.canvas.step_zoom(1 / self.canvas.zoom_factor),   id=wx.ID_ZOOM_OUT)
        self.Bind(wx.EVT_MENU, lambda _: self.canvas.set_zoom(1.0),                            id=wx.ID_ZOOM_100)
        self.Bind(wx.EVT_MENU, lambda _: self._zoom_fit_width(),  id=self._id_zoom_fit_w)
        self.Bind(wx.EVT_MENU, lambda _: self._zoom_fit_page(),   id=self._id_zoom_fit_p)
        self.Bind(wx.EVT_MENU, self._on_menu_inspector, self._mi_panel)
        self.Bind(wx.EVT_MENU, self._on_two_page, self._mi_two_page)

        help_menu = wx.Menu()
        help_menu.Append(wx.ID_ABOUT, "&About MiniWord…")
        self.Bind(wx.EVT_MENU, self._on_about, id=wx.ID_ABOUT)
        bar.Append(help_menu, "&Help")

        from ..layout import pagebuilder as _pagebuilder
        if _pagebuilder.DEBUG:
            self._id_debug_console = wx.NewIdRef()
            self._id_debug_dump    = wx.NewIdRef()
            debug_menu = wx.Menu()
            self._id_debug_txl     = wx.NewIdRef()
            self._id_debug_boxes   = wx.NewIdRef()
            debug_menu.Append(self._id_debug_console, "Open Python console")
            debug_menu.Append(self._id_debug_dump,    "Dump texel tree")
            debug_menu.Append(self._id_debug_txl,     "Dump TXL")
            debug_menu.Append(self._id_debug_boxes,   "Dump box tree")
            bar.Append(debug_menu, "&Debug")
            self.Bind(wx.EVT_MENU, self._on_debug_console, id=self._id_debug_console)
            self.Bind(wx.EVT_MENU, self._on_debug_dump,    id=self._id_debug_dump)
            self.Bind(wx.EVT_MENU, self._on_debug_txl,     id=self._id_debug_txl)
            self.Bind(wx.EVT_MENU, self._on_debug_boxes,   id=self._id_debug_boxes)

        self.SetMenuBar(bar)

    def _create_editor_canvas(self):
        factory = Factory(testsheet, device=CairoDevice())
        factory.blobs = self.document.blobs
        builder = PageBuilder(self.document.textmodel, factory)
        builder.rebuild()
        builder.assure_index(len(self.document.textmodel))
        self.editor = TestEditor(self.document.textmodel)
        self.canvas = TextCanvas(
            self._base, self.document.textmodel, builder, self.editor)
        self.editor.canvas = self.canvas
        colours.set(self.canvas, 'BackgroundColour', 'CanvasBg')
        self.editor.add_view(self)

    def _build_inspector_panels(self):
        self._inspector_book = wx.Simplebook(self._base)
        colours.set(self._inspector_book, 'BackgroundColour', 'BTNFACE')
        self._inspector_pages = {}
        self.inspector = StyleInspector(self._inspector_book, self.editor, self.document.basestyles)
        self.document_settings = SettingsInspector(self._inspector_book, self.document)
        self.table_panel = TablePanel(self._inspector_book, self.editor)
        self._search_panel = SearchPanel(self._inspector_book, self.editor)
        self._outline_panel = OutlinePanel(self._inspector_book, self.document, self.editor)
        for key, panel in [
            ("style",    self.inspector),
            ("settings", self.document_settings),
            ("table",    self.table_panel),
            ("search",   self._search_panel),
            ("outline",  self._outline_panel),
        ]:
            idx = self._inspector_book.GetPageCount()
            self._inspector_book.AddPage(panel, "")
            self._inspector_pages[key] = idx
        self._inspector_book.Hide()

    def _build_layout(self):
        self._base = wx.Panel(self)
        colours.set(self._base, 'BackgroundColour', 'CanvasBg')
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(self._base, 1, wx.EXPAND)
        self.SetSizer(outer)

        self._create_editor_canvas()
        self._build_inspector_panels()
        self._panel_key = None

        self._build_strip()

        self._base.Bind(wx.EVT_SIZE, lambda e: (e.Skip(), self._layout()))

        self.Bind(wx.EVT_DPI_CHANGED, self._on_dpi_changed)
        self.Bind(wx.EVT_DISPLAY_CHANGED, self._on_dpi_changed)

        wx.CallAfter(self._layout)

    def _on_panel_toggle(self, key):
        book = self._inspector_book
        if key is None:
            self._panel_key = None
            book.Hide()             
        else:
            self._panel_key = key
            pageno = self._inspector_pages[key]
            book.SetSelection(pageno)
            book.Show()
            book.Raise()
            page = book.GetPage(pageno)
            page.update_visible()
        # update menu item            
        self._mi_panel.Check(key is not None)
        self._layout()

    def _on_preferences(self, _):
        from ..core.config import get_config
        from .unitentry import LengthInput
        dlg = _PreferencesDialog(self, LengthInput.prefs, get_config())
        dlg.ShowModal()
        dlg.Destroy()

    def _on_about(self, _):
        from importlib.metadata import version, PackageNotFoundError
        try:
            ver = version("miniword")
        except PackageNotFoundError:
            ver = "-"

        dlg = wx.Dialog(self, title="About MiniWord")
        logo_bmp = wx.StaticBitmap(dlg,
            bitmap=wx.BitmapBundle.FromSVGFile(
                str(ICONS_DIR / "miniword.svg"), (64, 64)
            ).GetBitmap(wx.Size(64, 64)))
        name_lbl = wx.StaticText(dlg, label="MiniWord")
        name_lbl.SetFont(name_lbl.GetFont().Bold().Scaled(1.4))
        info_lbl = wx.StaticText(dlg,
            label=f"Version {ver}\n\nCopyright \u00a9 2025 C. Ecker\nLicense: LGPL v3")
        ok_btn = wx.Button(dlg, wx.ID_OK, label="OK")
        ok_btn.SetDefault()

        text_sizer = wx.BoxSizer(wx.VERTICAL)
        text_sizer.Add(name_lbl, 0, wx.BOTTOM, 6)
        text_sizer.Add(info_lbl, 0)

        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(logo_bmp, 0, wx.RIGHT | wx.ALIGN_TOP, 16)
        row.Add(text_sizer, 0, wx.ALIGN_CENTER_VERTICAL)

        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(row,    0, wx.ALL, 20)
        outer.Add(ok_btn, 0, wx.ALIGN_CENTER | wx.BOTTOM, 16)
        dlg.SetSizerAndFit(outer)
        dlg.ShowModal()
        dlg.Destroy()

    def _on_menu_inspector(self, _):
        if self._mi_panel.IsChecked():
            self._panel_key = "style"
            self._inspector_book.SetSelection(self._inspector_pages["style"])
            self._inspector_book.Show()
            self._inspector_book.Raise()
            self._strip.activate("style")
        else:
            self._panel_key = None
            self._inspector_book.Hide()
            self._strip.deactivate()
        self._layout()

    def _on_two_page(self, _):
        pass # XXX TwoPageLayout not yet adapted to flow-based layout

    def _on_find(self, _):
        self.show_right_panel("search")

    def _zoom_fit_width(self):
        layout = self.canvas.layout
        cw = self.canvas.GetClientSize()[0]
        if layout.width > 0 and cw > 0:
            self.canvas.set_zoom(cw / layout.width)

    def _zoom_fit_page(self):
        tv = self.canvas
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

    def _layout(self):
        w, h = self._base.GetClientSize()
        if w <= 0 or h <= 0:
            return
        strip_w = self.FromDIP(STRIP_W)
        panel_w = self.FromDIP(PANEL_W) if self._panel_key is not None else 0
        text_w  = w - strip_w - panel_w

        self.canvas.SetPosition((0, 0))
        self.canvas.SetSize((text_w, h))

        self._strip.SetPosition((w - strip_w, 0))
        self._strip.SetSize((strip_w, h))

        if self._panel_key is not None:
            self._inspector_book.SetPosition((text_w, 0))
            self._inspector_book.SetSize((panel_w, h))

        self._base.Refresh()

    def _build_strip(self):
        self._strip = RightStrip(self._base, [
            ("outline",  "Outline"),
            ("style",    "Styles"),
            ("search",   "Search"),
            ("table",    "Table"),
            ("settings", "Settings"),
        ], self._on_panel_toggle)

    def _on_dpi_changed(self, event):
        self._build_menu()
        self._register_plugin_menus()
        active_key = self._strip.active_btn._key if self._strip.active_btn else None
        self._strip.Destroy()
        self._build_strip()
        if active_key:
            self._strip.activate(active_key)
        self.canvas.Refresh()
        self._layout()
        self.Refresh()
        event.Skip()

    def _update_title(self):
        name = os.path.basename(self._current_path) if self._current_path else "Untitled"
        dirty = hasattr(self, 'editor') and self.editor.undocount() > 0
        suffix = ' *' if dirty else ''
        self.SetTitle("MiniWord — " + name + suffix)
        if hasattr(self, '_mi_reload'):
            self._mi_reload.Enable(bool(self._current_path))

    def _on_close(self, event):
        if hasattr(self, 'editor') and self.editor.undocount() > 0:
            dlg = wx.MessageDialog(
                self,
                'There are unsaved changes.',
                'Unsaved Changes',
                wx.YES_NO | wx.CANCEL | wx.YES_DEFAULT | wx.ICON_WARNING,
            )
            dlg.SetYesNoCancelLabels("Save", "Discard", "Cancel")
            result = dlg.ShowModal()
            dlg.Destroy()
            if result == wx.ID_YES:
                self._on_save(event)
                if self.editor.undocount() > 0:
                    event.Veto()
                    return
            elif result == wx.ID_CANCEL:
                event.Veto()
                return
        builder = getattr(getattr(self, 'canvas', None), 'builder', None)
        if builder is not None:
            builder.generator = None
            builder._layout.is_finished = True  # stop buildto_y immediately
        get_file_history().RemoveMenu(self._recent_menu)
        event.Skip()

    def _on_new(self, event):
        from ..core.document import Document
        frame = MainFrame(Document())
        frame.Show()

    def _on_open(self, event):
        from ..io import importexport
        with wx.FileDialog(
            self, "Open",
            wildcard=importexport.open_wildcard(),
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            path = dlg.GetPath()
        try:
            doc = importexport.open_file(path)
        except Exception as e:
            wx.MessageBox(str(e), "Open", wx.OK | wx.ICON_ERROR, self)
            return
        frame = MainFrame(doc)
        frame._current_path = path
        frame._update_title()
        frame.Show()
        get_file_history().AddFileToHistory(path)
        save_file_history()

    def _on_recent_file(self, event):
        idx = event.GetId() - wx.ID_FILE1
        fh = get_file_history()
        path = fh.GetHistoryFile(idx)
        from ..io import importexport
        try:
            doc = importexport.open_file(path)
        except Exception as e:
            wx.MessageBox(str(e), "Open Recent", wx.OK | wx.ICON_ERROR, self)
            fh.RemoveFileFromHistory(idx)
            save_file_history()
            return
        frame = MainFrame(doc)
        frame._current_path = path
        frame._update_title()
        frame.Show()
        fh.AddFileToHistory(path)
        save_file_history()

    def _on_import(self, event):
        from ..io import importexport
        with wx.FileDialog(
            self, "Import",
            wildcard=importexport.import_wildcard(),
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            path = dlg.GetPath()
        try:
            doc = importexport.open_file(path)
        except Exception as e:
            wx.MessageBox(str(e), "Import", wx.OK | wx.ICON_ERROR, self)
            return
        frame = MainFrame(doc)
        frame.Show()
        get_file_history().AddFileToHistory(path)
        save_file_history()

    def _on_export(self, event):
        from ..io import importexport
        with wx.FileDialog(
            self, "Export",
            defaultDir=self._doc_dir(),
            wildcard=importexport.export_wildcard(),
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        ) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            path = dlg.GetPath()
            if not os.path.splitext(path)[1]:
                default = importexport.export_default_ext(dlg.GetFilterIndex())
                if default:
                    path += '.' + default
        fn = importexport.find_export_filter(path)
        if fn is None:
            wx.MessageBox("No export filter for this file type.",
                          "Export", wx.OK | wx.ICON_ERROR, self)
            return
        warnings = importexport.check_export(path, self.document)
        if warnings and not self._confirm_lossy_save(path, warnings):
            return
        fn(self.document, path)
        # NOTE: _current_path and home_format are NOT updated — pure export

    def _on_save(self, event):
        if not self._current_path:
            self._on_saveas(event)
            return
        self._do_save(self._current_path)

    def _doc_dir(self):
        return os.path.dirname(self._current_path) if self._current_path else ''

    def _on_saveas(self, event):
        from ..io import importexport
        with wx.FileDialog(
            self, "Save As",
            defaultDir=self._doc_dir(),
            wildcard=importexport.saveas_wildcard(),
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        ) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            path = dlg.GetPath()
            if not os.path.splitext(path)[1]:
                default = importexport.saveas_default_ext(dlg.GetFilterIndex())
                if default:
                    path += '.' + default
        ext = os.path.splitext(path)[1].lstrip('.').lower()
        self.document.home_format = ext if ext != 'txl' else 'txl'
        self._current_path = path
        self._do_save(path)

    def _do_save(self, path):
        """Save to path respecting doc.home_format. Warns if lossy."""
        from ..io import importexport
        if getattr(self.document, 'home_format', 'txl') == 'txl':
            self.document.save(path)
        else:
            warnings = importexport.check_export(path, self.document)
            if warnings and not self._confirm_lossy_save(path, warnings):
                return
            fn = importexport.find_export_filter(path)
            if fn is None:
                wx.MessageBox("No export filter for this format.",
                              "Save", wx.OK | wx.ICON_ERROR, self)
                return
            fn(self.document, path)
        self.editor.clear_undo()
        self._update_title()
        get_file_history().AddFileToHistory(path)
        save_file_history()

    def _confirm_lossy_save(self, path, warnings):
        items = '\n'.join('\u2022 ' + w for w in warnings)
        msg = ("Saving as '%s' will lose:\n\n%s\n\nSave anyway?"
               % (os.path.basename(path), items))
        dlg = wx.MessageDialog(self, msg, "Format Warning",
                               wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING)
        result = dlg.ShowModal()
        dlg.Destroy()
        return result == wx.ID_YES

    def _on_reload(self, event):
        if self.editor.undocount() > 0:
            wx.MessageBox("Document has been modified. Please save your changes first.",
                          "Reload", wx.OK | wx.ICON_WARNING, self)
            return
        index = self.editor.index
        from ..core.document import Document
        doc = Document.load(self._current_path)
        self.replace_document(doc)
        self.editor.index = min(index, len(self.editor.root))
        self._update_title()

    def _on_print(self, event):
        import tempfile, subprocess
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            path = f.name
        self._export_pdf(path)
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.run(["open", path])
        else:
            subprocess.run(["xdg-open", path])

    def _on_export_pdf(self, event):
        with wx.FileDialog(
            self, "Export as PDF",
            defaultDir=self._doc_dir(),
            wildcard="PDF files (*.pdf)|*.pdf|All files (*.*)|*.*",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        ) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            path = dlg.GetPath()
            if not os.path.splitext(path)[1] and dlg.GetFilterIndex() == 0:
                path += '.pdf'
        self._export_pdf(path)

    def _export_pdf(self, path):
        # XXX PDF export not yet adapted to the new Editor/Canvas API.
        wx.MessageBox("PDF export is not yet implemented.",
                      "Export PDF", wx.OK | wx.ICON_INFORMATION, self)

    def replace_document(self, doc):
        self.canvas.Destroy()
        self._inspector_book.Destroy()
        self.document = doc
        self._create_editor_canvas()
        self._build_inspector_panels()
        self._panel_key = None
        self._layout()

    def show_right_panel(self, key):
        self._strip.activate(key)
        self._on_panel_toggle(key)

    def show_left_panel(self, key):
        self.show_right_panel(key)

    def _update_undo_ui(self):
        if not hasattr(self, "editor"):
            return
        self.undo_item.Enable(self.editor.undocount() > 0)
        self.redo_item.Enable(self.editor.redocount() > 0)
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


    def _get_debug_range(self):
        if self.editor.has_selection():
            return sorted(self.editor.selection)
        return None

    def _on_debug_console(self, _):
        from ..wxtextview import testing
        l = locals()
        l.update(globals())
        testing.pyshell(l)

    def _get_debug_texel(self):
        model = self.editor.root
        r = self._get_debug_range()
        if r:
            return model.copy(*r).texel
        return model.texel

    def _on_debug_dump(self, _):
        from ..textmodel.texeltree import dump
        dump(self._get_debug_texel())

    def _on_debug_txl(self, _):
        from ..io.texeltreeformat import serialize
        print(serialize(self._get_debug_texel()))

    def _on_debug_boxes(self, _):
        layout = self.canvas.builder.layout
        r = self._get_debug_range()
        if r:
            i1, i2 = r
            def _dump(box, i=0, x=0, y=0, indent=0):
                for j1, j2, x1, y1, child in box.iter_boxes(i, x, y):
                    if j2 > i1 and j1 < i2:
                        child.dump_boxes(j1, x1, y1, indent)
            _dump(layout)
        else:
            layout.dump_boxes(0, 0, 0)


def demo_00():
    from einstein import get_einstein_model
    from ..core.document import Document
    from ..core.styles import testsheet

    app = wx.App(True)
    doc = Document()
    doc.textmodel = get_einstein_model()
    for name, style in testsheet.items():
        doc.basestyles.set(name, style)
    frame = MainFrame(doc)
    frame.Show()

    if 1:
        editor = frame.editor
        canvas = frame.canvas

        from . import testing
        l = locals()
        l.update(globals())
        testing.pyshell(l)

    app.MainLoop()


def demo_01():
    from moby import get_moby_styled
    from ..core.document import Document
    from ..core.styles import testsheet

    textmodel = get_moby_styled()

    app = wx.App(True)
    doc = Document()
    doc.textmodel = textmodel
    for name, style in testsheet.items():
        doc.basestyles.set(name, style)
    frame = MainFrame(doc)
    frame.Show()

    if 1:
        editor = frame.editor
        canvas = frame.canvas

        from . import testing
        l = locals()
        l.update(globals())
        testing.pyshell(l)

    app.MainLoop()


def test_00():
    "open MainFrame, type text, verify document content, close"
    from ..core.document import Document
    import wx

    app = wx.App()
    doc = Document()
    frame = MainFrame(doc)
    frame.Show()
    app.Yield()

    editor = frame.editor
    for ch in "Hello":
        editor.insert_text(ch)
    app.Yield()

    text = doc.textmodel.get_text()
    assert "Hello" in text, repr(text)

    frame.Destroy()
    app.Yield()


def test_01():
    "cursor inside table installs CursorController, outside removes it"
    from ..core.document import Document
    from ..tables.tables import empty_table
    from ..tables.table_controllers import CursorController
    import wx

    app = wx.App()
    doc = Document()
    frame = MainFrame(doc)
    frame.Show()
    app.Yield()

    editor = frame.editor
    editor.insert_texel(empty_table(2, 2))
    editor.insert_text("X") # content after the table
    app.Yield()

    # cursor inside table → CursorController
    editor.index = 1
    assert isinstance(editor.controller, CursorController), type(editor.controller)

    # cursor outside table → NullController
    editor.index = 6 # on the "X" after the table
    assert editor.controller.is_null, type(editor.controller)

    frame.Destroy()
    app.Yield()


def test_02():
    "rapid key events arrive in correct order"
    from ..core.document import Document
    import wx

    app = wx.App()
    doc = Document()
    frame = MainFrame(doc)
    frame.Show()
    app.Yield()

    class _FakeKeyEvent:
        def __init__(self, ch):
            self._ch = ch
        def GetKeyCode(self):    return ord(self._ch)
        def GetUnicodeKey(self): return ord(self._ch)
        def ControlDown(self):   return False
        def ShiftDown(self):     return False
        def AltDown(self):       return False
        def Skip(self):          pass

    canvas = frame.canvas
    word = "Hello"
    for ch in word:
        canvas.on_char(_FakeKeyEvent(ch))
        # no Yield between chars — simulates rapid typing

    app.Yield()

    text = doc.textmodel.get_text().rstrip('\n')
    assert text == word, repr(text)

    frame.Destroy()
    app.Yield()
