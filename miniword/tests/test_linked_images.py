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
    "LINK-2: TXL keeps the path; a linked image has no blob"
    from ..core.document import Document
    from ..io import txlio
    from ..images.images import iter_images
    from ..textmodel.texeltree import grouped
    data = png()
    doc = Document()
    doc.textmodel.insert_text(0, 'x\n')
    model = doc.textmodel.create_textmodel()
    model.texel = grouped([Image(path='wal.png', alt='Wal'),
                           Image(data, path='https://x.org/a.png')])
    doc.textmodel.insert(0, model)
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, 'doc.txl')
        txlio.save(doc, path)
        text = open(path, encoding='utf-8').read()
        assert text.count('[blobs]') == 1 and text.count('.png"') >= 1
        images = list(iter_images(txlio.load(path).textmodel.texel))
    assert [(i.content, i.path, i.alt) for i in images] == \
        [(None, 'wal.png', 'Wal'), (data, 'https://x.org/a.png', '')]


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
        write(folder, 'wal.png', data)
        factory = Factory(testsheet)
        factory.base_dir = folder
        box = factory.Image_handler(Image(path='wal.png', scale_x=0.5,
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
    "LINK-6: the window tells the layout the document's folder"
    from ..core.document import Document
    from ..ui.mainwindow import MainFrame
    app()
    frame = MainFrame(Document())
    try:
        factory = frame.canvas.builder.factory
        assert factory.base_dir == ''
        frame._current_path = '/home/x/texte/brief.txl'
        assert factory.base_dir == '/home/x/texte'
    finally:
        frame.Destroy()
