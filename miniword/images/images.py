"""
Inline image support: Image texel, boxes, inspector, tests.

Image texel parameters (see develnotes/images_concept.md):
    content  -- the image data (bytes), or None (linked or placeholder)
    path     -- linked: absolute file path or URL; with content it is
                just where the image came from
    relative -- the path is kept relative to the document in files
    alt      -- alternative text (Markdown, HTML), default ''
    scale_x  -- horizontal scale factor, default 1.0
    scale_y  -- vertical scale factor, default 1.0
    crop     -- (left, right, top, bottom) margins in source pixels, or
                None for the full image

Texels and their data are immutable: editing an image means inserting
a new texel (with new data for pixel operations).

TXL format: the data lives in the file's [blobs] section, the texel only
refers to it by blob_key(content):
    IMG("3f9a0c1e27b4d685.png")
    IMG("3f9a0c1e27b4d685.png", {scale_x=0.5, scale_y=0.5, alt="Photo"})
    IMG("", {path="bilder/wal.png"})                (linked: no blob)
"""

import os
import wx
from copy import copy
from ..textmodel.texeltree import Single, EMPTYSTYLE, NL, iter_childs
from ..layout.boxes import Box
from ..layout.testdevice import TESTDEVICE


# ---------------------------------------------------------------------------
# Texel
# ---------------------------------------------------------------------------

class Image(Single):
    """Inline image texel. Length=1, no parstyle, no indent."""
    text    = '\x0C'   # form feed — unique placeholder
    content      = None   # image data (bytes) or None
    path         = None   # file path or URL (linked), or None
    relative     = False  # path relative to the document in files
    alt          = ''
    scale_x      = 1.0
    scale_y      = 1.0
    proportional = True   # True → editor enforces fixed aspect ratio
    crop         = None   # None or (left, right, top, bottom) in source pixels

    def __init__(self, content=None, scale_x=1.0, scale_y=1.0,
                 proportional=True, crop=None, alt='', path=None,
                 relative=False):
        assert content is None or type(content) is bytes, \
            "image content must be immutable bytes"
        if content is not None:
            self.content = content
        if scale_x != 1.0:
            self.scale_x = scale_x
        if scale_y != 1.0:
            self.scale_y = scale_y
        if not proportional:
            self.proportional = False
        if crop is not None:
            self.crop = crop
        if alt:
            self.alt = alt
        if path:
            self.path = path
        if relative:
            self.relative = True

    def set_relative(self, relative):
        clone = copy(self)
        clone.relative = relative
        return clone

    def set_path(self, path):
        clone = copy(self)
        clone.path = path
        return clone

    def set_content(self, content):
        assert content is None or type(content) is bytes
        clone = copy(self)
        clone.content = content
        return clone

    def set_alt(self, alt):
        clone = copy(self)
        clone.alt = alt
        return clone

    def set_scale_x(self, value):
        clone = copy(self)
        clone.scale_x = value
        return clone

    def set_scale_y(self, value):
        clone = copy(self)
        clone.scale_y = value
        return clone

    def set_proportional(self, value):
        clone = copy(self)
        clone.proportional = value
        return clone

    def set_crop(self, crop):
        clone = copy(self)
        clone.crop = crop
        return clone

    def __repr__(self):
        if self.content is None:
            return 'IMG(None)'
        return 'IMG(%s)' % blob_key(self.content)


_MAGIC = [
    (b'\x89PNG\r\n\x1a\n', '.png'),
    (b'\xff\xd8\xff', '.jpg'),
    (b'GIF87a', '.gif'),
    (b'GIF89a', '.gif'),
]

_MIME = {'.png': 'image/png', '.jpg': 'image/jpeg', '.gif': 'image/gif',
         '.bin': 'application/octet-stream'}


def image_extension(content):
    """File extension for image data, from its magic bytes ('.bin' if
    unknown)."""
    for magic, ext in _MAGIC:
        if content.startswith(magic):
            return ext
    return '.bin'


MAX_IMAGE = 20 * 1024 * 1024  # bytes loaded at most from the web


def is_url(path):
    return bool(path) and path.startswith(('http://', 'https://'))


