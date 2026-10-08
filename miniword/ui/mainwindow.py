import os
import sys
import time
import wx
from ..textmodel.viewbase import ViewBase
from .styleinspector import StyleInspector
from .settingsinspector import SettingsInspector
from ..texteditor.editor import TwoFlowEditor
from ..texteditor.textcanvas import TextCanvas
from ..layout.pagebuilder import PageBuilder
from ..layout.rowfactory import Factory
from ..layout.cairodevice import CairoDevice
from ..tables.table_panel import TablePanel
from .sidepanel import RightStrip, STRIP_W, PANEL_W
from .colours import colours
from .messagebar import MessageBar
from .icons import ICONS_DIR, app_icon_bundle
from .outlinepanel import OutlinePanel
from .searchtool import SearchPanel
from .linkpanel import LinksPanel
from ..images import ImageInspector
from ..core.config import get_config
from ..core.document import Document
from ..hyphenation import system_language

from ..images import image_controllers  # registers controllers
from ..tables import table_controllers  # registers controllers



# ---------------------------------------------------------------------------
# Progress dialog
# ---------------------------------------------------------------------------

def with_bitmap(texel, png):
    """A pasted texel that is just one image, no text (e.g. 'Copy image'
    in a browser: HTML and a bitmap of the image): that image embedded
    with the bitmap png, its path kept as origin. Else texel unchanged -
    e.g. office programs add a picture of copied text."""
    from ..images.images import iter_images
    from ..images.imageio import content_of, pixel_size
    from ..textmodel.texeltree import get_text, grouped
    images = list(iter_images(texel))
    if len(images) != 1 \
            or get_text(texel).replace(images[0].text, '').strip():
        return texel
    image = images[0]
    shown, bitmap = pixel_size(content_of(image)), pixel_size(png)
    if shown and bitmap:  # as large as the image (a Hi-DPI bitmap: half)
        image = image.set_scale_x(shown[0] * image.scale_x / bitmap[0])
        image = image.set_scale_y(shown[1] * image.scale_y / bitmap[1])
    return grouped([image.set_content(png)])


