# -*- coding: utf-8 -*-

"""
Tests for images, following develnotes/images_tests.md (concept:
develnotes/images_concept.md). Each test's docstring starts with its ID.

Run with: python runtests.py miniword/tests/test_images.py

Written ahead of the implementation: many tests fail until the concept
is implemented. They assume this API (adjust here if the
implementation chooses differently):

- images.Image(content=None, scale_x=1.0, scale_y=1.0,
  proportional=True, crop=None): content are the image's bytes;
  set_content, set_scale_x/_y, set_crop, set_proportional return copies.
- images.blob_key(content): first 16 hex digits of SHA-256 plus the
  extension found from the content's magic bytes (.png, .jpg, .gif,
  fallback .bin).
- imageio.decode_cached(content): decoded images via the
  application-wide LRU imageio.decoded (an OrderedDict keyed by content,
  bounded by memory: imageio.DECODED_LIMIT). No cache on the document.
- Saving/loading TXL (Document.save/Document.load) hydrates Image
  texels with their content; blob keys are blob_key(content).
- rowfactory.RowFactory(state, stylesheet, device) with an
  Image_handler: ImageBox from the decoded content (decode_cached),
  ErrorPlaceholderBox if there is none or it can't be decoded.
- PageBuilder(model, factory), factory being a rowfactory.Factory.
- image_controllers.resize_box(state, handle, dx, dy, proportional),
  image_controllers.scale_after_resize(old_state, new_state, scale_x,
  scale_y), image_controllers.drag_crop(crop, handle, dx, dy, scale,
  src_size), image_controllers.round_crop(crop): the calculations of
  ImageSizeController/ImageCropController as plain functions.
- image_panel.size_to_scale(changed, value, natural, scales,
  proportional): the calculation of ImagePanel._on_size.

Imports of the new API are done inside the tests, so that every test
fails on its own until its part is implemented.

Not covered here yet (concept step 4 and UI): FILE-7, CACHE-4,
RENDER-4, PANEL-2, PASTE-5..8, MDEXP, LINK.
"""

import io
import os
import hashlib
import tempfile

import wx

from ..textmodel.textmodel import TextModel
from ..textmodel.texeltree import T, grouped, length, NewLine
from ..core.document import Document
from ..core.stylesheet import testsheet
from ..images import imageio
from ..images.images import ImageBox, ErrorPlaceholderBox, ImageData
from ..layout.testdevice import TESTDEVICE
from ..layout.rowfactory import State, RowFactory, generate_pages, \
    Factory as RowFactoryBase


def app():
    if wx.App.Get() is None:
        wx.App(False)


# Test images

def png(w, h, rgb=(1, 0, 0)):
    """PNG bytes of a w x h image in colour rgb (0..1)."""
    import cairocffi as cairo
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    ctx = cairo.Context(surface)
    ctx.set_source_rgb(*rgb)
    ctx.paint()
    buf = io.BytesIO()
    surface.write_to_png(buf)
    return buf.getvalue()


def quadrants_png():
    """4 x 4 PNG: top left red, top right green, bottom left blue,
    bottom right white."""
    import cairocffi as cairo
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 4, 4)
    ctx = cairo.Context(surface)
    for x, y, rgb in ((0, 0, (1, 0, 0)), (2, 0, (0, 1, 0)),
                      (0, 2, (0, 0, 1)), (2, 2, (1, 1, 1))):
        ctx.set_source_rgb(*rgb)
        ctx.rectangle(x, y, 2, 2)
        ctx.fill()
    buf = io.BytesIO()
    surface.write_to_png(buf)
    return buf.getvalue()


def jpeg(w, h):
    app()
    image = wx.Image(w, h)
    image.SetData(bytes([200, 100, 50]) * (w * h))
    buf = io.BytesIO()
    image.SaveFile(buf, wx.BITMAP_TYPE_JPEG)
    return buf.getvalue()


GIF = b'GIF89a' + b'\x00' * 20  # magic bytes only, enough for blob_key


def pixel(surface, x, y):
    """(r, g, b) of an ARGB32 surface (stored as BGRA)."""
    surface.flush()
    stride = surface.get_stride()
    data = surface.get_data()
    i = y * stride + 4 * x
    b, g, r = bytes(data[i:i + 3])
    return r, g, b


def image(**kw):
    from ..images.images import Image
    return Image(**kw)


