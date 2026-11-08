import sys
import threading
import wx
from .core.document import Document
from .core.config import get_config
from .ui.mainwindow import MainFrame, new_document
from .ui.unitentry import LengthInput, UnitPrefs
from .layout import pagebuilder


def _enable_dpi_awareness():
    """Enable Per-Monitor DPI awareness v2 on Windows."""
    if sys.platform != 'win32':
        return
    import ctypes
    try:
        # Windows 10 v1703+: Using SetProcessDpiAwarenessContext mit v2
        # -4 entspricht DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        # NOTE: the context value is a HANDLE (pointer-sized). Passing a
        # bare negative Python int lets ctypes marshal it as a 32-bit
        # c_int, which truncates it on 64-bit Windows; the call then
        # fails (returns FALSE) without raising, silently leaving the
        # process DPI-unaware (-> blurry, bitmap-stretched window). It
        # must be wrapped as c_void_p, and the return value checked.
        ok = ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        if not ok:
            raise OSError("SetProcessDpiAwarenessContext failed")
    except Exception:
        try:
            # Fallback for Windows 8.1 / early Win 10 (2 = Process_Per_Monitor_DPI_Aware)
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                # Fallback for Windows Vista / 7
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
            
def _run_font_preload_dialog():
    """Show a modal progress dialog while the font-coverage cache is built.

    Runs on the first start (or after a system font update).  Subsequent starts
    load the cache from disk and skip this dialog entirely.
    """
    from .core.fontfinder import run_preload_sync

    finished = [False]
    progress = [0, 1]  # [done, total]

    def worker():
        def cb(done, total):
            progress[0] = done
            progress[1] = total
        run_preload_sync(progress_cb=cb)
        finished[0] = True

    t = threading.Thread(target=worker, daemon=True, name='fontlink-preload')
    t.start()

    dlg = wx.Dialog(None, title="miniword",
                    style=wx.CAPTION | wx.STAY_ON_TOP)
    panel = wx.Panel(dlg)
    label = wx.StaticText(panel, label="Indexing fonts (first start only) …")
    gauge = wx.Gauge(panel, range=100, size=dlg.FromDIP(wx.Size(300, 14)))
    sizer = wx.BoxSizer(wx.VERTICAL)
    sizer.Add(label, 0, wx.ALL, dlg.FromDIP(14))
    sizer.Add(gauge, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, dlg.FromDIP(14))
    panel.SetSizer(sizer)
    sizer.Fit(dlg)
    dlg.Centre()

    timer = wx.Timer(dlg)

    def _on_timer(evt):
        if finished[0]:
            timer.Stop()
            dlg.EndModal(wx.ID_OK)
        else:
            gauge.SetValue(int(progress[0] * 100 / max(1, progress[1])))

    dlg.Bind(wx.EVT_TIMER, _on_timer, timer)
    timer.Start(80)
    dlg.ShowModal()
    t.join()
    dlg.Destroy()


def parse_args(argv):
    """The command line options (argv without the program name)."""
    import argparse
    from . import __version__
    parser = argparse.ArgumentParser(
        prog='miniword', description="MiniWord, a small word processor.")
    parser.add_argument(
        'file', nargs='?',
        help="document to open (.txl, or a format a plugin imports, "
             "e.g. .md); without it a new document")
    parser.add_argument(
        '-o', '--output', metavar='OUTFILE',
        help="write the document to OUTFILE and exit, without a window; "
             "the format follows the extension (.pdf, .txl, .md, .txt)")
    parser.add_argument(
        '--template', metavar='TEMPLATE',
        help="with -o: page setup from TEMPLATE (.txl), and the values of "
             "its styles for the styles with the same role")
    parser.add_argument(
        '--set', metavar='KEY=VALUE', action='append', default=[],
        type=parse_setting,
        help="with -o: a document setting, after --template, e.g. "
             "paper=A5, paper=170x240mm, margin_left=2cm, "
             "hyphenation=yes, footer_center=page, header_left=text:Draft; "
             "repeatable")
    parser.add_argument(
        '--debug', action='store_true',
        help="debug output of the page layout")
    parser.add_argument(
        '--install-desktop', action='store_true',
        help="Linux: add MiniWord to the menu and open .txl files with it")
    parser.add_argument(
        '--uninstall-desktop', action='store_true',
        help="Linux: undo --install-desktop")
    parser.add_argument(
        '--version', action='version', version='%(prog)s ' + __version__)
    args = parser.parse_args(argv)
    if args.output and not args.file:
        parser.error("-o needs a document to read")
    if (args.template or args.set) and not args.output:
        parser.error("--template and --set need -o")
    return args


BOOLS = {'yes': True, 'true': True, 'on': True, '1': True,
         'no': False, 'false': False, 'off': False, '0': False}


