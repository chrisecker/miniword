# -*- coding: utf-8 -*-

"""
Tests for linked images (develnotes/images_concept.md, step 4a): the
Image texel's path, TXL, the cache for external images and rendering.
IDs LINK-n.

Run with: python runtests.py miniword/tests/test_linked_images.py
"""

import io
import os
import tempfile
import time

import wx

from ..core.stylesheet import testsheet
from ..images import imageio
from ..images.images import Image, ImageBox, ErrorPlaceholderBox
from ..layout.rowfactory import Factory
from .guitest import app
from .test_paste import serve


def png(width=4, height=2):
    app()
    stream = io.BytesIO()
    wx.Image(width, height).SaveFile(stream, wx.BITMAP_TYPE_PNG)
    return stream.getvalue()


def write(folder, name, data):
    path = os.path.join(folder, name)
    with open(path, 'wb') as f:
        f.write(data)
    return path


def test_LINK_1():
    "LINK-1: an image has a path (linked), set_path gives a copy"
    image = Image(path='bilder/wal.png', alt='Wal')
    assert image.content is None and image.path == 'bilder/wal.png'
    other = image.set_path('https://x.org/wal.png')
    assert other.path == 'https://x.org/wal.png'
    assert image.path == 'bilder/wal.png'
    assert Image().path is None


def test_LINK_2():
    "LINK-2: TXL: relative paths relative to the file, absolute ones kept"
    from ..core.document import Document
    from ..io import txlio
    from ..images.images import iter_images
    from ..textmodel.texeltree import grouped
    data = png()
    with tempfile.TemporaryDirectory() as folder:
        doc = Document()
        doc.textmodel.insert_text(0, 'x\n')
        model = doc.textmodel.create_textmodel()
        model.texel = grouped([
            Image(path=os.path.join(folder, 'bilder', 'wal.png'), alt='Wal',
                  relative=True),
            Image(path='/srv/logo.png'),
            Image(data, path='https://x.org/a.png')])
        doc.textmodel.insert(0, model)
        path = os.path.join(folder, 'doc.txl')
        txlio.save(doc, path)
        text = open(path, encoding='utf-8').read()
        assert 'path="bilder/wal.png"' in text
        assert 'path="/srv/logo.png"' in text
        assert text.count('[blobs]') == 1
        images = list(iter_images(txlio.load(path).textmodel.texel))
        assert [(i.content, i.path, i.relative, i.alt) for i in images] == [
            (None, os.path.join(folder, 'bilder', 'wal.png'), True, 'Wal'),
            (None, '/srv/logo.png', False, ''),
            (data, 'https://x.org/a.png', False, '')]


def test_LINK_3():
    "LINK-3: local files are read on demand, relative to base_dir, anew"
    first, second = png(4), png(6)
    with tempfile.TemporaryDirectory() as folder:
        write(folder, 'wal.png', first)
        assert imageio.external_content('wal.png', folder) == first
        time.sleep(0.01)
        write(folder, 'wal.png', second)
        os.utime(os.path.join(folder, 'wal.png'),
                 (time.time() + 5, time.time() + 5))  # surely newer
        assert imageio.external_content('wal.png', folder) == second
        absolute = os.path.join(folder, 'wal.png')
        assert imageio.external_content(absolute, '/elsewhere') == second
        assert imageio.external_content('missing.png', folder) is None


def test_LINK_4():
    "LINK-4: URLs only after load_url (no web access while laying out)"
    data = png()
    with tempfile.TemporaryDirectory() as folder:
        write(folder, 'wal.png', data)
        server, url = serve(folder)
        try:
            src = url + 'wal.png'
            assert imageio.external_content(src) is None
            assert imageio.load_url(src) is True
            assert imageio.external_content(src) == data
            assert imageio.load_url(url + 'missing.png') is False
        finally:
            server.shutdown()


def test_LINK_5():
    "LINK-5: linked images are drawn; missing ones as a labelled placeholder"
    data = png(40, 20)
    with tempfile.TemporaryDirectory() as folder:
        path = write(folder, 'wal.png', data)
        factory = Factory(testsheet)
        box = factory.Image_handler(Image(path=path, scale_x=0.5,
                                          scale_y=0.5), {})
        assert isinstance(box, ImageBox)
        assert (box.width, box.height) == (20, 10)
        box = factory.Image_handler(
            Image(path='https://x.org/bilder/wal.png'), {})
        assert isinstance(box, ErrorPlaceholderBox)
        assert box.label == 'wal.png' and box.width > 50
        box = factory.Image_handler(Image(), {})  # nothing at all
        assert isinstance(box, ErrorPlaceholderBox) and not box.label