def mk_doc(*items):
    """Document of items (Image texels or strings), ending with ENDMARK."""
    doc = Document()
    texels = [T(item) if isinstance(item, str) else item for item in items]
    doc.textmodel.texel = grouped(texels)
    return doc


def roundtrip(doc):
    """Save doc to a temporary TXL file and load it again. Returns the
    loaded document and the file's text."""
    with tempfile.NamedTemporaryFile(suffix='.txl', delete=False) as f:
        path = f.name
    try:
        doc.save(path)
        with open(path, encoding='utf-8') as f:
            text = f.read()
        return Document.load(path), text
    finally:
        os.unlink(path)


def load_text(text):
    with tempfile.NamedTemporaryFile(suffix='.txl', delete=False,
                                     mode='w', encoding='utf-8') as f:
        f.write(text)
        path = f.name
    try:
        return Document.load(path)
    finally:
        os.unlink(path)


def images_in(texel):
    from ..images.images import Image
    from ..textmodel.utils import iter_leafes
    return [t for _, _, t in iter_leafes(texel, 0, True)
            if isinstance(t, Image)]


def sha_key(data, ext):
    return hashlib.sha256(data).hexdigest()[:16] + ext


class DecodeCounter:
    """Counts calls of imageio.decode while installed (with-statement).
    Starts with an empty application-wide cache."""
    def __enter__(self):
        imageio.decoded.clear()
        self.calls = 0
        self.original = imageio.decode
        def counting(data):
            self.calls += 1
            return self.original(data)
        imageio.decode = counting
        return self

    def __exit__(self, *args):
        imageio.decode = self.original


def boxes(texel, width=400):
    """All boxes RowFactory makes of texel."""
    factory = RowFactory(State(width), testsheet, TESTDEVICE)
    return [box for par in factory.generate(texel, 0)
            for record in par for box in record[0].childs]


def image_boxes(texel, width=400):
    return [box for box in boxes(texel, width)
            if isinstance(box, (ImageBox, ErrorPlaceholderBox))]


def par(*items):
    texels = [T(item) if isinstance(item, str) else item for item in items]
    return grouped(texels + [NewLine()])


# IMG - Texel

def test_IMG_1():
    "IMG-1: defaults"
    img = image()
    assert img.content is None
    assert (img.scale_x, img.scale_y) == (1.0, 1.0)
    assert img.crop is None
    assert img.proportional is True


def test_IMG_2():
    "IMG-2: setters return copies, the original stays unchanged"
    data = png(4, 2)
    img = image(content=data)
    for new in (img.set_content(png(2, 2)), img.set_scale_x(2.0),
                img.set_scale_y(3.0), img.set_crop((1, 0, 0, 0)),
                img.set_proportional(False)):
        assert new is not img
    assert img.content is data
    assert (img.scale_x, img.scale_y, img.crop, img.proportional) == \
        (1.0, 1.0, None, True)
    assert img.set_scale_x(2.0).content is data  # data shared, not copied


def test_IMG_3():
    "IMG-3: an image has length 1"
    assert length(image(content=png(2, 2))) == 1
    assert length(image()) == 1


def test_IMG_4():
    "IMG-4: content is immutable bytes; setters leave texel and data alone"
    data = png(4, 2)
    img = image(content=data)
    assert type(img.content) is bytes
    before = bytes(data)
    img.set_scale_x(2.0)
    img.set_crop((1, 1, 0, 0))
    img.set_content(png(2, 2))
    assert img.content is data and img.content == before


def test_IMG_5():
    "IMG-5: editing replaces the texel; undo restores the old one"
    from ..texteditor.editor import Editor
    data = png(4, 2)
    model = TextModel()
    model.texel = grouped([T('a'), image(content=data), T('b')])
    editor = Editor(model)
    old = images_in(model.texel)[0]

    editor.set_texel_attributes(1, old, scale_x=2.0)
    new = images_in(model.texel)[0]
    assert new is not old and new.scale_x == 2.0
    assert new.content is data

    editor.undo()
    restored = images_in(model.texel)[0]
    assert restored.scale_x == 1.0 and restored.content is data
    editor.redo()
    assert images_in(model.texel)[0].scale_x == 2.0


# MEM - image data in memory

