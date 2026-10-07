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
from ..plugins.htmlfilter import clipboard_html, html_text_to_fragment, \
    paste_html
from ..plugins.mdfilter import md_text_to_fragment
from ..textmodel.textmodel import TextModel
from .guitest import app


def png(width=2):
    """PNG data of a small image."""
    app()
    stream = io.BytesIO()
    wx.Image(width, 2).SaveFile(stream, wx.BITMAP_TYPE_PNG)
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
    "PASTE-6: pasted HTML loads its images; else the alt text as a link"
    data = png()
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, 'wal.png')
        with open(path, 'wb') as f:
            f.write(data)
        model, images = pasted('<p>Ein <img src="%s" alt="Wal"> !</p>'
                               % path)
        assert [image.content for image in images] == [data]
        model, images = pasted('<p><img src="%s" alt="Wal"></p>'
                               % os.path.join(folder, 'missing.png'))
        assert images == [] and 'Wal' in model.get_text()
        assert style_of(model, 'Wal').get('href', '').endswith('missing.png')


def test_PASTE_7():
    "PASTE-7: Markdown images from files and the web, pasted and imported"
    from ..plugins import mdfilter
    data = png()
    with tempfile.TemporaryDirectory() as folder:
        with open(os.path.join(folder, 'wal.png'), 'wb') as f:
            f.write(data)
        server, url = serve(folder)
        try:
            for src in (os.path.join(folder, 'wal.png'), url + 'wal.png'):
                model = TextModel('')
                model.texel = md_text_to_fragment(
                    'Ein ![Wal](%s) !\n' % src, Document())
                assert [i.content for i in iter_images(model.texel)] \
                    == [data], src
            md = os.path.join(folder, 'text.md')
            with open(md, 'w') as f:
                f.write('# Titel\n\n![Wal](wal.png)\n')  # relative
            import sys
            for mistune in (sys.modules.get('mistune'), None):
                saved = sys.modules.get('mistune')
                sys.modules['mistune'] = mistune  # None: built-in parser
                try:
                    document = mdfilter._load(md)
                finally:
                    sys.modules['mistune'] = saved
                assert [i.content for i in iter_images(
                    document.textmodel.texel)] == [data], mistune
        finally:
            server.shutdown()


def test_PASTE_8():
    "PASTE-8: an image alone on the clipboard is pasted as its bitmap"
    data = png()
    uri = 'data:image/png;base64,' + base64.b64encode(data).decode()
    browser = '<meta charset="utf-8"><img src="https://x.org/wal.webp">'
    assert paste_html(browser, data) == '<img src="%s">' % uri
    assert paste_html(None, data) == '<img src="%s">' % uri  # screenshot
    text = '<p>Text <img src="https://x.org/wal.webp"></p>'
    assert paste_html(text, data) == text  # more than the image
    assert paste_html(text, None) == text
    assert paste_html(None, None) is None


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
