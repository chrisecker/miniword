"""
Inline image support: Image texel, boxes, inspector, tests.

Image texel parameters:
    blob_id  -- key into Document.blobs (str)
    scale    -- uniform scale factor, default 1.0
    crop     -- (x, y, w, h) in source pixels, or None for full image

TXL format:
    IMG("photo.png")
    IMG("photo.png", {scale=0.5})
    IMG("photo.png", {scale=2.0, crop_x=10, crop_y=20, crop_w=400, crop_h=300})

Factory.Image_handler() sketch (to be added to factory.py):

    def Image_handler(self, texel, i1, i2):
        from .image import ImageBox, PlaceholderBox
        blob = self.blobs.get(texel.blob_id)
        if blob is None:
            return [PlaceholderBox(50, 50, self.device)]
        bitmap, src_w, src_h = self.device.load_image(blob)
        x, y, w, h = texel.crop if texel.crop else (0, 0, src_w, src_h)
        return [ImageBox(bitmap, w * texel.scale, h * texel.scale, self.device)]

DocumentView integration sketch:
    - current_style_changed / cursor_changed: check if texel at index is Image
    - if yes: call image_inspector.refresh(image, index)
    - on_change callback: replace_image(index, blob_id, scale, crop)

    def replace_image(self, i, blob_id, scale, crop):
        from .textmodel.texeltree import grouped
        img = Image(blob_id, scale, crop)
        tmp = self.model.create_textmodel()
        tmp.texel = grouped([img])
        with self.atomic():
            self.model.remove(i, i + 1)
            self.model.insert(i, tmp)
"""

import wx
from .textmodel.texeltree import Single, EMPTYSTYLE, NL
from .wxtextview.boxes import Box
from .wxtextview.testdevice import TESTDEVICE


# ---------------------------------------------------------------------------
# Texel
# ---------------------------------------------------------------------------

class Image(Single):
    """Inline image texel. Length=1, no parstyle, no indent."""
    text    = '\x0C'   # form feed — unique placeholder
    blob_id = None
    scale   = 1.0
    crop    = None     # None or (x, y, w, h) in source pixels

    def __init__(self, blob_id, scale=1.0, crop=None):
        self.blob_id = blob_id
        if scale != 1.0:
            self.scale = scale
        if crop is not None:
            self.crop = crop

    def __repr__(self):
        return 'IMG(%r)' % self.blob_id


# ---------------------------------------------------------------------------
# Boxes
# ---------------------------------------------------------------------------

class ImageBox(Box):
    """Inline image box. Sits on the baseline (depth=0)."""
    depth = 0

    def __init__(self, bitmap, width, height, device=TESTDEVICE):
        self.bitmap = bitmap
        self.width  = width
        self.height = height
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
        return 1 if x >= self.width / 2 else 0



# ---------------------------------------------------------------------------
# Inspector / Image Tool
# ---------------------------------------------------------------------------

