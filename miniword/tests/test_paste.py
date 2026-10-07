# -*- coding: utf-8 -*-

"""
Tests for pasting HTML (e.g. from a browser) and Markdown, and for
loading their images from data URIs, files and the web (fetch_image).
IDs PASTE-n.

Run with: python runtests.py miniword/tests/test_paste.py
"""

import base64
import io
import os
import tempfile
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler

import wx

from ..core.document import Document
from ..images.images import fetch_image, iter_images
from ..plugins.htmlfilter import clipboard_html, html_text_to_fragment
from ..plugins.mdfilter import md_text_to_fragment
from ..textmodel.textmodel import TextModel
from .guitest import app


def png(width=2, height=2):
    """PNG data of a small image."""
    app()
    stream = io.BytesIO()
    wx.Image(width, height).SaveFile(stream, wx.BITMAP_TYPE_PNG)
    return stream.getvalue()


def pasted(html):
    """(model, images) of html pasted into a new document."""
    model = TextModel('')
    model.texel = html_text_to_fragment(html, Document())
    return model, list(iter_images(model.texel))


def style_of(model, word):
    return model.get_style(model.get_text().index(word))


def test_PASTE_1():
    "PASTE-1: the clipboard's HTML in UTF-8 or UTF-16 (Firefox) is decoded"
    html = '<p>Wal – Säugetier</p>'
    for data in (html.encode('utf-8'), html.encode('utf-16'),
                 html.encode('utf-16-le')):
        assert clipboard_html(data) == html


def test_PASTE_2():
    "PASTE-2: no whitespace-only paragraphs around a browser fragment"
    model, _ = pasted('<html><body>\n<!--StartFragment--><p>Wal</p>'
                      '<!--EndFragment-->\n</body>\n</html>')
    assert model.get_text() == 'Wal\n'


def test_PASTE_3():
    "PASTE-3: bold, italic and strike from CSS and <s>/<del>"
    model, _ = pasted(
        '<p><span style="font-weight:700">fett</span> '
        '<span style="font-weight: bold">auch</span> '
        '<span style="font-weight:400">normal</span> '
        '<span style="font-style:italic">schraeg</span> '
        '<span style="text-decoration: line-through">alt</span> '
        '<s>weg</s> <del>raus</del></p>')
    assert style_of(model, 'fett').get('bold') is True
    assert style_of(model, 'auch').get('bold') is True
    assert not style_of(model, 'normal').get('bold')
    assert style_of(model, 'schraeg').get('italic') is True
    for word in ('alt', 'weg', 'raus'):
        assert style_of(model, word).get('strike') is True, word


def test_PASTE_4():
    "PASTE-4: fetch_image reads data URIs and files (path, file://, relative)"
    data = png()
    uri = 'data:image/png;base64,' + base64.b64encode(data).decode()
    assert fetch_image(uri) == data
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, 'bild 1.png')
        with open(path, 'wb') as f:
            f.write(data)
        text = os.path.join(folder, 'notes.txt')
        with open(text, 'wb') as f:
            f.write(b'no image')
        assert fetch_image(path) == data
        assert fetch_image('file://' + path.replace(' ', '%20')) == data
        assert fetch_image('bild 1.png', folder) == data
        assert fetch_image(text) is None  # not an image
        assert fetch_image(os.path.join(folder, 'missing.png')) is None


def serve(folder):
    """A local web server for folder: (server, base URL)."""
    class Quiet(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kw):
            super().__init__(*args, directory=folder, **kw)

        def log_message(self, *args):
            pass
    server = HTTPServer(('127.0.0.1', 0), Quiet)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, 'http://127.0.0.1:%d/' % server.server_port


def test_PASTE_5():
    "PASTE-5: fetch_image loads from the web; not found gives None"
    data = png()
    with tempfile.TemporaryDirectory() as folder:
        with open(os.path.join(folder, 'wal.png'), 'wb') as f:
            f.write(data)
        server, url = serve(folder)
        try:
            assert fetch_image(url + 'wal.png') == data
            assert fetch_image(url + 'missing.png') is None
        finally:
            server.shutdown()


def test_PASTE_6():
    "PASTE-6: pasted HTML: data URIs embedded, paths and URLs linked"
    data = png()
    uri = 'data:image/png;base64,' + base64.b64encode(data).decode()
    model, images = pasted('<p>A <img src="%s" alt="Eins"> B '
                           '<img src="/x/wal.png" alt="Wal"> C '
                           '<img src="https://x.org/b.png"></p>' % uri)
    assert [(i.content, i.path, i.alt) for i in images] == [
        (data, None, 'Eins'), (None, '/x/wal.png', 'Wal'),
        (None, 'https://x.org/b.png', '')]
    assert model.get_text().startswith('A \x0c B \x0c C')


