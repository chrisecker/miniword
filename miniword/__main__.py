import sys
import wx
from .document import Document
from .mainwindow import MainFrame
from . import builder


def main():
    args = sys.argv[1:]
    if '--debug' in args:
        builder.DEBUG = True
        args = [a for a in args if a != '--debug']
    path = args[0] if args else None

    app = wx.App(redirect=False)
    from .mainwindow import load_plugins
    load_plugins()
    if path:
        from . import importexport
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
