import sys
import wx
from .core.document import Document
from .ui.mainwindow import MainFrame
from .layout import builder


def main():
    args = sys.argv[1:]
    if '--debug' in args:
        builder.DEBUG = True
        args = [a for a in args if a != '--debug']
    path = args[0] if args else None

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