def test_MEM_2():
    "MEM-2: loading an image used several times shares one object"
    data = png(4, 2)
    doc = mk_doc(image(content=data), 'x', image(content=data))
    doc2, text = roundtrip(doc)
    loaded = images_in(doc2.textmodel.texel)
    assert len(loaded) == 2
    assert loaded[0].content == data
    assert loaded[0].content is loaded[1].content


def data_uri(data):
    import base64
    return 'data:image/png;base64,' + base64.b64encode(data).decode('ascii')


def md_images(md):
    from ..plugins.mdfilter import md_text_to_fragment
    return images_in(md_text_to_fragment(md, Document()))


def html_images(html, doc=None):
    from ..plugins.htmlfilter import html_text_to_fragment
    return images_in(html_text_to_fragment(html, doc or Document()))


def test_MEM_1():
    "MEM-1: equal data in two objects: one blob, shared after reloading"
    data = png(4, 2)
    copy = bytes(bytearray(data))
    doc = mk_doc(image(content=data), 'x', image(content=copy))
    doc2, text = roundtrip(doc)
    assert text.count('"%s" = ' % sha_key(data, '.png')) == 1
    a, b = images_in(doc2.textmodel.texel)
    assert a.content is b.content


def test_MEM_3():
    "MEM-3: Markdown import of the same data URI twice shares one object"
    uri = data_uri(png(4, 2))
    a, b = md_images('![a](%s)\n\n![b](%s)\n' % (uri, uri))
    assert a.content is b.content
    assert (a.alt, b.alt) == ('a', 'b')


def test_MEM_4():
    "MEM-4: HTML import of the same data URI twice shares one object"
    uri = data_uri(png(4, 2))
    a, b = html_images('<p><img src="%s" alt="a"> <img src="%s"></p>'
                       % (uri, uri))
    assert a.content is b.content


# FILE - saving and loading TXL

def test_FILE_1():
    "FILE-1: save/load roundtrip keeps content, scaling and crop"
    a, b = png(4, 2), png(3, 3, (0, 0, 1))
    doc = mk_doc('x', image(content=a, scale_x=0.5, scale_y=0.25),
                 image(content=b, crop=(1, 0, 1, 0)), 'y')
    doc2, text = roundtrip(doc)
    loaded = images_in(doc2.textmodel.texel)
    assert [img.content for img in loaded] == [a, b]
    assert (loaded[0].scale_x, loaded[0].scale_y) == (0.5, 0.25)
    assert loaded[1].crop == (1, 0, 1, 0)


def test_FILE_2():
    "FILE-2: blob keys are SHA-256[:16] plus extension from magic bytes"
    from ..images.images import blob_key
    data_png, data_jpg = png(2, 2), jpeg(2, 2)
    assert blob_key(data_png) == sha_key(data_png, '.png')
    assert blob_key(data_jpg) == sha_key(data_jpg, '.jpg')
    assert blob_key(GIF) == sha_key(GIF, '.gif')
    assert blob_key(b'unknown') == sha_key(b'unknown', '.bin')

    doc = mk_doc(image(content=data_png))
    doc2, text = roundtrip(doc)
    key = sha_key(data_png, '.png')
    assert 'IMG("%s"' % key in text or "IMG('%s'" % key in text
    assert '"%s" = ' % key in text


def test_FILE_3():
    "FILE-3: the same content at several places: one blob in the file"
    data = png(4, 2)
    doc = mk_doc(image(content=data), 'x', image(content=bytes(data)))
    doc2, text = roundtrip(doc)
    assert text.count('"%s" = ' % sha_key(data, '.png')) == 1


def test_FILE_4():
    "FILE-4: a removed image leaves no blob in the file"
    a, b = png(4, 2), png(3, 3, (0, 0, 1))
    doc = mk_doc(image(content=a), 'x')
    doc.textmodel.insert(1, TextModel('y'))
    doc2, text = roundtrip(doc)
    assert sha_key(a, '.png') in text
    assert sha_key(b, '.png') not in text


def test_FILE_5():
    "FILE-5: old files with file names as blob keys load correctly"
    data = png(4, 2)
    doc2, text = roundtrip(mk_doc(image(content=data), 'x'))
    old_style = text.replace(sha_key(data, '.png'), 'photo.png')
    assert 'photo.png' in old_style
    doc3 = load_text(old_style)
    assert images_in(doc3.textmodel.texel)[0].content == data


