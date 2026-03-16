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
        doc = Document.load(path)
        frame = MainFrame(doc)
        frame._current_path = path
        frame._update_title()
    else:
        frame = MainFrame(Document())
    frame.Show()
    app.MainLoop()


if __name__ == '__main__':
    main()