def test_PASTE_7():
    "PASTE-7: Markdown images: linked, pasted and imported; saved as paths"
    from ..plugins import mdfilter
    from ..images import imageio
    data = png()
    with tempfile.TemporaryDirectory() as folder:
        with open(os.path.join(folder, 'wal.png'), 'wb') as f:
            f.write(data)
        model = TextModel('')
        model.texel = md_text_to_fragment(
            'Ein ![Wal](https://x.org/wal.png) !\n', Document())
        assert [(i.content, i.path) for i in iter_images(model.texel)] \
            == [(None, 'https://x.org/wal.png')]
        md = os.path.join(folder, 'text.md')
        text = '# Titel\n\n![Wal](wal.png)\n'  # relative
        with open(md, 'w') as f:
            f.write(text)
        import sys
        for mistune in (sys.modules.get('mistune'), None):
            saved = sys.modules.get('mistune')
            sys.modules['mistune'] = mistune  # None: built-in parser
            try:
                document = mdfilter._load(md)
            finally:
                sys.modules['mistune'] = saved
            images = list(iter_images(document.textmodel.texel))
            assert [(i.content, i.path) for i in images] == \
                [(None, 'wal.png')], mistune
            assert imageio.external_content('wal.png', folder) == data
            out = os.path.join(folder, 'out.md')
            mdfilter._save(document, out)
            assert open(out).read() == text  # the README stays as it was


def test_PASTE_10():
    "PASTE-10: load_urls loads the web images of a pasted fragment"
    from ..images import imageio
    data = png(6)
    with tempfile.TemporaryDirectory() as folder:
        with open(os.path.join(folder, 'wal.png'), 'wb') as f:
            f.write(data)
        server, url = serve(folder)
        try:
            model, images = pasted('<img src="%swal.png"> <img src="x.png">'
                                   % url)
            assert imageio.external_content(url + 'wal.png') is None
            assert imageio.load_urls(model.texel) == 0  # none failed
            assert imageio.external_content(url + 'wal.png') == data
            model, images = pasted('<img src="%smissing.png">' % url)
            assert imageio.load_urls(model.texel) == 1
        finally:
            server.shutdown()


def test_PASTE_8():
    "PASTE-8: with_bitmap embeds the bitmap only into a lone image"
    from ..ui.mainwindow import with_bitmap
    bitmap = png(8)
    model, _ = pasted('<img src="https://x.org/wal.webp" alt="Wal">')
    images = list(iter_images(with_bitmap(model.texel, bitmap)))
    assert [(i.content, i.path, i.alt) for i in images] == \
        [(bitmap, 'https://x.org/wal.webp', 'Wal')]
    for html in ('<p>Text <img src="a.png"></p>',     # Office: a preview
                 '<img src="a.png"><img src="b.png">', '<p>nur Text</p>'):
        model, _ = pasted(html)
        assert with_bitmap(model.texel, bitmap) is model.texel, html


def test_PASTE_9():
    "PASTE-9: the canvas leaves Ctrl+V to the menu (paste with HTML)"
    from ..texteditor.editor import Editor
    from ..texteditor.textcanvas import TextCanvas
    from ..layout.pagebuilder import PageBuilder
    from ..layout.rowfactory import Factory
    from ..layout.cairodevice import CairoDevice
    app()
    frame = wx.Frame(None)
    try:
        document = Document()
        model = document.textmodel
        builder = PageBuilder(
            model, Factory(document.basestyles, device=CairoDevice()))
        builder.settings = document.settings
        builder.rebuild()
        editor = Editor(model)
        canvas = TextCanvas(frame, model, builder, editor)
        editor.canvas = canvas
        event = wx.KeyEvent(wx.wxEVT_CHAR)
        event.SetKeyCode(22)  # Ctrl+V
        event.SetControlDown(True)
        event.Skip(False)
        canvas.on_char(event)
        assert event.GetSkipped()
    finally:
        frame.Destroy()


class FakeClipboard:
    """Stands in for the canvas' clipboard access: {flavor: bytes}, an
    image (PNG data) and plain text."""
    def __init__(self, data=None, image=None, text=None):
        self.data, self.image, self.text = data or {}, image, text

    def install(self, canvas):
        canvas.read_clipboard_data = self.data.get
        canvas.read_clipboard_image = lambda: self.image
        canvas.read_clipboard_text = lambda: self.text
        canvas.read_clipboard = lambda: self.text and TextModel(self.text)


def clear(frame):
    """Remove the whole text, through the editor (moves the cursor)."""
    frame.editor.selection = (0, len(frame.document.textmodel))
    frame.editor.remove()


