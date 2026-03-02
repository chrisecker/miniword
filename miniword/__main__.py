import sys
import wx
from .document import Document
from .mainwindow import MainFrame


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else None

    app = wx.App(redirect=False)
    if path:
        doc = Document.load(path)
        frame = MainFrame(doc)
        frame._current_path = path
        frame._update_title()
    else:
        frame = MainFrame(Document())
    frame.Show()
    app.MainLoop()


main()