def file_path(image, folder):
    """The path of image to write into a file in folder: a relative one
    relative to folder (if possible), else as it is."""
    if not (image.relative and image.path and folder):
        return image.path
    try:
        return os.path.relpath(image.path, folder)
    except ValueError:  # Windows: another drive
        return image.path


def memory_path(path, folder):
    """(path, relative) of a path read from a file in folder: a relative
    file path becomes absolute (relative=True)."""
    if not path or not folder or is_url(path) or os.path.isabs(path):
        return path, False
    return os.path.normpath(os.path.join(folder, path)), True


def fetch_image(src, base_dir=''):
    """Image data from src (see fetch), or None."""
    return fetch(src, base_dir)[0]


def fetch(src, base_dir=''):
    """(data, None) for image src - a data URI (taken as it is), a file
    (path or file:// URL, relative to base_dir) or a http(s) URL (10 s,
    MAX_IMAGE at most) - or (None, why not). From files and the web,
    formats other than PNG, JPEG and GIF become PNG (if wx reads them)."""
    import base64
    import binascii
    import urllib.error
    import urllib.parse
    import urllib.request
    kind = None  # the content type a web server tells
    try:
        if src.startswith('data:'):
            return base64.b64decode(src.split('base64,', 1)[1]), None
        if is_url(src):
            request = urllib.request.Request(
                src, headers={'User-Agent': 'Miniword'})
            with urllib.request.urlopen(request, timeout=10) as f:
                kind = f.headers.get_content_type()
                data = f.read(MAX_IMAGE + 1)
            if len(data) > MAX_IMAGE:
                return None, 'larger than %d MB' % (MAX_IMAGE >> 20)
        else:
            if src.startswith('file://'):
                src = urllib.parse.unquote(urllib.parse.urlparse(src).path)
            with open(os.path.join(base_dir, src), 'rb') as f:
                data = f.read()
    except urllib.error.HTTPError as e:
        return None, 'HTTP %d %s' % (e.code, e.reason)
    except TimeoutError:
        return None, 'no answer within 10 s'
    except urllib.error.URLError as e:
        return None, 'cannot connect: %s' % e.reason
    except FileNotFoundError:
        return None, 'file not found'
    except (OSError, ValueError, IndexError, binascii.Error) as e:
        return None, str(e) or type(e).__name__
    if image_extension(data) != '.bin':
        return data, None
    png = _to_png(data)
    if png:
        return png, None
    if kind == 'text/html':
        return None, ('a web page (text/html), not an image - use the '
                      'address of the image itself')
    return None, 'not an image (or an unknown format)'


def _to_png(data):
    """data in another image format as PNG, or None."""
    import io
    image = wx.Image()
    with wx.LogNull():  # no error dialogs for unknown data
        if not image.LoadFile(io.BytesIO(data)) or not image.IsOk():
            return None
    stream = io.BytesIO()
    image.SaveFile(stream, wx.BITMAP_TYPE_PNG)
    return stream.getvalue()


def image_mime(content):
    return _MIME[image_extension(content)]


def blob_key(content):
    """Key of image data in a file's [blobs] section: the first 16 hex
    digits of its SHA-256 plus the extension. Equal data - equal key."""
    import hashlib
    return hashlib.sha256(content).hexdigest()[:16] + image_extension(content)


def iter_images(texel):
    """Yield all Image texels within texel (descending into groups,
    containers, e.g. tables, and footnote contents)."""
    from ..textmodel.submodel import Footnote
    if isinstance(texel, Image):
        yield texel
    elif isinstance(texel, Footnote):
        yield from iter_images(texel.content)
    elif texel.is_group or texel.is_container:
        for i1, i2, child in iter_childs(texel):
            yield from iter_images(child)


# ---------------------------------------------------------------------------
# ImageData — decoded image (Cairo surface + natural pixel dimensions)
# ---------------------------------------------------------------------------

class ImageData:
    """Decoded image: Cairo surface + natural pixel dimensions."""
    def __init__(self, bitmap, width_px, height_px):
        self.bitmap    = bitmap
        self.width_px  = width_px
        self.height_px = height_px


# ---------------------------------------------------------------------------
# Boxes
# ---------------------------------------------------------------------------