def main_frame():
    from ..ui.mainwindow import MainFrame
    app()
    return MainFrame(Document())


def test_PASTE_11():
    "PASTE-11: paste: a registered flavor (a lone image with the bitmap), "
    "else the bitmap, else text"
    frame = main_frame()
    try:
        model = frame.document.textmodel
        FakeClipboard({'html': b'<h2>Titel</h2>'}, png()).install(
            frame.editor.canvas)
        frame.paste()
        assert model.get_text() == 'Titel\n'
        clear(frame)
        image = png(8)
        FakeClipboard({'html': b'<img src="x.png">'}, image).install(
            frame.editor.canvas)
        frame.paste()  # just an image: the bitmap, with its origin
        assert [(i.content, i.path) for i in iter_images(model.texel)] \
            == [(image, 'x.png')]
        clear(frame)
        FakeClipboard({}, image).install(frame.editor.canvas)
        frame.paste()  # a screenshot
        assert [(i.content, i.path) for i in iter_images(model.texel)] \
            == [(image, None)]
        clear(frame)
        FakeClipboard(text='plain').install(frame.editor.canvas)
        frame.paste()
        assert model.get_text() == 'plain'
    finally:
        frame.Destroy()


def test_PASTE_12():
    "PASTE-12: plugins register 'Paste from ...'; the Edit menu lists it"
    from ..io.importexport import paste_as_handlers
    frame = main_frame()
    try:
        labels = [label for label, _ in paste_as_handlers()]
        assert 'Paste from &Markdown' in labels
        bar = frame.GetMenuBar()
        edit = bar.GetMenu(bar.FindMenu('Edit'))
        texts = [item.GetItemLabel() for item in edit.GetMenuItems()]
        assert 'Paste from &Markdown' in texts
        assert texts.index('Paste from &Markdown') == \
            texts.index('&Paste\tCtrl+V') + 1
        FakeClipboard(text='# Titel\n').install(frame.editor.canvas)
        item = edit.FindItemByPosition(texts.index('Paste from &Markdown'))
        frame.ProcessEvent(wx.CommandEvent(wx.wxEVT_MENU, item.GetId()))
        model = frame.document.textmodel
        assert model.get_text() == 'Titel\n'
        assert model.get_parstyle(0).get('base') == 'h1'
    finally:
        frame.Destroy()


def test_PASTE_13():
    "PASTE-13: width/height of an <img> become its scale"
    data = png(10)  # 10 x 2 pixels
    uri = 'data:image/png;base64,' + base64.b64encode(data).decode()
    for attrs, scale in (('width="5"', (0.5, 0.5)),
                         ('height="4px"', (2.0, 2.0)),
                         ('width="20" height="1"', (2.0, 0.5)),
                         ('width="50%"', (1.0, 1.0)), ('', (1.0, 1.0))):
        _, images = pasted('<img src="%s" %s>' % (uri, attrs))
        assert (images[0].scale_x, images[0].scale_y) == scale, attrs


def test_PASTE_14():
    "PASTE-14: pasting loads web images at once, so their size is known"
    from ..plugins.htmlfilter import html_clipboard_fragment
    from ..images import imageio
    data = png(40)
    with tempfile.TemporaryDirectory() as folder:
        with open(os.path.join(folder, 'gross.png'), 'wb') as f:
            f.write(data)
        server, url = serve(folder)
        try:
            html = '<p>A <img src="%sgross.png" width="10"></p>' % url
            _, images = pasted(html)  # import: no web access
            assert imageio.external_content(url + 'gross.png') is None
            assert images[0].scale_x == 1.0
            texel = html_clipboard_fragment(html.encode(), Document())
            image, = iter_images(texel)
            assert (image.content, image.path) == (None, url + 'gross.png')
            assert image.scale_x == 0.25
        finally:
            server.shutdown()


def test_PASTE_15():
    "PASTE-15: the bitmap of a lone image shows as large as the image"
    from ..ui.mainwindow import with_bitmap
    from ..images import imageio
    from ..images.images import Image
    from ..textmodel.texeltree import grouped
    url = 'https://x.org/klein.png'
    imageio.external[url] = png(250, 100)  # as if loaded
    try:
        texel = grouped([Image(path=url, scale_x=0.8, scale_y=0.8)])
        image, = iter_images(with_bitmap(texel, png(500, 200)))  # Hi-DPI
        assert image.content is not None and image.path == url
        assert (image.scale_x, image.scale_y) == (0.4, 0.4)
    finally:
        del imageio.external[url]
    texel = grouped([Image(path='https://x.org/unbekannt.png')])
    image, = iter_images(with_bitmap(texel, png(500)))
    assert image.scale_x == 1.0  # size unknown: the bitmap as it is