def parse_setting(text):
    """--set KEY=VALUE: the settings [(key, value)], the value read by the
    type of the default (see develnotes/cli_converter_concept.md)."""
    from argparse import ArgumentTypeError
    from .core.document import settings_default
    from .core.units import parse_length
    from .ui.settingsinspector import FIELD_KINDS
    key, sep, value = text.partition('=')
    if not sep or key not in settings_default:
        raise ArgumentTypeError("%r: KEY is one of %s"
                                % (text, ', '.join(settings_default)))
    default = settings_default[key]
    try:
        if key == 'paper':
            return paper_settings(value)
        if isinstance(default, bool):
            return [(key, BOOLS[value.lower()])]
        if isinstance(default, float):
            return [(key, parse_length(value))]
        if isinstance(default, tuple):
            kind, _, field = value.partition(':')
            if kind not in [k for _, k in FIELD_KINDS]:
                raise ValueError
            return [(key, (kind, field))]
    except (KeyError, ValueError):
        raise ArgumentTypeError("%r: invalid value for %s" % (text, key))
    return [(key, value)]


def paper_settings(value):
    """--set paper=: a name from PAPER_SIZES (any case), custom, or
    WIDTHxHEIGHT with a unit, e.g. 170x240mm."""
    import re
    from .core.papersizes import PAPER_SIZES
    from .core.units import parse_length
    names = {name.lower(): name for name in list(PAPER_SIZES) + ['custom']}
    if value.lower() in names:
        return [('paper', names[value.lower()])]
    m = re.fullmatch(r'([\d.]+)x([\d.]+)([a-z]*)', value.lower())
    if m is None:
        raise ValueError(value)
    width, height, unit = m.groups()
    return [('paper', 'custom'), ('paper_width', parse_length(width + unit)),
            ('paper_height', parse_length(height + unit))]


CONTENT_SETTINGS = ('title', 'author')  # not taken from a template


def apply_template(doc, template):
    """--template: doc takes the settings of template except title and
    author (content, not layout), and each of its styles with a role the
    values of template's style with that role; the names stay."""
    doc.settings = {key: value for key, value in template.settings.items()
                    if key not in CONTENT_SETTINGS} | \
        {key: value for key, value in doc.settings.items()
         if key in CONTENT_SETTINGS}
    sheet = doc.basestyles
    for key, style in sheet.items():
        role = style.get('role')
        other = template.basestyles.role_key(role) if role else None
        if other:
            sheet.set(key, template.basestyles.get(other))


def convert(path, output, template=None, settings=()):
    """Command line -o: write the document at path to output, in the
    format of its extension; returns the exit code. Losses (e.g. .txl to
    .md) are only reported. template: path of a template (--template),
    settings: [(key, value)] (--set)."""
    import os
    from .io import importexport
    from .io.pdf import export_pdf

    def report(text):
        print('miniword: ' + text, file=sys.stderr)

    try:
        doc = importexport.open_file(path)
        if template:
            apply_template(doc, importexport.open_file(template))
        for key, value in settings:
            doc.set_setting(key, value)
        ext = os.path.splitext(output)[1].lower()
        if ext == '.pdf':
            export_pdf(doc, output)
        elif ext == '.txl':
            doc.save(output)
        else:
            fn = importexport.find_export_filter(output)
            if fn is None:
                report("no format for '%s'" % output)
                return 1
            for warning in importexport.check_export(output, doc):
                report("'%s' loses: %s" % (output, warning))
            fn(doc, output)
    except Exception as e:
        report(str(e))
        return 1
    return 0


class App(wx.App):
    def MacOpenFiles(self, filenames):
        """macOS: files opened in the Finder (double click, Open With).
        An untouched empty window gives way to them."""
        from .io import importexport
        from .ui.mainwindow import note_file
        empty = [w for w in wx.GetTopLevelWindows()
                 if isinstance(w, MainFrame) and not w._current_path
                 and w.editor.undocount() == 0]
        opened = False
        for path in filenames:
            try:
                doc = importexport.open_file(path)
            except Exception as e:
                wx.MessageBox(str(e), "Open", wx.OK | wx.ICON_ERROR)
                continue
            frame = MainFrame(doc)
            frame._current_path = path
            frame._update_title()
            frame.Show()
            note_file(path)
            opened = True
        if opened:
            for w in empty:
                w.Close()


def main():
    args = parse_args(sys.argv[1:])  # before wx: --help needs no window
    if args.install_desktop or args.uninstall_desktop:
        if not sys.platform.startswith('linux'):
            print("Only on Linux; the installers do this on Windows/macOS.")
            return
        from . import desktop
        if args.install_desktop:
            desktop.install()
        else:
            desktop.uninstall()
        return
    pagebuilder.DEBUG = args.debug
    path = args.file

    _enable_dpi_awareness()
    config = get_config()
    LengthInput.prefs = UnitPrefs(
        layout=config.get("layout_unit"),
        typographic=config.get("typographic_unit"),
    )
    app = App(redirect=False)
    app.SetAppName("miniword")
    from .ui.mainwindow import load_plugins
    load_plugins()

    from .core.fontfinder import _scan_needed, run_preload_sync
    if args.output:
        if _scan_needed:
            run_preload_sync()  # no dialog without a window
        settings = [pair for pairs in args.set for pair in pairs]
        return convert(path, args.output, args.template, settings)
    if _scan_needed:
        _run_font_preload_dialog()

    if path:
        from .io import importexport
        try:
            doc = importexport.open_file(path)
        except Exception as e:
            print("Error opening '%s': %s" % (path, e))
            return
        frame = MainFrame(doc)
        frame._current_path = path
        frame._update_title()
    else:
        frame = MainFrame(new_document())
    frame.Show()
    app.MainLoop()


if __name__ == '__main__':
    sys.exit(main())
