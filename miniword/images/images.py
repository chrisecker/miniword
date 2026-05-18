"""
Inline image support: Image texel, boxes, inspector, tests.

Image texel parameters:
    blob_id  -- key into Document.blobs (str)
    scale_x  -- horizontal scale factor, default 1.0
    scale_y  -- vertical scale factor, default 1.0
    crop     -- (left, right, top, bottom) margins in source pixels, or None for full image

TXL format:
    IMG("photo.png")
    IMG("photo.png", {scale_x=0.5, scale_y=0.5})
    IMG("photo.png", {scale_x=2.0, scale_y=2.0, crop_x=10, crop_y=20, crop_w=400, crop_h=300})

Factory.Image_handler() sketch (to be added to factory.py):

    def Image_handler(self, texel, i1, i2):
        from .images import ImageBox, PlaceholderBox
        blob = self.blobs.get(texel.blob_id)
        if blob is None:
            return [PlaceholderBox(50, 50, self.device)]
        bitmap, src_w, src_h = self.device.load_image(blob)
        x, y, w, h = texel.crop if texel.crop else (0, 0, src_w, src_h)
        return [ImageBox(bitmap, w * texel.scale_x, h * texel.scale_y, self.device)]

DocumentView integration sketch:
    - current_style_changed / cursor_changed: check if texel at index is Image
    - if yes: call image_inspector.refresh(image, index)
    - on_change callback: replace_image(index, blob_id, scale_x, scale_y, crop)

    def replace_image(self, i, blob_id, scale_x, scale_y, crop):
        from .textmodel.texeltree import grouped
        img = Image(blob_id, scale_x, scale_y, crop)
        tmp = self.model.create_textmodel()
        tmp.texel = grouped([img])
        with self.atomic():
            self.model.remove(i, i + 1)
            self.model.insert(i, tmp)
"""

import wx
from copy import copy
from ..textmodel.texeltree import Single, EMPTYSTYLE, NL
from ..layout.boxes import Box
from ..layout.testdevice import TESTDEVICE


# ---------------------------------------------------------------------------
# Texel
# ---------------------------------------------------------------------------

class Image(Single):
    """Inline image texel. Length=1, no parstyle, no indent."""
    text    = '\x0C'   # form feed — unique placeholder
    blob_id      = None
    scale_x      = 1.0
    scale_y      = 1.0
    proportional = True   # True → editor enforces fixed aspect ratio
    crop         = None   # None or (left, right, top, bottom) in source pixels

    def __init__(self, blob_id, scale_x=1.0, scale_y=1.0, proportional=True, crop=None):
        self.blob_id = blob_id
        if scale_x != 1.0:
            self.scale_x = scale_x
        if scale_y != 1.0:
            self.scale_y = scale_y
        if not proportional:
            self.proportional = False
        if crop is not None:
            self.crop = crop

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

    def set_blob_id(self, blob_id):
        clone = copy(self)
        clone.blob_id = blob_id
        return clone

    def __repr__(self):
        return 'IMG(%r)' % self.blob_id


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
    """Shown when an image could not be loaded."""
    depth = 0

    def __init__(self, width=50, height=50, device=TESTDEVICE):
        self.width  = width
        self.height = height
        if device is not TESTDEVICE:
            self.device = device

    def __len__(self):
        return 1

    def draw(self, x, y, gc):
        self.device.draw_rect(x, y, self.width, self.height, gc)
        self.device.draw_line(x, y, x + self.width, y + self.height, 1, gc)
        self.device.draw_line(x + self.width, y, x, y + self.height, 1, gc)

    def draw_selection(self, i1, i2, x, y, gc):
        if i1 < 1 and i2 > 0:
            self.device.invert_rect(x, y, self.width, self.height, gc)

    def get_index(self, x, y):
        return 0


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def demo_00():
    "Show text with an inline image placeholder in a view."
    import os
    import wx
    from ..textmodel.texeltree import grouped, Text
    from ..core.document import Document
    from ..texteditor import TextEditor

    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    def load_blob(filename):
        with open(os.path.join(here, 'test', filename), 'rb') as f:
            return f.read()

    doc = Document()
    doc.blobs = {'red.png': load_blob('red.png'), 'blue.png': load_blob('blue.png')}
    doc.textmodel.texel = grouped([
        Text("Text before "), Image("red.png"), Text(" text after."), NL,
        Text("Second paragraph with "), Image("blue.png", scale_x=0.5, scale_y=0.5), Text("."), NL,
    ])

    app = wx.App(False)
    frame = wx.Frame(None, title="Image Demo", size=(500, 400))
    view = TextEditor(frame, doc)
    view.builder.factory.blobs = doc.blobs
    frame.Show()
    app.MainLoop()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_00():
    "Image texel: defaults"
    from ..textmodel.texeltree import length
    img = Image("photo.png")
    assert img.blob_id == "photo.png"
    assert img.scale_x == 1.0
    assert img.scale_y == 1.0
    assert img.crop    is None
    assert length(img) == 1
    assert img.text    == '\x0C'


def test_01():
    "Image texel: scale_x, scale_y and crop"
    img = Image("photo.png", scale_x=0.5, scale_y=2.0, crop=(10, 20, 400, 300))
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