def test_LINK_6():
    "LINK-6: the window tells the document its folder"
    from ..core.document import Document
    from ..ui.mainwindow import MainFrame
    app()
    frame = MainFrame(Document())
    try:
        assert frame.document.folder == ''
        frame._current_path = '/home/x/texte/brief.txl'
        assert frame.document.folder == '/home/x/texte'
    finally:
        frame.Destroy()


# ---------------------------------------------------------------------
# The image panel (step 4c)
# ---------------------------------------------------------------------

from contextlib import contextmanager


@contextmanager
def panel_with(image, folder=''):
    """(panel, frame): the image panel of a window whose document holds
    image, the cursor on it; the document lies in folder."""
    from ..core.document import Document
    from ..textmodel.texeltree import grouped
    from ..ui.mainwindow import MainFrame
    app()
    frame = MainFrame(Document())
    try:
        frame._current_path = os.path.join(folder, 'doc.txl')
        model = frame.document.textmodel.create_textmodel()
        model.texel = grouped([image])
        frame.document.textmodel.insert(0, model)
        frame.editor.index = 0
        panel = frame.image_inspector
        panel.update()
        yield panel, frame
    finally:
        frame.Destroy()


def image_at(frame):
    from ..images.images import iter_images
    return next(iter(iter_images(frame.document.textmodel.texel)))


def test_LINK_7():
    "LINK-7: only external images show their source; embedded as before"
    with panel_with(Image(png())) as (panel, frame):
        assert not panel.txt_path.IsShown()
        assert not panel.btn_embed.IsShown()
    with panel_with(Image(png(), path='https://x.org/a.png')) as (panel,
                                                                   frame):
        assert not panel.txt_path.IsShown()  # embedded, path just origin
    with panel_with(Image(path='wal.png')) as (panel, frame):
        assert panel.txt_path.IsShown() and panel.btn_embed.IsShown()
        assert panel.txt_path.GetValue() == 'wal.png'
        assert panel.lbl_status.GetLabel() == 'file not found'


def test_LINK_8():
    "LINK-8: Embed: the data goes into the document, the path stays origin"
    from .guitest import click_button
    data = png(10)
    with tempfile.TemporaryDirectory() as folder:
        path = write(folder, 'wal.png', data)
        with panel_with(Image(path=path), folder) as (panel, frame):
            click_button(panel.btn_embed)
            image = image_at(frame)
            assert (image.content, image.path) == (data, path)
            assert not panel.txt_path.IsShown()  # now an embedded image
            frame.editor.undo()
            assert image_at(frame).content is None


def test_LINK_9():
    "LINK-9: entering a path links it; a URL is loaded, its status shown"
    from .guitest import enter
    data = png(12)
    with tempfile.TemporaryDirectory() as folder:
        write(folder, 'wal.png', data)
        server, url = serve(folder)
        try:
            with panel_with(Image(path='alt.png')) as (panel, frame):
                enter(panel.txt_path, url + 'wal.png')
                assert image_at(frame).path == url + 'wal.png'
                assert imageio.external_content(url + 'wal.png') == data
                assert panel.lbl_status.GetLabel() == 'Loaded'
                frame.editor.index = 0
                enter(panel.txt_path, url + 'missing.png')
                assert image_at(frame).path == url + 'missing.png'
                assert 'HTTP 404' in panel.lbl_status.GetLabel()
        finally:
            server.shutdown()


def test_LINK_10():
    "LINK-10: a link: URL as it is; a file absolute, remembered as relative"
    from ..images.image_panel import link_source
    assert link_source(' https://x.org/a.png ', '/home/x') == \
        ('https://x.org/a.png', False)
    assert link_source('bilder/wal.png', '/home/x') == \
        ('/home/x/bilder/wal.png', True)
    assert link_source('/srv/wal.png', '/home/x') == ('/srv/wal.png', False)
    assert link_source('/srv/wal.png', '/home/x', browsed=True) == \
        ('/srv/wal.png', True)
    assert link_source('bilder/wal.png', '') == ('bilder/wal.png', False)
    assert link_source('  ', '/home/x') is None


def test_LINK_13():
    "LINK-13: loading errors say why, also on stdout"
    import contextlib
    with tempfile.TemporaryDirectory() as folder:
        write(folder, 'seite.html', b'<!DOCTYPE html><html>Bild</html>')
        write(folder, 'notes.txt', b'no image')
        server, url = serve(folder)
        try:
            from ..images.images import fetch
            data, error = fetch(url + 'seite.html')
            assert data is None and 'web page' in error
            assert 'HTTP 404' in fetch(url + 'missing.png')[1]
            assert 'not found' in fetch('missing.png', folder)[1]
            assert 'not an image' in fetch('notes.txt', folder)[1]
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                assert not imageio.load_url(url + 'seite.html')
            assert 'web page' in output.getvalue()
            assert 'web page' in imageio.errors[url + 'seite.html']
        finally:
            server.shutdown()