def test_FILE_6():
    "FILE-6: a missing blob loads as an image without content"
    data = png(4, 2)
    doc2, text = roundtrip(mk_doc(image(content=data), 'x'))
    start = text.index('[blobs]')
    end = text.index('[document]')
    doc3 = load_text(text[:start] + text[end:])
    assert images_in(doc3.textmodel.texel)[0].content is None


def test_FILE_8():
    "FILE-8: saving doesn't change the document"
    data = png(4, 2)
    doc = mk_doc(image(content=data), 'x')
    texel = doc.textmodel.texel
    img = images_in(texel)[0]
    roundtrip(doc)
    assert doc.textmodel.texel is texel
    assert images_in(doc.textmodel.texel)[0] is img
    assert img.content is data


# CACHE - application-wide image caches

def test_CACHE_1():
    "CACHE-1: every image is decoded only once"
    data = png(4, 2)
    texel = par('a', image(content=data), 'b', image(content=data))
    with DecodeCounter() as counter:
        image_boxes(texel)
        image_boxes(texel)
    assert counter.calls == 1


def test_CACHE_1b():
    "CACHE-1b: equal content in different bytes objects is decoded once"
    data = png(4, 2)
    copy = bytes(bytearray(data))
    assert copy is not data
    texel = par(image(content=data), image(content=copy))
    with DecodeCounter() as counter:
        image_boxes(texel)
    assert counter.calls == 1


def test_CACHE_2():
    "CACHE-2: two views, two documents with the same image: decoded once"
    from ..layout.pagebuilder import PageBuilder
    app()
    data = png(4, 2)
    doc1 = mk_doc('a', image(content=data), 'b')
    doc2 = mk_doc('c', image(content=bytes(bytearray(data))))
    with DecodeCounter() as counter:
        for doc in (doc1, doc1, doc2):
            builder = PageBuilder(doc.textmodel,
                                  RowFactoryBase(testsheet, TESTDEVICE))
            builder.rebuild()
            builder.assure_finished()
    assert counter.calls == 1


def test_CACHE_3():
    "CACHE-3: no image cache in the State/restart memo or the document"
    data = png(4, 2)
    texel = par('a', image(content=data))
    pages = list(generate_pages(texel, 0, State(400), testsheet,
                                TESTDEVICE))
    for page in pages:
        memo = page.restartmemo
        assert all(value is not imageio.decoded
                   for value in vars(memo).values())
    assert not hasattr(Document(), 'image_cache')


def test_CACHE_5():
    "CACHE-5: the LRU keeps its memory limit, dropping the oldest"
    images = [png(10, 10, (k / 4, 0, 0)) for k in range(4)]
    def size(data):
        return len(data) + 4 * 10 * 10  # content plus decoded pixels
    old_limit = imageio.DECODED_LIMIT
    try:
        imageio.decoded.clear()
        imageio.DECODED_LIMIT = sum(size(images[k]) for k in (0, 2, 3))
        for data in images[:3]:
            imageio.decode_cached(data)
        imageio.decode_cached(images[0])  # now the most recently used
        imageio.decode_cached(images[3])  # drops the oldest: images[1]
        assert list(imageio.decoded) == [images[2], images[0], images[3]]
        imageio.DECODED_LIMIT = 1  # smaller than one image: newest stays
        imageio.decode_cached(images[1])
        assert list(imageio.decoded) == [images[1]]
    finally:
        imageio.DECODED_LIMIT = old_limit
        imageio.decoded.clear()


def test_CACHE_6():
    "CACHE-6: data that can't be decoded is tried only once"
    with DecodeCounter() as counter:
        assert imageio.decode_cached(b'no image at all') is None
        assert imageio.decode_cached(b'no image at all') is None
    assert counter.calls == 1


# RENDER - RowFactory.Image_handler

def test_RENDER_1():
    "RENDER-1: an ImageBox of source size times scale"
    box, = image_boxes(par(image(content=png(40, 20), scale_x=0.5,
                                 scale_y=2.0)))
    assert isinstance(box, ImageBox)
    assert (box.width, box.height) == (20, 40)


def test_RENDER_2():
    "RENDER-2: with crop: size of the cut-out times scale"
    img = image(content=png(40, 20), crop=(5, 5, 0, 10), scale_x=2.0,
                scale_y=2.0)
    box, = image_boxes(par(img))
    assert (box.width, box.height) == (60, 20)