def build_to(builder, y, parent, delay=0.3):
    """Build the pages down to y (e.g. the visible area after a rebuild);
    a progress window if that takes longer than delay seconds. Meanwhile
    all other windows are disabled (no input, no menus) and views don't
    paint, build or scroll (PageBuilder.busy). Returns whether the
    window was shown."""
    start, total, shown = time.time(), len(builder.model) + 1, []

    def progress():
        if not shown and time.time() - start >= delay:
            window = progress_window(parent)
            shown.append((window, wx.WindowDisabler(window)))
        if shown:
            shown[0][0].gauge.SetValue(100 * len(builder.layout) // total)
            wx.YieldIfNeeded()  # paints the window; input is disabled
    PageBuilder.busy = True
    try:
        builder.assure_y(y, progress)
    finally:
        PageBuilder.busy = False
        windows = [window for window, _ in shown]
        shown.clear()  # ends the disabler: the windows are enabled again
        for window in windows:
            window.Destroy()
    return bool(windows)


def progress_window(parent):
    """A small window 'Laying out document' with a gauge (0..100)."""
    window = wx.Frame(parent, title="Miniword", style=wx.CAPTION
                      | wx.FRAME_FLOAT_ON_PARENT | wx.FRAME_TOOL_WINDOW)
    panel = wx.Panel(window)
    sizer = wx.BoxSizer(wx.VERTICAL)
    sizer.Add(wx.StaticText(panel, label="Laying out document…"),
              0, wx.ALL, 12)
    window.gauge = wx.Gauge(panel, range=100, size=(300, 16))
    sizer.Add(window.gauge, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
    panel.SetSizer(sizer)
    window.SetClientSize(panel.GetBestSize())
    window.CentreOnParent()
    window.Show()
    return window


file_history = None


def get_file_history():
    global file_history
    if file_history is None:
        file_history = wx.FileHistory(9)
        config = wx.FileConfig(localFilename=_config_path())
        file_history.Load(config)
    return file_history


def _forget_menu(menu):
    """Take menu out of the file history (before it is destroyed)."""
    history = get_file_history()
    if menu in history.GetMenus():
        history.RemoveMenu(menu)


def save_file_history():
    config = wx.FileConfig(localFilename=_config_path())
    file_history.Save(config)
    config.Flush()


_last_dir = ''  # while the app runs: folder of the last file opened/saved


def last_dir():
    """Folder of the last document opened or saved ('' if none)."""
    return _last_dir


def remember_dir(path):
    """Make path's folder the one the file dialogs start in."""
    global _last_dir
    _last_dir = os.path.dirname(os.path.abspath(path))


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


def plugin_menu(frame, items):
    """A wx.Menu for a plugin's items: (label, handler), (label, handler,
    enabled), (label, [items]) for a submenu, None for a separator.
    handler(frame) runs the entry, enabled(frame) greys it out."""
    menu = wx.Menu()
    for item in items:
        if item is None:
            menu.AppendSeparator()
        elif isinstance(item[1], list):
            menu.AppendSubMenu(plugin_menu(frame, item[1]), item[0])
        else:
            item_id = menu.Append(wx.ID_ANY, item[0]).GetId()
            frame.Bind(wx.EVT_MENU, lambda e, h=item[1]: h(frame),
                       id=item_id)
            if len(item) > 2:
                frame.Bind(wx.EVT_UPDATE_UI,
                           lambda e, f=item[2]: e.Enable(f(frame)),
                           id=item_id)
    return menu


def load_plugins():
    """Load plugins from an ordered list of directories; first file wins per name.

    Search order: user config dir, then built-in miniword/plugins/.
    Returns (tools_items, all_mods):
      tools_items: [(name, mod), ...] for modules with a run() function
      all_mods:    all successfully loaded modules
    """
    import glob
    import importlib
    import importlib.util

    from ..core.respath import package_dir
    _builtin = str(package_dir() / 'plugins')
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
            stem = os.path.splitext(os.path.basename(path))[0]
            if os.path.dirname(os.path.abspath(path)) == os.path.abspath(_builtin):
                # Built-in plugins are regular package modules. Import them
                # by package name, not by file path, so they share module
                # identity with any `from miniword.plugins.X import ...`
                # done elsewhere in the codebase (e.g. htmlfilter.py imports
                # from mdfilter.py) -- otherwise the module, including its
                # side-effecting register_import/register_export calls,
                # would run a second time under a different sys.modules key.
                mod = importlib.import_module(f"miniword.plugins.{stem}")
            else:
                mod_name = f"_mw_plugin_{stem}"
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
        self.Bind(wx.EVT_BUTTON, self.on_ok, id=wx.ID_OK)

        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(grid,       0, wx.ALL | wx.EXPAND, 16)
        outer.Add(btn_sizer,  0, wx.ALIGN_RIGHT | wx.ALL, 8)
        self.SetSizerAndFit(outer)
        self.CentreOnParent()

    def on_ok(self, event):
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


def show_marks():
    """Show formatting marks? From the user's config, default yes."""
    return get_config().get('show_formatting_marks') is not False


def new_document(locale_name=None):
    """A new document in the system language (for hyphenation), or that
    of locale_name, e.g. 'de_DE'."""
    if locale_name is None:
        locale_name = wx.Locale.GetLanguageCanonicalName(
            wx.Locale.GetSystemLanguage())
    document = Document()
    document.set_setting('language', system_language(locale_name))
    return document


def window_rect(saved, areas, max_w):
    """Window rect (x, y, w, h): the saved one if it starts on one of the
    displays' work areas (shrunk to fit it), else 90% of the first area,
    at most max_w wide, centred."""
    if saved is not None:
        x, y, w, h = saved
        for ax, ay, aw, ah in areas:
            if ax <= x < ax + aw and ay <= y < ay + ah:
                return x, y, min(w, ax + aw - x), min(h, ay + ah - y)
    ax, ay, aw, ah = areas[0]
    w, h = min(max_w, int(aw * 0.9)), int(ah * 0.9)
    return ax + (aw - w) // 2, ay + (ah - h) // 2, w, h


class MainFrame(wx.Frame, ViewBase):

    _path = None
    _debug_menu = None

    @property
    def _current_path(self):
        return self._path

    @_current_path.setter
    def _current_path(self, path):
        """The document's file; the document gets its folder (the image
        panel shows paths relative to it)."""
        self._path = path
        self.document.folder = self._doc_dir()
        self.image_inspector.update()
        self.check_external_images()

    def _fit_loaded(self, urls):
        """Images just loaded from urls, now of known size: too large ones
        made smaller (fit_to_page), in one undo step. The cursor stays."""
        from ..images.images import Image, fit_to_page
        from ..textmodel.utils import iter_leafes
        editor = self.editor
        if getattr(editor, 'flow', 0) != 0:
            return  # the images are replaced in the main text
        root, index = self.document.textmodel.texel, editor.index
        with editor.atomic():
            for i1, i2, texel in list(iter_leafes(root, 0, True)):
                if not isinstance(texel, Image) or texel.path not in urls:
                    continue
                fitted = fit_to_page(texel, self.document.settings,
                                     (root, i1))
                if fitted is not texel:
                    editor.set_texel_attributes(
                        i1, texel, scale_x=fitted.scale_x,
                        scale_y=fitted.scale_y)
        editor.index = index

    def check_external_images(self):
        """Web images aren't loaded on opening (privacy, as in Word): a
        bar offers to load them."""
        from ..images.imageio import unloaded_urls
        if unloaded_urls(self.document.textmodel.texel):
            self.image_bar.show(
                "This document contains images from the web, not loaded "
                "to protect your privacy.",
                "Load external images", self.load_external_images)
        elif self.image_bar.IsShown():
            self.image_bar.close()

    def load_external_images(self):
        """Load the web images (bar button); failures stay in the bar."""
        from ..images.imageio import unloaded_urls, load_url, errors
        urls = unloaded_urls(self.document.textmodel.texel)
        with wx.BusyCursor():
            failed = [url for url in sorted(urls) if not load_url(url)]
        self._fit_loaded(urls - set(failed))
        self._rebuild()
        if failed:
            self.image_bar.show("%d of %d images not loaded: %s" % (
                len(failed), len(urls), errors[failed[0]]))
        else:
            self.image_bar.close()
    _secret_armed = False
    _secret_buffer = ''
    _markdown_preview = None

    def __init__(self, document):
        self.document = document
        wx.Frame.__init__(self, None, title="MiniWord")
        ViewBase.__init__(self)
        self.Bind(wx.EVT_CHAR_HOOK, self.on_secret_key)

        self.SetMinSize(self.FromDIP(wx.Size(800, 480)))
        self.SetIcons(app_icon_bundle())
        self.SetName("miniword")
        self._build_menu()
        self._load_plugins()
        self._build_layout()
        self._update_title()
        self._restore_geometry()
        self.SetDropTarget(_FileDropTarget(self))

    def _load_plugins(self):
        self._plugin_tools, self._plugin_mods = load_plugins()
        self._register_plugin_menus()

    def _register_plugin_menus(self):
        from ..io.importexport import paste_as_handlers
        bar = self.GetMenuBar()
        edit = bar.GetMenu(bar.FindMenu('Edit'))
        k = [i.GetId() for i in edit.GetMenuItems()].index(wx.ID_PASTE) + 1
        for label, handler in paste_as_handlers():  # 'Paste from ...'
            item = edit.Insert(k, wx.ID_ANY, label)
            self.Bind(wx.EVT_MENU, lambda e, h=handler: self.paste_as(h),
                      item)
            k += 1
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
                bar.Insert(bar.GetMenuCount() - 1,
                           plugin_menu(self, items), menu_name)

    def _add_actions(self, menu, items):
        """Menu entries (label, action) for the editor's actions; None: a
        separator."""
        for entry in items:
            if entry is None:
                menu.AppendSeparator()
                continue
            item = menu.Append(wx.ID_ANY, entry[0])
            self.Bind(wx.EVT_MENU, lambda _, a=entry[1]:
                      self.editor.controller.handle_action(a, False), item)

    def _build_menu(self):
        bar = wx.MenuBar()

        file_menu = wx.Menu()
        file_menu.Append(wx.ID_NEW,    "&New\tCtrl+N")
        file_menu.Append(wx.ID_OPEN,   "&Open\tCtrl+O")
        if hasattr(self, '_recent_menu'):  # a rebuild (DPI change)
            _forget_menu(self._recent_menu)
        self._recent_menu = wx.Menu()
        file_menu.AppendSubMenu(self._recent_menu, "Open &Recent")
        fh = get_file_history()
        fh.UseMenu(self._recent_menu)
        fh.AddFilesToMenu(self._recent_menu)
        self.Bind(wx.EVT_MENU_RANGE, self.on_recent_file,
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
        self._id_show_markdown = wx.NewIdRef()
        file_menu.Append(self._id_show_markdown, "Show &Markdown")
        file_menu.Append(wx.ID_PRINT, "&Print…\tCtrl+P")
        file_menu.AppendSeparator()
        file_menu.Append(wx.ID_CLOSE, "&Close Window\tCtrl+W")
        file_menu.Append(wx.ID_EXIT,  "E&xit\tCtrl+Q")
        bar.Append(file_menu, "&File")
        self.Bind(wx.EVT_MENU, lambda _: self.new(),            id=wx.ID_NEW)
        self.Bind(wx.EVT_MENU, lambda _: self.open_document(),  id=wx.ID_OPEN)
        self.Bind(wx.EVT_MENU, lambda _: self.import_document(), id=self._id_import)
        self.Bind(wx.EVT_MENU, lambda _: self.save(),           id=wx.ID_SAVE)
        self.Bind(wx.EVT_MENU, lambda _: self.save_as(),        id=wx.ID_SAVEAS)
        self.Bind(wx.EVT_MENU, lambda _: self.reload(),         id=self._id_reload)
        self.Bind(wx.EVT_MENU, lambda _: self.export_pdf(),     id=self._id_export_pdf)
        self.Bind(wx.EVT_MENU, lambda _: self.export_document(), id=self._id_export)
        self.Bind(wx.EVT_MENU, lambda _: self.show_markdown(),  id=self._id_show_markdown)
        self.Bind(wx.EVT_MENU, lambda _: self.print_document(), id=wx.ID_PRINT)
        self.Bind(wx.EVT_MENU, lambda _: self.Close(), id=wx.ID_CLOSE)
        self.Bind(wx.EVT_MENU, lambda _: self.Close(), id=wx.ID_EXIT)
        self.Bind(wx.EVT_CLOSE, self.on_close)

        edit_menu = wx.Menu()
        self.undo_item = edit_menu.Append(wx.ID_UNDO, "&Undo\tCtrl+Z")
        self.redo_item = edit_menu.Append(wx.ID_REDO, "&Redo\tCtrl+Y")
        edit_menu.AppendSeparator()
        edit_menu.Append(wx.ID_CUT,   "Cu&t\tCtrl+X")
        edit_menu.Append(wx.ID_COPY,  "&Copy\tCtrl+C")
        edit_menu.Append(wx.ID_PASTE, "&Paste\tCtrl+V")
        edit_menu.AppendSeparator()
        self._add_actions(edit_menu, (
            ("Move Paragraph &Up\tAlt+Up", 'move_par_up'),
            ("Move Paragraph &Down\tAlt+Down", 'move_par_down')))
        edit_menu.AppendSeparator()
        edit_menu.Append(wx.ID_FIND,    "&Find && Replace…\tCtrl+F")
        edit_menu.AppendSeparator()
        edit_menu.Append(wx.ID_PREFERENCES, "&Preferences…")
        bar.Append(edit_menu, "&Edit")

        insert_menu = wx.Menu()
        for label, char in (
                ("Non-breaking &space\tCtrl+Shift+Space", '\u00a0'),
                ("Non-breaking &hyphen\tCtrl+Shift+-", '\u2011'),
                ("Soft h&yphen\tCtrl+Alt+-", '\u00ad')):
            item = insert_menu.Append(wx.ID_ANY, label)
            self.Bind(wx.EVT_MENU, lambda _, c=char: self.insert_char(c),
                      item)
        insert_menu.AppendSeparator()
        item = insert_menu.Append(wx.ID_ANY, "Horizontal &Rule")
        self.Bind(wx.EVT_MENU, lambda _: self.insert_rule(), item)
        bar.Append(insert_menu, "&Insert")

        format_menu = wx.Menu()
        self._add_actions(format_menu, (
            ("&Bold\tCtrl+B", 'bold'), ("&Italic\tCtrl+I", 'italic'),
            ("&Underline\tCtrl+U", 'underline'), None,
            ("Increase &Indent\tAlt+Right", 'indent'),
            ("&Decrease Indent\tAlt+Left", 'dedent'),
            ("Next &List Type\tCtrl+T", 'cycle_list_type'),
            ("Next &Paragraph Style\tAlt+T", 'cycle_basestyle')))
        bar.Append(format_menu, "F&ormat")
        self.Bind(wx.EVT_MENU, lambda _: self.editor.undo(),  id=wx.ID_UNDO)
        self.Bind(wx.EVT_MENU, lambda _: self.editor.redo(),  id=wx.ID_REDO)
        self.Bind(wx.EVT_MENU, lambda _: self.cut(),   id=wx.ID_CUT)
        self.Bind(wx.EVT_MENU, lambda _: self.copy(),  id=wx.ID_COPY)
        self.Bind(wx.EVT_MENU, lambda _: self.paste(), id=wx.ID_PASTE)
        self.Bind(wx.EVT_MENU, lambda _: self.find(),        id=wx.ID_FIND)
        self.Bind(wx.EVT_MENU, lambda _: self.preferences(), id=wx.ID_PREFERENCES)

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
        self._mi_marks = view_menu.AppendCheckItem(wx.ID_ANY,
                                                   "Formatting marks")
        self._mi_marks.Check(show_marks())
        bar.Append(view_menu, "&View")
        self.Bind(wx.EVT_MENU, lambda _: self.canvas.step_zoom(self.canvas.zoom_factor),       id=wx.ID_ZOOM_IN)
        self.Bind(wx.EVT_MENU, lambda _: self.canvas.step_zoom(1 / self.canvas.zoom_factor),   id=wx.ID_ZOOM_OUT)
        self.Bind(wx.EVT_MENU, lambda _: self.canvas.set_zoom(1.0),                            id=wx.ID_ZOOM_100)
        self.Bind(wx.EVT_MENU, lambda _: self._zoom_fit_width(),  id=self._id_zoom_fit_w)
        self.Bind(wx.EVT_MENU, lambda _: self._zoom_fit_page(),   id=self._id_zoom_fit_p)
        self.Bind(wx.EVT_MENU, lambda _: self.menu_inspector(), self._mi_panel)
        self.Bind(wx.EVT_MENU, lambda _: self.two_page(), self._mi_two_page)
        self.Bind(wx.EVT_MENU, lambda _: self.formatting_marks(),
                  self._mi_marks)

        help_menu = wx.Menu()
        help_menu.Append(wx.ID_ABOUT, "&About MiniWord…")
        self.Bind(wx.EVT_MENU, lambda _: self.about(), id=wx.ID_ABOUT)
        bar.Append(help_menu, "&Help")

        self.SetMenuBar(bar)
        from ..layout import pagebuilder as _pagebuilder
        if _pagebuilder.DEBUG:
            self._add_debug_menu()

    def _add_debug_menu(self):
        if self._debug_menu is not None:
            return
        self._id_debug_console = wx.NewIdRef()
        self._id_debug_dump    = wx.NewIdRef()
        self._id_debug_txl     = wx.NewIdRef()
        self._id_debug_boxes   = wx.NewIdRef()
        debug_menu = wx.Menu()
        debug_menu.Append(self._id_debug_console, "Open Python console")
        debug_menu.Append(self._id_debug_dump,    "Dump texel tree")
        debug_menu.Append(self._id_debug_txl,     "Dump TXL")
        debug_menu.Append(self._id_debug_boxes,   "Dump box tree")
        self.GetMenuBar().Append(debug_menu, "&Debug")
        self.Bind(wx.EVT_MENU, lambda _: self.debug_console(), id=self._id_debug_console)
        self.Bind(wx.EVT_MENU, lambda _: self.debug_dump(),    id=self._id_debug_dump)
        self.Bind(wx.EVT_MENU, lambda _: self.debug_txl(),     id=self._id_debug_txl)
        self.Bind(wx.EVT_MENU, lambda _: self.debug_boxes(),   id=self._id_debug_boxes)
        self._debug_menu = debug_menu

    def on_secret_key(self, event):
        """Hidden 'ESC debug ESC' key-code enables the Debug menu at runtime."""
        code = event.GetKeyCode()
        if code == wx.WXK_ESCAPE:
            if self._secret_armed and self._secret_buffer == 'debug':
                from ..layout import pagebuilder as _pagebuilder
                _pagebuilder.DEBUG = True
                self._add_debug_menu()
                self._secret_armed = False
            else:
                self._secret_armed = True
            self._secret_buffer = ''
            event.Skip()
            return
        if self._secret_armed:
            uni = event.GetUnicodeKey()
            ch = chr(uni).lower() if uni != wx.WXK_NONE else ''
            if ch and 'debug'.startswith(self._secret_buffer + ch):
                self._secret_buffer += ch
            else:
                self._secret_armed = False
                self._secret_buffer = ''
        event.Skip()

    def _create_editor_canvas(self):
        factory = Factory(self.document.basestyles, device=CairoDevice())
        builder = PageBuilder(self.document.textmodel, factory)
        builder.settings = self.document.settings
        builder.rebuild()
        builder.assure_y(1)  # build first row, so initial geometry is known
        builder.build_background()  # build the rest asynchronously
        self.editor = TwoFlowEditor(self.document.textmodel)
        self.canvas = TextCanvas(
            self._base, self.document.textmodel, builder, self.editor)
        self.editor.canvas = self.canvas
        self.canvas.show_marks = show_marks()
        colours.set(self.canvas, 'BackgroundColour', 'CanvasBg')
        self.editor.add_view(self)
        self.document.add_view(self)

    def _build_inspector_panels(self):
        self._inspector_book = wx.Simplebook(self._base)
        colours.set(self._inspector_book, 'BackgroundColour', 'BTNFACE')
        self._inspector_pages = {}
        self.inspector = StyleInspector(self._inspector_book, self.editor, self.document.basestyles)
        self.document_settings = SettingsInspector(
            self._inspector_book, self.document, self.editor)
        self.table_panel = TablePanel(self._inspector_book, self.editor)
        self.image_inspector = ImageInspector(self._inspector_book, self.editor, self.document)
        self._search_panel = SearchPanel(self._inspector_book, self.editor)
        self._outline_panel = OutlinePanel(self._inspector_book, self.document, self.editor)
        self._links_panel = LinksPanel(self._inspector_book, self.editor, self.document)
        self.panels = [
            ("style",    self.inspector),
            ("settings", self.document_settings),
            ("table",    self.table_panel),
            ("image",    self.image_inspector),
            ("search",   self._search_panel),
            ("outline",  self._outline_panel),
            ("links",    self._links_panel),
        ]
        for key, panel in self.panels:
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
        self.image_bar = MessageBar(self._base, self._layout)
        self._build_inspector_panels()
        self._panel_key = None

        self._build_strip()

        self._base.Bind(wx.EVT_SIZE, lambda e: (e.Skip(), self._layout()))

        self.Bind(wx.EVT_DPI_CHANGED, self.on_dpi_changed)
        self.Bind(wx.EVT_DISPLAY_CHANGED, self.on_dpi_changed)

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

    def preferences(self):
        from ..core.config import get_config
        from .unitentry import LengthInput
        dlg = _PreferencesDialog(self, LengthInput.prefs, get_config())
        dlg.ShowModal()
        dlg.Destroy()

    def about(self):
        from miniword import __version__ as ver

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

    def menu_inspector(self):
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

    def two_page(self):
        from ..layout.pagebuilder import Layout, TwoPageLayout
        builder = self.canvas.builder
        was_finished = builder._layout.is_finished
        pages = builder.layout.childs
        builder.layout_class = TwoPageLayout if self._mi_two_page.IsChecked() else Layout
        builder._layout = builder.layout_class(pages)
        builder._layout.is_finished = was_finished
        self.canvas.refresh()

    def find(self):
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
        for _p1, _p2, _px, py, page in layout.iter_boxes(0):
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

        bar = getattr(self, 'image_bar', None)  # not yet while building
        top = bar.GetBestSize()[1] if bar and bar.IsShown() else 0
        if top:  # above the page
            bar.SetPosition((0, 0))
            bar.SetSize((text_w, top))
        self.canvas.SetPosition((0, top))
        self.canvas.SetSize((text_w, h - top))

        self._strip.SetPosition((w - strip_w, 0))
        self._strip.SetSize((strip_w, h))

        if self._panel_key is not None:
            self._inspector_book.SetPosition((text_w, 0))
            self._inspector_book.SetSize((panel_w, h))

        self._base.Refresh()

    def _build_strip(self):
        self._strip = RightStrip(self._base, [
            ("style",    "Styles"),    # format text and objects
            ("table",    "Table"),
            ("image",    "Image"),
            ("links",    "Links"),
            ("outline",  "Outline"),   # navigate
            ("search",   "Search"),
            ("settings", "Settings"),  # the document
        ], self._on_panel_toggle)

    def on_dpi_changed(self, event):
        self._build_menu()
        self._register_plugin_menus()
        active_key = self._strip.active_btn._key if self._strip.active_btn else None
        self._strip.Destroy()
        self._build_strip()
        if active_key:
            self._strip.activate(active_key)
        for key, panel in self.panels:
            panel.dpi_changed()
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

    def setting_changed(self, document, name, old):
        """Paper, margins, header/footer...: the pages are built anew
        (their restart memos hold the settings)."""
        self.canvas.builder.settings = document.settings
        self._rebuild()

    def _restore_geometry(self):
        """Size and position as last time, else most of the screen."""
        config = get_config()
        displays = [wx.Display(k) for k in range(wx.Display.GetCount())]
        displays.sort(key=lambda d: not d.IsPrimary())
        areas = [d.GetClientArea().Get() for d in displays]
        rect = window_rect(config.get('window_rect'), areas,
                           self.FromDIP(1400))
        self.SetRect(wx.Rect(*rect))
        if config.get('window_maximized'):
            self.Maximize()

    def _save_geometry(self):
        config = get_config()
        config.set('window_maximized', self.IsMaximized())
        if not self.IsMaximized() and not self.IsIconized():
            config.set('window_rect', list(self.GetRect().Get()))

    def on_close(self, event):
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
                self.save()
                if self.editor.undocount() > 0:
                    event.Veto()
                    return
            elif result == wx.ID_CANCEL:
                event.Veto()
                return
        self.release()
        self._save_geometry()
        event.Skip()

    def release(self):
        """Free what outlives the window: stop the layout, take the
        recent files menu out of the app-wide file history (on closing;
        tests call it too)."""
        builder = getattr(getattr(self, 'canvas', None), 'builder', None)
        if builder is not None:
            builder.stop()
        _forget_menu(self._recent_menu)

    def formatting_marks(self):
        """View > Formatting marks: only redrawn, nothing is rebuilt."""
        show = self._mi_marks.IsChecked()
        self.canvas.show_marks = show
        get_config().set('show_formatting_marks', show)
        self.canvas.refresh()

    def insert_rule(self):
        """Insert a horizontal rule, in a paragraph of its own (style
        with the role 'rule', if there is one)."""
        from ..core.texels import Rule
        from ..textmodel.texeltree import NL, grouped
        editor = self.editor
        with editor.atomic():
            editor.remove()
            if editor.index != editor.target.linestart(editor.index):
                editor.insert_newline()
            key = editor.role_key('rule')
            nl = NL.set_parstyle({'base': key}) if key else NL
            editor.insert_texel(grouped([Rule(), nl]))

    def insert_char(self, char):
        """Type char: it replaces the selection."""
        with self.editor.atomic():
            self.editor.remove()
            self.editor.insert_text(char)

    def new(self):
        frame = MainFrame(new_document())
        frame.Show()

    def open_document(self):
        from ..io import importexport
        with wx.FileDialog(
            self, "Open",
            defaultDir=last_dir(),
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
        remember_dir(path)

    def on_recent_file(self, event):
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
        remember_dir(path)

    def import_document(self):
        from ..io import importexport
        with wx.FileDialog(
            self, "Import",
            defaultDir=last_dir(),
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
        remember_dir(path)

    def export_document(self):
        from ..io import importexport
        with wx.FileDialog(
            self, "Export",
            defaultDir=self._dialog_dir(),
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

    def show_markdown(self):
        if getattr(self, '_markdown_preview', None) is not None:
            self._markdown_preview.Raise()
            return
        from .markdownpreview import MarkdownPreviewFrame
        self._markdown_preview = MarkdownPreviewFrame(self, self.document)
        self._markdown_preview.Bind(wx.EVT_CLOSE, self.on_markdown_preview_close)
        self._markdown_preview.Show()

    def on_markdown_preview_close(self, event):
        self._markdown_preview = None
        event.Skip()

    def cut(self):
        self.editor.controller.handle_action('cut', False)

    def copy(self):
        self.editor.controller.handle_action('copy', False)

    def paste(self):
        """Ctrl+V: Miniword's own format; else the first clipboard flavor
        a plugin pastes (e.g. HTML from a browser, see register_paste);
        else an image (e.g. a screenshot); else plain text."""
        from ..io.importexport import paste_handlers
        from ..images.images import Image
        from ..textmodel.texeltree import grouped
        canvas = self.editor.canvas
        if canvas.read_clipboard_data('pytextmodel') is None:
            image = canvas.read_clipboard_image()
            for flavor, handler in paste_handlers():
                data = canvas.read_clipboard_data(flavor)
                if data and self._paste_fragment(handler, data, image):
                    return
            if image:
                return self._insert_fragment(grouped([Image(image)]))
        self.editor.controller.handle_action('paste', False)

    def paste_as(self, handler):
        """'Paste from ...': the clipboard's plain text, e.g. as Markdown
        (see register_paste_as)."""
        text = self.editor.canvas.read_clipboard_text()
        if text:
            self._paste_fragment(handler, text)

    def _paste_fragment(self, handler, data, image=None):
        """Insert what handler makes of data; a lone image gets the
        clipboard's bitmap image (see with_bitmap), web images are loaded
        now. Whether there was something."""
        from ..images.imageio import load_urls
        with wx.BusyCursor():
            texel = handler(data, self.document)
            if texel is not None and image:
                texel = with_bitmap(texel, image)
            if texel is not None:
                load_urls(texel)
        if texel is not None:
            self._insert_fragment(texel)
        return texel is not None

    def _insert_fragment(self, texel):
        """Insert texel; too large images are made smaller (fit_to_page)."""
        from ..images.images import fit_to_page
        editor = self.editor
        texel = fit_to_page(texel, self.document.settings,
                            (editor.target.texel, editor.index))
        with self.editor.atomic():
            self.editor.remove()
            self.editor.insert_texel(texel)

    def save(self):
        if not self._current_path:
            self.save_as()
            return
        self._do_save(self._current_path)

    def _doc_dir(self):
        return os.path.dirname(self._current_path) if self._current_path else ''

    def _dialog_dir(self):
        """Where file dialogs start: the document's folder, else the
        last one used."""
        return self._doc_dir() or last_dir()

    def save_as(self):
        from ..io import importexport
        with wx.FileDialog(
            self, "Save As",
            defaultDir=self._dialog_dir(),
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
        remember_dir(path)

    def _confirm_lossy_save(self, path, warnings):
        items = '\n'.join('\u2022 ' + w for w in warnings)
        msg = ("Saving as '%s' will lose:\n\n%s\n\nSave anyway?"
               % (os.path.basename(path), items))
        dlg = wx.MessageDialog(self, msg, "Format Warning",
                               wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING)
        result = dlg.ShowModal()
        dlg.Destroy()
        return result == wx.ID_YES

    def reload(self):
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

    def print_document(self):
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

    def export_pdf(self):
        with wx.FileDialog(
            self, "Export as PDF",
            defaultDir=self._dialog_dir(),
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
        self.canvas.export_pdf(path)

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

    def basestyles_changed(self, *args):
        self.canvas.builder.clear_caches()
        self._rebuild()

    def _rebuild(self):
        """All pages anew: the visible ones now (with progress), the
        rest in the background."""
        builder = self.canvas.builder
        builder.rebuild()
        build_to(builder, self.canvas.get_viewport().y2, self)
        builder.build_background()
        self.canvas.refresh()


    def _get_debug_range(self):
        if self.editor.has_selection():
            return sorted(self.editor.selection)
        return None

    def debug_console(self):
        from . import testing
        l = locals()
        l.update(globals())
        testing.pyshell(l)

    def _get_debug_texel(self):
        model = self.editor.root
        r = self._get_debug_range()
        if r:
            return model.copy(*r).texel
        return model.texel

    def debug_dump(self):
        from ..textmodel.texeltree import dump
        dump(self._get_debug_texel())

    def debug_txl(self):
        from ..io.texeltreeformat import serialize
        print(serialize(self._get_debug_texel()))

    def debug_boxes(self):
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

    app = wx.App(True)
    doc = Document()
    doc.textmodel = get_einstein_model()
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

    textmodel = get_moby_styled()

    app = wx.App(True)
    doc = Document()
    doc.textmodel = textmodel
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


def test_03():
    "View > zoom menu actions (in/out/actual size/fit width/fit page)"
    from ..core.document import Document
    import wx

    app = wx.App()
    doc = Document()
    frame = MainFrame(doc)
    frame.Show()
    app.Yield()

    editor = frame.editor
    for ch in "Some text to lay out.":
        editor.insert_text(ch)
    app.Yield()

    tv = frame.canvas

    # Zoom In / Out: multiply/divide by zoom_factor, capped at min/max_zoom
    tv.set_zoom(1.0)
    tv.step_zoom(tv.zoom_factor)
    assert tv.get_zoom() == 1.0 * tv.zoom_factor
    tv.set_zoom(tv.max_zoom)
    tv.step_zoom(tv.zoom_factor)
    assert tv.get_zoom() == tv.max_zoom  # capped, doesn't overshoot

    tv.set_zoom(1.0)
    tv.step_zoom(1 / tv.zoom_factor)
    assert tv.get_zoom() == 1.0 / tv.zoom_factor
    tv.set_zoom(tv.min_zoom)
    tv.step_zoom(1 / tv.zoom_factor)
    assert tv.get_zoom() == tv.min_zoom  # capped, doesn't undershoot

    # Actual Size: bound to wx.ID_ZOOM_100 in _build_menu
    tv.set_zoom(2.5)
    tv.set_zoom(1.0)
    assert tv.get_zoom() == 1.0

    # Fit to Text Width
    cw = tv.GetClientSize()[0]
    expected = cw / tv.layout.width
    frame._zoom_fit_width()
    assert tv.get_zoom() == expected, (tv.get_zoom(), expected)

    # Fit to Page -- used to raise: iter_boxes() takes 2 args, 4 given
    cw, ch_ = tv.GetClientSize()
    _p1, _p2, _px, _py, page = next(iter(tv.layout.iter_boxes(0)))
    expected = min(cw / tv.layout.width, ch_ / (page.height + page.depth))
    frame._zoom_fit_page()
    assert tv.get_zoom() == expected, (tv.get_zoom(), expected)

    frame.Destroy()
    app.Yield()


def test_04():
    "window_rect: first start fills 90% of the screen, at most max_w wide"
    full_hd = [(0, 0, 1920, 1080)]
    assert window_rect(None, full_hd, 1400) == (260, 54, 1400, 972)
    laptop = [(0, 0, 1280, 800)]
    assert window_rect(None, laptop, 1400) == (64, 40, 1152, 720)


def test_05():
    "window_rect: a saved rect is kept if it starts on some display"
    two = [(0, 0, 1920, 1080), (1920, 0, 1920, 1080)]
    assert window_rect((100, 50, 1000, 600), two, 1400) == (100, 50, 1000, 600)
    assert window_rect((2000, 100, 800, 600), two, 1400) == \
        (2000, 100, 800, 600)
    # the second display is gone: back to the default
    one = two[:1]
    assert window_rect((2000, 100, 800, 600), one, 1400) == \
        window_rect(None, one, 1400)


def test_06():
    "window_rect: a saved rect larger than its display is shrunk to it"
    one = [(0, 0, 1280, 800)]
    assert window_rect((10, 20, 1600, 1000), one, 1400) == (10, 20, 1270, 780)


def test_07():
    "the window opens as large as it was closed (config replaced by a dict)"
    from ..core.document import Document
    global get_config

    class FakeConfig(dict):
        def set(self, key, value):
            self[key] = value

    config = FakeConfig()
    saved_get_config, get_config = get_config, lambda: config
    app = wx.App.Get() or wx.App()
    try:
        frame = MainFrame(Document())
        frame.Show()
        frame.SetSize(frame.FromDIP(wx.Size(900, 600)))
        app.Yield()
        size = frame.GetSize()
        frame.Close()
        app.Yield()
        assert config['window_rect'][2:] == [size.width, size.height]
        assert config['window_maximized'] is False

        frame = MainFrame(Document())
        assert frame.GetSize() == size
        frame.Destroy()
        app.Yield()
    finally:
        get_config = saved_get_config


def test_08():
    "document settings reach the page layout, also when changed later"
    from ..core.document import Document
    from ..core.units import cm
    app = wx.App.Get() or wx.App()
    doc = Document()
    doc.set_setting('margin_left', 4 * cm)
    frame = MainFrame(doc)
    try:
        builder = frame.canvas.builder
        builder.assure_y(1)
        assert builder._layout.childs[0].margin[3] == 4 * cm
        doc.set_setting('margin_left', 5 * cm)
        doc.set_setting('header_left', ('text', 'Draft'))
        builder.assure_y(1)
        page = builder._layout.childs[0]
        assert page.margin[3] == 5 * cm
        assert page.header_footer_texts()[0][0] == 'Draft'
    finally:
        frame.Destroy()
        app.Yield()


def test_09():
    "new documents get the system language for hyphenation"
    from ..core.document import settings_default
    from ..core.utils import updated
    doc = new_document('de_DE')
    assert doc.settings['language'] == 'de-1996'
    doc = new_document('fr_FR')
    assert updated(settings_default, doc.settings)['language'] == 'en-us'
    assert doc.settings.get('hyphenation') is None  # stays off


def test_10():
    "Insert menu: protected space and hyphen, soft hyphen, with shortcuts"
    from ..core.document import Document
    app = wx.App.Get() or wx.App()
    frame = MainFrame(Document())
    try:
        menu = frame.GetMenuBar().GetMenu(
            frame.GetMenuBar().FindMenu('Insert'))
        expected = {'Ctrl+Shift+Space': '\u00a0', 'Ctrl+Shift+-': '\u2011',
                    'Ctrl+Alt+-': '\u00ad'}
        items = menu.GetMenuItems()
        accels = [item.GetItemLabel().split('\t')[1] for item in items]
        assert sorted(accels) == sorted(expected)
        for item, accel in zip(items, accels):
            frame.ProcessWindowEvent(
                wx.CommandEvent(wx.wxEVT_MENU, item.GetId()))
        text = frame.document.textmodel.get_text()
        assert ''.join(expected[a] for a in accels) in text
    finally:
        frame.Destroy()
        app.Yield()


def test_11():
    "View > Formatting marks: drawn on screen only, no relayout, saved"
    from ..core.document import Document
    from ..layout import marks
    global get_config

    class FakeConfig(dict):
        def set(self, key, value):
            self[key] = value

    config = FakeConfig()
    saved_get_config, get_config = get_config, lambda: config
    saved_draw_marks = marks.draw_marks
    calls = []
    marks.draw_marks = lambda dc, boxes: calls.append(1)
    app = wx.App.Get() or wx.App()
    frame = MainFrame(Document())
    try:
        frame.Show()
        app.Yield()
        assert frame.canvas.show_marks          # on by default
        layout = frame.canvas.builder._layout
        rows = [list(page.rows) for page in layout.childs]
        item = frame._mi_marks
        item.Check(False)
        frame.ProcessWindowEvent(wx.CommandEvent(wx.wxEVT_MENU,
                                                 item.GetId()))
        assert not frame.canvas.show_marks
        assert config['show_formatting_marks'] is False
        assert frame.canvas.builder._layout is layout   # nothing rebuilt
        assert [list(page.rows) for page in layout.childs] == rows
        calls.clear()
        frame.canvas.Refresh()
        frame.canvas.Update()
        app.Yield()
        assert calls == []                      # off: not drawn
    finally:
        marks.draw_marks = saved_draw_marks
        get_config = saved_get_config
        frame.Destroy()
        app.Yield()