def test_LINK_14():
    "LINK-14: opening: a bar offers to load the web images, then they show"
    from .guitest import click_button
    with tempfile.TemporaryDirectory() as folder:
        write(folder, 'wal.png', png(30, 20))
        server, url = serve(folder)
        try:
            with panel_with(Image(path=url + 'wal.png')) as (panel, frame):
                frame._current_path = os.path.join(folder, 'text.md')
                assert frame.image_bar.IsShown()
                click_button(frame.image_bar.button)
                assert not frame.image_bar.IsShown()
                builder = frame.canvas.builder
                builder.assure_finished()
                assert [type(b) for b in boxes_in(builder)] == [ImageBox]
        finally:
            server.shutdown()


def test_LINK_15():
    "LINK-15: no bar without web images; a failed load shows its reason"
    from .guitest import click_button
    with tempfile.TemporaryDirectory() as folder:
        write(folder, 'wal.png', png())
        with panel_with(Image(path='wal.png')) as (panel, frame):
            frame._current_path = os.path.join(folder, 'text.md')
            assert not frame.image_bar.IsShown()
        server, url = serve(folder)
        try:
            with panel_with(Image(path=url + 'gone.png')) as (panel, frame):
                frame._current_path = os.path.join(folder, 'text.md')
                click_button(frame.image_bar.button)
                assert frame.image_bar.IsShown()
                assert 'HTTP 404' in frame.image_bar.text.GetLabel()
        finally:
            server.shutdown()


def test_LINK_16():
    "LINK-16: one 'Insert Image' button with a menu; no Replace"
    with panel_with(Image(png())) as (panel, frame):
        menu = panel.insert_menu()  # kept: a temporary would be freed
        labels = [item.GetItemLabelText() for item in menu.GetMenuItems()]
        assert labels == ['Embed Image from File…',
                          'Link to Image (File or URL)…']
        assert not hasattr(panel, 'btn_replace')
        assert panel.btn_export.IsEnabled()


def boxes_in(builder):
    """All image and placeholder boxes of the builder's pages."""
    found = []

    def walk(box):
        if isinstance(box, (ImageBox, ErrorPlaceholderBox)):
            found.append(box)
        elif hasattr(box, 'iter_boxes'):
            for *_, child in box.iter_boxes(0, 0, 0):
                walk(child)
    for *_, page in builder.layout.iter_boxes(0):
        walk(page)
    return found



def test_LINK_17():
    "LINK-17: Save As elsewhere: the image still shows, the file is right"
    from ..io import txlio
    data = png(30, 20)
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, 'a', 'bilder'))
        os.makedirs(os.path.join(root, 'b'))
        image = write(os.path.join(root, 'a', 'bilder'), 'wal.png', data)
        with panel_with(Image(path=image, relative=True),
                        os.path.join(root, 'a')) as (panel, frame):
            new = os.path.join(root, 'b', 'doc.txl')
            txlio.save(frame.document, new)
            frame._current_path = new
            assert 'path="../a/bilder/wal.png"' in open(new).read()
            builder = frame.canvas.builder
            builder.rebuild()
            builder.assure_finished()
            assert [type(b) for b in boxes_in(builder)] == [ImageBox]
            assert panel.txt_path.GetValue() == '../a/bilder/wal.png'


def test_LINK_18():
    "LINK-18: a linked image copied into a document elsewhere still shows"
    from ..core.document import Document
    from ..io import txlio
    from ..images.images import iter_images
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, 'a'))
        image = write(os.path.join(root, 'a'), 'wal.png', png())
        with panel_with(Image(path=image, relative=True),
                        os.path.join(root, 'a')) as (panel, frame):
            txlio.save(frame.document, os.path.join(root, 'a', 'doc.txl'))
            copied = txlio.load(os.path.join(root, 'a', 'doc.txl'))
        moved, = iter_images(copied.textmodel.texel)
        assert moved.path == image  # absolute in memory: valid anywhere


def test_LINK_19():
    "LINK-19: the panel's 'Relative to document' switches the kind"
    from .guitest import click
    with tempfile.TemporaryDirectory() as folder:
        image = write(folder, 'wal.png', png())
        with panel_with(Image(path=image, relative=True), folder) as (
                panel, frame):
            assert panel.chk_relative.GetValue()
            assert panel.txt_path.GetValue() == 'wal.png'
            click(panel.chk_relative, False)
            assert image_at(frame).relative is False
            assert panel.txt_path.GetValue() == image
        with panel_with(Image(path='https://x.org/a.png'), folder) as (
                panel, frame):
            assert not panel.chk_relative.IsEnabled()  # no file