class ImageBox(Box):
    """Inline image box. Sits on the baseline (depth=0)."""
    depth      = 0
    image_data = None

    def __init__(self, bitmap, width, height, image_data=None, device=TESTDEVICE):
        self.bitmap = bitmap
        self.width  = width
        self.height = height
        if image_data is not None:
            self.image_data = image_data
        if device is not TESTDEVICE:
            self.device = device

    def __len__(self):
        return 1

    def draw(self, x, y, gc):
        self.device.draw_bitmap(self.bitmap, x, y, self.width, self.height, gc)

    def draw_selection(self, i1, i2, x, y, gc):
        if i1 < 1 and i2 > 0:
            self.device.invert_rect(x, y, self.width, self.height, gc)

    def get_index(self, x, y):
        return 0


class ErrorPlaceholderBox(Box):
    """Shown when an image could not be loaded; label: e.g. the file name
    of a linked image."""
    depth = 0

    def __init__(self, width=50, height=50, device=TESTDEVICE, label=''):
        self.width  = width
        self.height = height
        self.label = label
        if device is not TESTDEVICE:
            self.device = device

    def __len__(self):
        return 1

    def draw(self, x, y, gc):
        self.device.draw_rect(x, y, self.width, self.height, gc)
        self.device.draw_line(x, y, x + self.width, y + self.height, 1, gc)
        self.device.draw_line(x + self.width, y, x, y + self.height, 1, gc)
        if self.label:
            self.device.set_style(dict(font_size=8, color='#606060'), gc)
            self.device.draw_text(self.label, x + 4, y + 4, gc)

    def draw_selection(self, i1, i2, x, y, gc):
        if i1 < 1 and i2 > 0:
            self.device.invert_rect(x, y, self.width, self.height, gc)

    def get_index(self, x, y):
        return 0


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def demo_00():
    "Show text with inline images in a view."
    import os
    import wx
    from ..textmodel.texeltree import grouped, Text
    from ..core.document import Document
    from ..core.stylesheet import testsheet
    from ..layout.rowfactory import Factory
    from ..layout.cairodevice import CairoDevice
    from ..layout.pagebuilder import PageBuilder
    from ..texteditor.editor import Editor
    from ..texteditor.textcanvas import TextCanvas

    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    def load_blob(filename):
        with open(os.path.join(here, 'test', filename), 'rb') as f:
            return f.read()

    doc = Document()
    red, blue = load_blob('red.png'), load_blob('blue.png')
    doc.textmodel.texel = grouped([
        Text("Text before "), Image(red), Text(" text after."), NL,
        Text("Second paragraph with "), Image(blue, scale_x=0.5, scale_y=0.5), Text("."), NL,
    ])

    app = wx.App(False)
    frame = wx.Frame(None, title="Image Demo", size=(500, 400))

    factory = Factory(testsheet, device=CairoDevice())
    builder = PageBuilder(doc.textmodel, factory)
    builder.rebuild()

    editor = Editor(doc.textmodel)
    canvas = TextCanvas(frame, doc.textmodel, builder, editor)
    editor.canvas = canvas

    frame.Show()
    app.MainLoop()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_00():
    "Image texel: defaults"
    from ..textmodel.texeltree import length
    img = Image()
    assert img.content is None and img.alt == ''
    assert img.scale_x == 1.0
    assert img.scale_y == 1.0
    assert img.crop    is None
    assert length(img) == 1
    assert img.text    == '\x0C'


def test_01():
    "Image texel: scale_x, scale_y and crop"
    img = Image(b'data', scale_x=0.5, scale_y=2.0, crop=(10, 20, 400, 300))
    assert img.content == b'data'
    assert img.scale_x == 0.5
    assert img.scale_y == 2.0
    assert img.crop    == (10, 20, 400, 300)


def test_02():
    "ImageBox fallback: None bitmap"
    box = ImageBox(None, 80, 60)
    assert len(box)    == 1
    assert box.width   == 80
    assert box.height  == 60
    assert box.depth   == 0
    assert box.get_index(10, 0) == 0
    assert box.get_index(50, 0) == 0


def test_03():
    "ImageBox: length and geometry"
    box = ImageBox(None, 200, 150)
    assert len(box)   == 1
    assert box.width  == 200
    assert box.height == 150
    assert box.depth  == 0