class ImageInspector(wx.Panel):
    """Image Tool: insert new images and inspect/edit existing ones.

    Top section (always active):   insert a new image from a file.
    Bottom section (active only when cursor is on an Image texel):
        scale, crop, and replace the image.

    The owner must:
    - set self.blobs = doc.blobs (mutable dict shared with the document)
    - call refresh(image, index) when cursor moves onto an Image texel
    - call clear() when cursor leaves an Image texel
    - provide on_insert(blob_id) to insert a new Image texel at cursor
    - provide on_change(index, blob_id, scale, crop) to apply edits
    """

    blobs = {}   # set externally: inspector.blobs = doc.blobs

    def __init__(self, parent, on_insert, on_change):
        wx.Panel.__init__(self, parent)
        self.on_insert = on_insert
        self.on_change = on_change
        self._index    = None
        self._blob_id  = None
        self._updating = False

        from .ui.unitentry import UnitInput, EVT_UNIT_CHANGED

        sizer = wx.BoxSizer(wx.VERTICAL)

        # --- Insert section (always active) ---
        btn_insert = wx.Button(self, label="Insert Image\u2026")
        btn_insert.Bind(wx.EVT_BUTTON, self._on_insert)
        sizer.Add(btn_insert, 0, wx.ALL | wx.EXPAND, 8)

        # --- Separator ---
        sizer.Add(wx.StaticLine(self), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
        sizer.AddSpacer(8)

        # --- Inspector section (enabled only when cursor is on an Image) ---

        row_scale = wx.BoxSizer(wx.HORIZONTAL)
        row_scale.Add(wx.StaticText(self, label="Scale"), 0,
                      wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        self.txt_scale = wx.TextCtrl(self, value="1.0", size=(70, -1),
                                     style=wx.TE_PROCESS_ENTER)
        self.txt_scale.Bind(wx.EVT_TEXT_ENTER, self._on_scale)
        self.txt_scale.Bind(wx.EVT_KILL_FOCUS,  self._on_scale)
        row_scale.Add(self.txt_scale)
        sizer.Add(row_scale, 0, wx.ALL, 5)

        self.chk_crop = wx.CheckBox(self, label="Crop")
        self.chk_crop.Bind(wx.EVT_CHECKBOX, self._on_crop_toggle)
        sizer.Add(self.chk_crop, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)

        self._crop_panel = wx.Panel(self)
        grid = wx.FlexGridSizer(rows=2, cols=4, hgap=6, vgap=6)
        self._crop_fields = {}
        for key, label in [('x', 'X'), ('y', 'Y'), ('w', 'W'), ('h', 'H')]:
            grid.Add(wx.StaticText(self._crop_panel, label=label), 0,
                     wx.ALIGN_CENTER_VERTICAL)
            field = UnitInput(self._crop_panel, default_unit="mm")
            field.Bind(EVT_UNIT_CHANGED,
                       lambda e, k=key: self._on_crop_field(k, e))
            self._crop_fields[key] = field
            grid.Add(field, 0, wx.EXPAND)
        self._crop_panel.SetSizer(grid)
        sizer.Add(self._crop_panel, 0, wx.LEFT | wx.RIGHT, 20)

        sizer.AddSpacer(10)

        self.btn_replace = wx.Button(self, label="Replace image\u2026")
        self.btn_replace.Bind(wx.EVT_BUTTON, self._on_replace)
        sizer.Add(self.btn_replace, 0, wx.ALL | wx.EXPAND, 8)

        self.SetSizer(sizer)
        self._crop_panel.Show(False)
        self._set_inspector_enabled(False)

    # ------------------------------------------------------------------

    def _set_inspector_enabled(self, enabled):
        self.txt_scale.Enable(enabled)
        self.chk_crop.Enable(enabled)
        self._crop_panel.Enable(enabled)
        self.btn_replace.Enable(enabled)

    def refresh(self, image, index):
        """Enable inspector and fill values from the Image texel."""
        self._updating = True
        self._index   = index
        self._blob_id = image.blob_id
        self.txt_scale.SetValue(str(image.scale))
        has_crop = image.crop is not None
        self.chk_crop.SetValue(has_crop)
        self._crop_panel.Show(has_crop)
        if has_crop:
            x, y, w, h = image.crop
            for key, val in [('x', x), ('y', y), ('w', w), ('h', h)]:
                self._crop_fields[key].SetValue(val)
        self._set_inspector_enabled(True)
        self.Layout()
        self._updating = False

    def clear(self):
        """Disable inspector section (cursor is not on an Image texel)."""
        self._index   = None
        self._blob_id = None
        self._set_inspector_enabled(False)

    # ------------------------------------------------------------------

    def _read(self):
        try:
            scale = float(self.txt_scale.GetValue())
        except ValueError:
            scale = 1.0
        crop = None
        if self.chk_crop.GetValue():
            vals = [self._crop_fields[k].GetValue() for k in ('x', 'y', 'w', 'h')]
            if all(v is not None for v in vals):
                crop = tuple(vals)
        return scale, crop

    def _notify(self):
        if self._updating or self._index is None:
            return
        scale, crop = self._read()
        self.on_change(self._index, self._blob_id, scale, crop)

    def _on_scale(self, event):
        self._notify()
        event.Skip()

    def _on_crop_toggle(self, event):
        self._crop_panel.Show(event.IsChecked())
        self.Layout()
        self._notify()

    def _on_crop_field(self, key, event):
        self._notify()

    def _load_image_file(self):
        """Open file dialog; return (blob_id, bytes) or (None, None)."""
        import os
        with wx.FileDialog(
            self, "Choose image",
            wildcard="Images (*.png;*.jpg;*.jpeg)|*.png;*.jpg;*.jpeg",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return None, None
            path = dlg.GetPath()
        blob_id = os.path.basename(path)
        base, ext = os.path.splitext(blob_id)
        n = 1
        while blob_id in self.blobs:
            blob_id = '%s_%d%s' % (base, n, ext)
            n += 1
        with open(path, 'rb') as f:
            data = f.read()
        return blob_id, data

    def _on_insert(self, event):
        blob_id, data = self._load_image_file()
        if blob_id is None:
            return
        self.blobs[blob_id] = data
        self.on_insert(blob_id)

    def _on_replace(self, event):
        if self._index is None:
            return
        blob_id, data = self._load_image_file()
        if blob_id is None:
            return
        self.blobs[blob_id] = data
        self._blob_id = blob_id
        self._notify()


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def demo_00():
    "Show text with an inline image placeholder in a view."
    import os
    import wx
    from .textmodel.texeltree import grouped, Text
    from .document import Document
    from .documentview import DocumentView

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def load_blob(filename):
        with open(os.path.join(here, 'test', filename), 'rb') as f:
            return f.read()

    doc = Document()
    doc.blobs = {'red.png': load_blob('red.png'), 'blue.png': load_blob('blue.png')}
    doc.textmodel.texel = grouped([
        Text("Text before "), Image("red.png"), Text(" text after."), NL,
        Text("Second paragraph with "), Image("blue.png", scale=0.5), Text("."), NL,
    ])

    app = wx.App(False)
    frame = wx.Frame(None, title="Image Demo", size=(500, 400))
    view = DocumentView(frame, doc)
    view.builder.factory.blobs = doc.blobs
    frame.Show()
    app.MainLoop()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_00():
    "Image texel: defaults"
    from .textmodel.texeltree import length
    img = Image("photo.png")
    assert img.blob_id == "photo.png"
    assert img.scale   == 1.0
    assert img.crop    is None
    assert length(img) == 1
    assert img.text    == '\x0C'


def test_01():
    "Image texel: scale and crop"
    img = Image("photo.png", scale=0.5, crop=(10, 20, 400, 300))
    assert img.scale == 0.5
    assert img.crop  == (10, 20, 400, 300)


def test_02():
    "ImageBox fallback: None bitmap"
    box = ImageBox(None, 80, 60)
    assert len(box)    == 1
    assert box.width   == 80
    assert box.height  == 60
    assert box.depth   == 0
    assert box.get_index(10, 0) == 0
    assert box.get_index(50, 0) == 1


def test_03():
    "ImageBox: length and geometry"
    box = ImageBox(None, 200, 150)
    assert len(box)   == 1
    assert box.width  == 200
    assert box.height == 150
    assert box.depth  == 0