def test_RENDER_3():
    "RENDER-3: no content (and no path): a placeholder"
    box, = image_boxes(par(image()))
    assert isinstance(box, ErrorPlaceholderBox)


def test_RENDER_5():
    "RENDER-5: content that can't be decoded: a placeholder, no exception"
    box, = image_boxes(par(image(content=b'no image at all')))
    assert isinstance(box, ErrorPlaceholderBox)


def test_RENDER_6():
    "RENDER-6: row lengths are right with images (length 1)"
    from ..textmodel.utils import iter_paragraphs
    data = png(4, 2)
    texel = grouped([par('ab', image(content=data), 'cd'),
                     par(image(content=data))])
    factory = RowFactory(State(400), testsheet, TESTDEVICE)
    paragraphs = list(factory.generate(texel, 0))
    for (i1, i2, _), records in zip(iter_paragraphs(texel, 0), paragraphs):
        assert sum(len(r[0]) for r in records) == i2 - i1


def test_RENDER_7():
    "RENDER-7: an image taller than the page is placed, pages progress"
    memo = State(80)
    memo.geometry = (82, 22)
    memo.border = (1, 1, 1, 1)
    texel = grouped([par('a'), par(image(content=png(10, 500))),
                     par('b')])
    pages = list(generate_pages(texel, 0, memo, testsheet, TESTDEVICE))
    assert sum(len(p) for p in pages) == length(texel)


# PROC - image processing (imageio)

def test_PROC_1():
    "PROC-1: crop_surface cuts out the right region"
    data = imageio.decode(quadrants_png())
    part = imageio.crop_surface(data.bitmap, 2, 0, 2, 2)
    assert (part.get_width(), part.get_height()) == (2, 2)
    for x in range(2):
        for y in range(2):
            assert pixel(part, x, y) == (0, 255, 0), (x, y)
    part = imageio.crop_surface(data.bitmap, 1, 1, 2, 2)
    assert pixel(part, 0, 0) == (255, 0, 0)
    assert pixel(part, 1, 1) == (255, 255, 255)


def test_PROC_2():
    "PROC-2: decode gives size and bitmap; invalid data gives None"
    data = imageio.decode(png(40, 20))
    assert isinstance(data, ImageData)
    assert (data.width_px, data.height_px) == (40, 20)
    assert data.bitmap is not None
    data = imageio.decode(jpeg(30, 10))
    assert (data.width_px, data.height_px) == (30, 10)
    assert imageio.decode(b'no image at all') is None


# SIZE - resizing (ImageSizeController)

STATE = ((0, 0), 100, 50)


def resize(handle, dx, dy, proportional=False):
    from ..images.image_controllers import resize_box
    return resize_box(STATE, handle, dx, dy, proportional)


def test_SIZE_1():
    "SIZE-1: right/bottom handle grows and shrinks, at least 1"
    assert resize('E', 20, 0) == ((0, 0), 120, 50)
    assert resize('S', 0, -10) == ((0, 0), 100, 40)
    assert resize('SE', 10, 5) == ((0, 0), 110, 55)
    assert resize('E', -500, 0)[1] == 1
    assert resize('S', 0, -500)[2] == 1


def test_SIZE_2():
    "SIZE-2: left/top handle moves the origin and shrinks, not below 1"
    assert resize('W', 30, 0) == ((30, 0), 70, 50)
    assert resize('N', 0, 10) == ((0, 10), 100, 40)
    (x, y), w, h = resize('W', 500, 0)
    assert w == 1 and x == 99
    (x, y), w, h = resize('N', 0, 500)
    assert h == 1 and y == 49


def test_SIZE_3():
    "SIZE-3: proportional keeps the aspect ratio, edges stay centred"
    for handle, dx, dy in (('SE', 20, 3), ('SE', 2, 30), ('NW', 10, 2),
                           ('E', 20, 0), ('S', 0, 10)):
        (x, y), w, h = resize(handle, dx, dy, proportional=True)
        assert abs(w / h - 2.0) < 1e-9, (handle, w, h)
    (x, y), w, h = resize('E', 20, 0, proportional=True)
    assert abs(y - (50 - h) / 2) < 1e-9  # centred vertically
    (x, y), w, h = resize('S', 0, 10, proportional=True)
    assert abs(x - (100 - w) / 2) < 1e-9  # centred horizontally


