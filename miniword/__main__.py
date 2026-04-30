import sys
import wx
from .core.document import Document
from .core.config import get_config
from .ui.mainwindow import MainFrame
from .ui.unitentry import LengthInput, UnitPrefs
from .layout import builder


def _enable_dpi_awareness():
    """Enable Per-Monitor DPI awareness on Windows to avoid blurry rendering."""
    if sys.platform != 'win32':
        return
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-Monitor DPI aware
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def main():
    args = sys.argv[1:]
    if '--debug' in args:
        builder.DEBUG = True
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
