import os
import tempfile
import wx
from .colours import colours
from .icons import app_icon_bundle


class MarkdownPreviewFrame(wx.Frame):
    """Non-modal window showing the document as Markdown."""

    def __init__(self, parent, document):
        super().__init__(parent, title="Markdown Preview",
                          style=wx.DEFAULT_FRAME_STYLE)
        self._document = document
        self.SetIcons(app_icon_bundle())
        colours.set(self, 'BackgroundColour', 'BTNFACE')

        self.text_ctrl = wx.TextCtrl(
            self, style=wx.TE_MULTILINE | wx.TE_READONLY)
        colours.set(self.text_ctrl, 'BackgroundColour', 'WINDOW')
        colours.set(self.text_ctrl, 'ForegroundColour', 'WINDOWTEXT')
        font = wx.Font(wx.FontInfo(10).FaceName("Courier New"))
        self.text_ctrl.SetFont(font)

        update_btn = wx.Button(self, label="Update")
        close_btn  = wx.Button(self, label="Close")
        update_btn.Bind(wx.EVT_BUTTON, self._on_update)
        close_btn.Bind(wx.EVT_BUTTON, lambda evt: self.Close())

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(update_btn, 0, wx.RIGHT, 8)
        btn_sizer.Add(close_btn, 0)

        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(self.text_ctrl, 1, wx.EXPAND | wx.ALL, 8)
        outer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 8)
        self.SetSizer(outer)
        self.SetSize(self.FromDIP(wx.Size(700, 600)))

        self._refresh()
        self.CentreOnParent()

    def _on_update(self, event):
        self._refresh()

    def _refresh(self):
        self.text_ctrl.SetValue(document_to_markdown(self._document))


def document_to_markdown(document):
    """Render document to a Markdown string via the export filter."""
    from ..io import importexport
    fn = importexport.find_export_filter("preview.md")
    if fn is None:
        return ""
    fd, path = tempfile.mkstemp(suffix=".md")
    os.close(fd)
    try:
        fn(document, path)
        with open(path, encoding="utf-8") as f:
            return f.read()
    finally:
        os.unlink(path)


def _tesla_txl_path():
    here = os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(here, 'test', 'tesla.txl')


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def demo_00():
    "Markdown preview of test/tesla.txl"
    from ..core.document import Document
    from ..plugins import mdfilter  # noqa: F401 -- registers md export

    doc = Document.load(_tesla_txl_path())

    app = wx.App(True)
    frame = MarkdownPreviewFrame(None, doc)
    frame.Show()
    app.MainLoop()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_00():
    "document_to_markdown renders tesla.txl"
    from ..core.document import Document
    from ..plugins import mdfilter  # noqa: F401 -- registers md export

    doc = Document.load(_tesla_txl_path())

    md = document_to_markdown(doc)
    assert '# Nikola Tesla: Der Magier der Elektrizität' in md
    assert 'serbisch-amerikanischer Erfinder' in md


def test_01():
    "Update button re-renders after an edit"
    from ..core.document import Document
    from ..plugins import mdfilter  # noqa: F401 -- registers md export

    doc = Document.load(_tesla_txl_path())

    app = wx.App()
    frame = MarkdownPreviewFrame(None, doc)
    app.Yield()

    before = frame.text_ctrl.GetValue()
    assert '# Nikola Tesla: Der Magier der Elektrizität' in before
    assert 'ZZZ' not in before

    doc.textmodel.insert_text(0, 'ZZZ')
    frame._on_update(None)
    app.Yield()

    after = frame.text_ctrl.GetValue()
    assert '# ZZZNikola Tesla: Der Magier der Elektrizität' in after

    frame.Destroy()
    app.Yield()
