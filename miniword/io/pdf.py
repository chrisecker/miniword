# -*- coding: utf-8 -*-

"""
PDF export: the pages of a layout as a PDF file. export_pdf sets the
pages itself and needs no window (command line -o); the window writes
the pages it shows (TextCanvas.export_pdf). Both need a wx.App.
"""


def write_pdf(pages, path):
    """Write the pages of a finished layout to path."""
    import cairocffi as cairo
    if not pages:
        return
    surface = cairo.PDFSurface(path, pages[0].width, pages[0].height)
    ctx = cairo.Context(surface)
    for page in pages:
        page.draw_background(0, 0, ctx)
        page.draw_for_print(0, 0, ctx)
        ctx.show_page()
    surface.finish()


def export_pdf(document, path):
    """Set the pages of document and write them to path."""
    from ..layout.pagebuilder import PageBuilder
    from ..layout.rowfactory import Factory
    from ..layout.cairodevice import CairoDevice
    factory = Factory(document.basestyles, device=CairoDevice())
    builder = PageBuilder(document.textmodel, factory)
    builder.settings = document.settings
    builder.rebuild()
    builder.assure_finished()
    write_pdf(builder.layout.childs, path)


def test_00():
    "export_pdf writes a PDF, without a window"
    import os
    import tempfile
    import wx
    from ..core.document import Document
    from ..textmodel.texeltree import grouped, T, ENDMARK
    if wx.App.Get() is None:
        wx.App(False)
    doc = Document()
    doc.textmodel.set_xtexel(grouped([T('Hallo'), ENDMARK]))
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, 'a.pdf')
        export_pdf(doc, path)
        with open(path, 'rb') as f:
            assert f.read(5) == b'%PDF-'
