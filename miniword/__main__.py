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
    return args


def convert(path, output):
    """Command line -o: write the document at path to output, in the
    format of its extension; returns the exit code. Losses (e.g. .txl to
    .md) are only reported."""
    import os
    from .io import importexport
    from .io.pdf import export_pdf

    def report(text):
        print('miniword: ' + text, file=sys.stderr)

    try:
        doc = importexport.open_file(path)
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
        return convert(path, args.output)
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
