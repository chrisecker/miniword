import sys
import threading
import wx
from .core.document import Document
from .core.config import get_config
from .ui.mainwindow import MainFrame
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


def main():
    args = sys.argv[1:]
    if '--debug' in args:
        pagebuilder.DEBUG = True
        args = [a for a in args if a != '--debug']
    path = args[0] if args else None

    _enable_dpi_awareness()
    config = get_config()
    LengthInput.prefs = UnitPrefs(
        layout=config.get("layout_unit"),
        typographic=config.get("typographic_unit"),
    )
    app = wx.App(redirect=False)
    app.SetAppName("miniword")
    from .ui.mainwindow import load_plugins
    load_plugins()

    from .core.fontfinder import _scan_needed
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
        frame = MainFrame(Document())
    frame.Show()
    app.MainLoop()


if __name__ == '__main__':
    main()
