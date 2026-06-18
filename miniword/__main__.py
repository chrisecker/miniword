import sys
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
        ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)
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
