import os
import wx
from .image import Image
from .image_editors import ImageCropEditor
from .textmodel.texeltree import grouped
from .textmodel.viewbase import ViewBase
from .ui.unitentry import LengthInput, EVT_UNIT_CHANGED


class ImageInspector(wx.Panel, ViewBase):
    """Image Tool: insert new images and inspect/edit existing ones.

    Top section (always active):   insert a new image from a file.
    Bottom section (active only when cursor is on an Image texel):
        replace, resize, and crop the image.

    Registers itself on the DocumentView to receive editor_changed signals.
    """

    def __init__(self, parent, view):
        wx.Panel.__init__(self, parent)
        ViewBase.__init__(self)
        self._view = view
        self.add_model(view)
        self._index        = None
        self._blob_id      = None
        self._current_crop = None
        self._natural_w    = 1.0
        self._natural_h    = 1.0
        self._updating     = False

        M = 5   # margin

        sizer = wx.BoxSizer(wx.VERTICAL)

        # --- Insert (always active) ---
        btn_insert = wx.Button(self, label="Insert Image\u2026")
        btn_insert.Bind(wx.EVT_BUTTON, self._on_insert)
        sizer.Add(btn_insert, 0, wx.ALL | wx.EXPAND, M)

        sizer.Add(wx.StaticLine(self), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, M)

        # --- Replace ---
        self.btn_replace = wx.Button(self, label="Replace Image\u2026")
        self.btn_replace.Bind(wx.EVT_BUTTON, self._on_replace)
        sizer.Add(self.btn_replace, 0, wx.ALL | wx.EXPAND, M)

        sizer.AddSpacer(4)

        # --- Size / Scale grid ---
        grid = wx.FlexGridSizer(rows=2, cols=3, hgap=4, vgap=4)
        grid.AddGrowableCol(1)
        grid.AddGrowableCol(2)

        grid.Add(wx.StaticText(self, label="Size"),
                 0, wx.ALIGN_CENTER_VERTICAL)
        self.txt_size_x = LengthInput(self, display_unit="mm")
        self.txt_size_x.Bind(EVT_UNIT_CHANGED, self._on_size)
        grid.Add(self.txt_size_x, 0, wx.EXPAND)
        self.txt_size_y = LengthInput(self, display_unit="mm")
        self.txt_size_y.Bind(EVT_UNIT_CHANGED, self._on_size)
        grid.Add(self.txt_size_y, 0, wx.EXPAND)

        grid.Add(wx.StaticText(self, label="Scale"),
                 0, wx.ALIGN_CENTER_VERTICAL)
        self.txt_scale_x = wx.TextCtrl(self, value="1.0",
                                       style=wx.TE_PROCESS_ENTER)
        self.txt_scale_x.Bind(wx.EVT_TEXT_ENTER, self._on_scale)
        self.txt_scale_x.Bind(wx.EVT_KILL_FOCUS,  self._on_scale)
        grid.Add(self.txt_scale_x, 0, wx.EXPAND)
        self.txt_scale_y = wx.TextCtrl(self, value="1.0",
                                       style=wx.TE_PROCESS_ENTER)
        self.txt_scale_y.Bind(wx.EVT_TEXT_ENTER, self._on_scale)
        self.txt_scale_y.Bind(wx.EVT_KILL_FOCUS,  self._on_scale)
        grid.Add(self.txt_scale_y, 0, wx.EXPAND)

        sizer.Add(grid, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, M)

        sizer.AddSpacer(4)

        self.chk_proportional = wx.CheckBox(self, label="Proportional")
        self.chk_proportional.Bind(wx.EVT_CHECKBOX, self._on_proportional)
        sizer.Add(self.chk_proportional, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, M)

        sizer.AddSpacer(4)

        # --- Crop ---
        self.btn_crop = wx.ToggleButton(self, label="Crop")
        self.btn_crop.Bind(wx.EVT_TOGGLEBUTTON, self._on_crop_toggle)
        sizer.Add(self.btn_crop, 0, wx.ALL | wx.EXPAND, M)

        self.btn_unset_crop = wx.Button(self, label="Unset Crop")
        self.btn_unset_crop.Bind(wx.EVT_BUTTON, self._on_unset_crop)
        sizer.Add(self.btn_unset_crop, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, M)

        self.SetSizer(sizer)
        self._set_inspector_enabled(False)

    # ------------------------------------------------------------------

    def _set_inspector_enabled(self, enabled, has_crop=False):
        for w in (self.btn_replace, self.txt_size_x, self.txt_size_y,
                  self.txt_scale_x, self.txt_scale_y,
                  self.chk_proportional, self.btn_crop):
            w.Enable(enabled)
        self.btn_unset_crop.Enable(enabled and has_crop)

    def refresh(self, image, index, box=None):
        """Enable inspector and fill values from the Image texel."""
        self._updating     = True
        self._index        = index
        self._blob_id      = image.blob_id
        self._current_crop = image.crop
        if box is not None:
            self._natural_w = box.width  / (image.scale_x or 1.0)
            self._natural_h = box.height / (image.scale_y or 1.0)
        self.txt_size_x.SetValue(self._natural_w * image.scale_x)
        self.txt_size_y.SetValue(self._natural_h * image.scale_y)
        self.txt_scale_x.SetValue(f'{image.scale_x:g}')
        self.txt_scale_y.SetValue(f'{image.scale_y:g}')
        self.chk_proportional.SetValue(image.proportional)
        self._set_inspector_enabled(True, has_crop=image.crop is not None)
        self._updating = False

    def clear(self):
        """Disable inspector section (cursor is not on an Image texel)."""
        self._index   = None
        self._blob_id = None
        self._set_inspector_enabled(False)

    # ------------------------------------------------------------------

    def _notify(self):
        if self._updating or self._index is None:
            return
        try:
            scale_x = float(self.txt_scale_x.GetValue())
        except ValueError:
            scale_x = 1.0
        try:
            scale_y = float(self.txt_scale_y.GetValue())
        except ValueError:
            scale_y = 1.0
        self._view.set_texel_attributes(
            self._index, Image,
            blob_id=self._blob_id, scale_x=scale_x, scale_y=scale_y,
            proportional=self.chk_proportional.GetValue(),
            crop=self._current_crop)

    def _on_size(self, event):
        if self._updating or self._index is None:
            return
        sx_pt = self.txt_size_x.GetValue()
        sy_pt = self.txt_size_y.GetValue()
        if sx_pt is None or sy_pt is None:
            return
        scale_x = sx_pt / self._natural_w if self._natural_w else 1.0
        scale_y = sy_pt / self._natural_h if self._natural_h else 1.0
        self._updating = True
        self.txt_scale_x.SetValue(f'{scale_x:g}')
        self.txt_scale_y.SetValue(f'{scale_y:g}')
        self._updating = False
        self._notify()

    def _on_scale(self, event):
        if self._updating or self._index is None:
            return
        try:
            scale_x = float(self.txt_scale_x.GetValue())
            scale_y = float(self.txt_scale_y.GetValue())
        except ValueError:
            event.Skip()
            return
        self._updating = True
        self.txt_size_x.SetValue(scale_x * self._natural_w)
        self.txt_size_y.SetValue(scale_y * self._natural_h)
        self._updating = False
        self._notify()
        event.Skip()

    def _on_proportional(self, event):
        self._notify()

    def editor_changed(self, view, editor):
        if editor is not None and isinstance(editor.texel, Image):
            self.refresh(editor.texel, editor.index, getattr(editor, 'box', None))
        else:
            self.clear()
        self.btn_crop.SetValue(isinstance(editor, ImageCropEditor))

    def _on_crop_toggle(self, event):
        if self.btn_crop.GetValue():
            if self._index is not None:
                self._view.install_editor(ImageCropEditor(), self._index)
        else:
            self._view.remove_editor()

    def _on_unset_crop(self, event):
        if self._index is None:
            return
        self._current_crop = None
        self._notify()
        self.btn_unset_crop.Enable(False)

    def _load_image_file(self):
        """Open file dialog; return (blob_id, bytes) or (None, None)."""
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
        while blob_id in self._view.document.blobs:
            blob_id = '%s_%d%s' % (base, n, ext)
            n += 1
        with open(path, 'rb') as f:
            data = f.read()
        return blob_id, data

    def _on_insert(self, event):
        blob_id, data = self._load_image_file()
        if blob_id is None:
            return
        self._view.document.blobs[blob_id] = data
        index = self._view.index
        scale = 1.0
        load_image = getattr(self._view.builder.device, 'load_image', None)
        if load_image:
            _, src_w, _ = load_image(data)
            avail_w = self._view.get_rowwidth(index)
            if src_w > 0 and avail_w and src_w > avail_w:
                scale = avail_w / src_w
        self._view.insert_texel(index, grouped([Image(blob_id, scale)]))

    def _on_replace(self, event):
        if self._index is None:
            return
        blob_id, data = self._load_image_file()
        if blob_id is None:
            return
        self._view.document.blobs[blob_id] = data
        self._blob_id = blob_id
        self._notify()


def demo_00():
    """Show ImageInspector with a simulated active image selection."""
    app = wx.App()
    frame = wx.Frame(None, title="ImageInspector Demo", size=(260, 400))

    class _FakeDoc:
        blobs = {}

    class _FakeView:
        index    = 0
        document = _FakeDoc()
        def add_view(self, v): pass
        def set_texel_attributes(self, *a, **kw): pass
        def get_rowwidth(self, i): return 400
        def insert_texel(self, i, t): pass
        def install_editor(self, e, i): pass
        def remove_editor(self): pass

    panel = ImageInspector(frame, view=_FakeView())

    # Simulate cursor on an image texel
    img = Image("photo.jpg", scale_x=1.5, scale_y=1.5)
    panel.refresh(img, index=5)

    frame.Show()
    app.MainLoop()


if __name__ == '__main__':
    demo_00()