def test_SIZE_4():
    "SIZE-4: committing gives the right scale (also cropped), undo works"
    from ..images.image_controllers import scale_after_resize
    from ..texteditor.editor import Editor
    # a cropped image shown 60 x 20 (cut-out 30 x 10, scale 2.0)
    old, new = ((0, 0), 60, 20), ((0, 0), 90, 10)
    assert scale_after_resize(old, new, 2.0, 2.0) == (3.0, 1.0)

    model = TextModel()
    img = image(content=png(40, 20), crop=(5, 5, 0, 10), scale_x=2.0,
                scale_y=2.0)
    model.texel = grouped([img])
    editor = Editor(model)
    editor.set_texel_attributes(0, img, scale_x=3.0, scale_y=1.0)
    assert images_in(model.texel)[0].scale_x == 3.0
    editor.undo()
    assert images_in(model.texel)[0].scale_x == 2.0


# CROP - cropping (ImageCropController)

def drag(handle, dx, dy, crop=(0, 0, 0, 0), scale=(2.0, 2.0),
         src=(40, 20)):
    from ..images.image_controllers import drag_crop
    return tuple(drag_crop(list(crop), handle, dx, dy, scale, src))


def test_CROP_1():
    "CROP-1: dragging an edge changes just its value, divided by scale"
    assert drag('L', 10, 0) == (5, 0, 0, 0)
    assert drag('R', -10, 0) == (0, 5, 0, 0)
    assert drag('T', 0, 4) == (0, 0, 2, 0)
    assert drag('B', 0, -4) == (0, 0, 0, 2)


def test_CROP_2():
    "CROP-2: no negative crop, at least 1 pixel remains"
    assert drag('L', -10, 0) == (0, 0, 0, 0)
    assert drag('R', 10, 0) == (0, 0, 0, 0)
    cl, cr, ct, cb = drag('L', 1000, 0, crop=(0, 10, 0, 0))
    assert 40 - cl - cr == 1
    cl, cr, ct, cb = drag('B', 0, -1000, crop=(0, 0, 5, 0))
    assert 20 - ct - cb == 1


def test_CROP_3():
    "CROP-3: commit rounds to whole pixels and sets crop; undo works"
    from ..images.image_controllers import round_crop
    from ..texteditor.editor import Editor
    assert round_crop([1.4, 2.6, 0.5, 3.0]) in ((1, 3, 0, 3), (1, 3, 1, 3))
    assert all(type(v) is int for v in round_crop([1.4, 2.6, 0.5, 3.0]))

    model = TextModel()
    img = image(content=png(40, 20))
    model.texel = grouped([img])
    editor = Editor(model)
    editor.set_texel_attributes(0, img, crop=(1, 3, 0, 3))
    assert images_in(model.texel)[0].crop == (1, 3, 0, 3)
    editor.undo()
    assert images_in(model.texel)[0].crop is None


def test_CROP_4():
    "CROP-4: unset crop gives crop None"
    from ..texteditor.editor import Editor
    model = TextModel()
    img = image(content=png(40, 20), crop=(1, 1, 1, 1))
    model.texel = grouped([img])
    editor = Editor(model)
    editor.set_texel_attributes(0, img, crop=None)
    assert images_in(model.texel)[0].crop is None


# PANEL - inputs in the image panel

def test_PANEL_1():
    "PANEL-1: size <-> scale via the natural size, coupled if proportional"
    from ..images.image_panel import size_to_scale
    natural = (30, 10)  # natural size of the (cut-out) image
    assert size_to_scale('x', 60, natural, (1.0, 1.0), True) == (2.0, 2.0)
    assert size_to_scale('x', 60, natural, (1.0, 0.5), False) == \
        (2.0, 0.5)
    assert size_to_scale('y', 5, natural, (1.0, 1.0), True) == (0.5, 0.5)
    assert size_to_scale('y', 5, natural, (3.0, 1.0), False) == \
        (3.0, 0.5)


# PASTE - copy & paste, import

def test_PASTE_1():
    "PASTE-1: an image copied from A to B (via pickle) keeps its data"
    import pickle
    data = png(4, 2)
    a = mk_doc('x', image(content=data, alt='Photo'), 'y')
    clip = pickle.loads(pickle.dumps(a.textmodel.copy(1, 2)))
    b = mk_doc('abc')
    b.textmodel.insert(1, clip)
    img, = images_in(b.textmodel.texel)
    assert img.content == data and img.alt == 'Photo'
    b2, text = roundtrip(b)
    assert images_in(b2.textmodel.texel)[0].content == data


def test_PASTE_2():
    "PASTE-2: HTML paste doesn't overwrite an existing image"
    old, new = png(4, 2), png(3, 3, (0, 0, 1))
    doc = mk_doc(image(content=old, alt='photo.png'), 'x')
    img, = html_images('<p><img src="%s" alt="photo.png"></p>'
                       % data_uri(new), doc)
    assert img.content == new
    assert images_in(doc.textmodel.texel)[0].content is old


def test_PASTE_3():
    "PASTE-3: two different images with the same name both survive"
    a, b = png(4, 2), png(3, 3, (0, 0, 1))
    x, y = html_images('<p><img src="%s" alt="photo.png">'
                       '<img src="%s" alt="photo.png"></p>'
                       % (data_uri(a), data_uri(b)))
    assert (x.content, y.content) == (a, b)


def test_PASTE_4():
    "PASTE-4: Markdown import of a data URI gives an image with content"
    data = png(4, 2)
    img, = md_images('Text ![Photo](%s) more.\n' % data_uri(data))
    assert img.content == data and img.alt == 'Photo'


# PB - PageBuilder and app

def page_sig(page):
    def box_sig(box):
        return (type(box).__name__, len(box), box.width, box.height)
    return (len(page), [[box_sig(b) for b in row.childs]
                        for _, _, row in page.rows])


def mk_builder(model):
    from ..layout.pagebuilder import PageBuilder
    builder = PageBuilder(model, RowFactoryBase(testsheet, TESTDEVICE))
    builder.settings = {
        'paper': 'custom', 'paper_width': 60, 'paper_height': 40,
        'margin_top': 1, 'margin_right': 1, 'margin_bottom': 1,
        'margin_left': 1,
    }
    builder.rebuild()
    builder.assure_finished()
    return builder


def test_PB_1():
    "PB-1: the PageBuilder shows images with a rowfactory.Factory"
    app()
    model = TextModel()
    model.texel = grouped([T('a'), image(content=png(10, 5)), T('b')])
    builder = mk_builder(model)
    boxes = [box for page in builder._layout.childs
             for _, _, row in page.rows for box in row.childs]
    assert any(isinstance(box, ImageBox) for box in boxes)


def test_PB_2():
    "PB-2: editing images updates the layout like a full rebuild"
    from ..texteditor.editor import Editor
    app()
    model = TextModel('\n'.join('paragraph %d' % k for k in range(30)))
    builder = mk_builder(model)
    model.add_view(builder)
    editor = Editor(model)

    def check():
        builder.assure_finished()
        expected = [page_sig(p) for p in mk_builder(model)
                    ._layout.childs]
        assert [page_sig(p) for p in builder._layout.childs] == expected

    editor.index = 25
    editor.insert_texel(image(content=png(20, 15)))
    check()
    img = images_in(model.texel)[0]
    editor.set_texel_attributes(25, img, scale_x=2.0, scale_y=2.0)
    check()
    img = images_in(model.texel)[0]
    editor.set_texel_attributes(25, img, crop=(5, 5, 0, 0))
    check()
    editor.selection = (25, 26)
    editor.remove()
    check()
    assert images_in(model.texel) == []


def test_PB_3():
    "PB-3: undo/redo of image edits"
    from ..texteditor.editor import Editor
    app()
    model = TextModel('abc')
    builder = mk_builder(model)
    model.add_view(builder)
    editor = Editor(model)
    editor.index = 1
    editor.insert_texel(image(content=png(20, 15)))
    img = images_in(model.texel)[0]
    editor.set_texel_attributes(1, img, scale_x=2.0)
    editor.undo()
    assert images_in(model.texel)[0].scale_x == 1.0
    editor.undo()
    assert images_in(model.texel) == []
    editor.redo()
    editor.redo()
    assert images_in(model.texel)[0].scale_x == 2.0
    builder.assure_finished()
    assert [page_sig(p) for p in builder._layout.childs] == \
        [page_sig(p) for p in mk_builder(model)._layout.childs]
