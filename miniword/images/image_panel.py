import os
import wx
from .images import Image
from ..core.utils import get_path
from .image_controllers import ImageCropController
from ..textmodel.texeltree import grouped
from ..ui.sidepanel import SidePanel
from ..ui.unitentry import LengthInput, FractionInput, EVT_UNIT_CHANGED
from ..ui.design import flat_button, make_panel, add_section, add_row
from ..ui.flatbutton import ResetButton


class ImageInspector(SidePanel):
    """Image Tool: insert new images and inspect/edit existing ones.

    Top section (always active):   insert a new image from a file.
    Bottom section (active only when cursor is on an Image texel):
        replace, resize, and crop the image.
    """

    def __init__(self, parent, view):
        SidePanel.__init__(self, parent)
        self._view = view
        self.add_model(view)
        self.add_model(view.model)
        self._blob_id       = None
        self._current_crop  = None
        self._last_image_dir = ''
        self._natural_w    = 1.0
        self._natural_h    = 1.0
        self._updating     = False
        self._crop_active  = False
        self.create()

    def create(self):
        dip = self.FromDIP
        sizer = make_panel(self, "IMAGE")

        # --- Insert (always active) ---
        add_section("Insert", self, sizer)
        btn_insert = flat_button(self, "Insert Image\u2026", size=(-1, dip(28)))
        btn_insert.Bind(wx.EVT_BUTTON, self._on_insert)
        sizer.Add(btn_insert, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, dip(5))

        # --- Replace / Export ---
        self.btn_replace = flat_button(self, "Replace Image\u2026", size=(-1, dip(28)))
        self.btn_replace.Bind(wx.EVT_BUTTON, self._on_replace)
        sizer.Add(self.btn_replace, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, dip(5))

        self.btn_export = flat_button(self, "Export Image\u2026", size=(-1, dip(28)))
        self.btn_export.Bind(wx.EVT_BUTTON, self._on_export)
        sizer.Add(self.btn_export, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, dip(5))

        # --- Size ---
        add_section("Size", self, sizer)

        self.txt_size_x = LengthInput(self, category="layout")
        self.txt_size_x.Bind(EVT_UNIT_CHANGED, lambda e: self._on_size('x'))
        self.btn_reset_w = ResetButton(self)
        self.btn_reset_w.callback = self._reset_size_x
        add_row(sizer, wx.StaticText(self, label="Width"), self.txt_size_x, self.btn_reset_w)

        self.txt_size_y = LengthInput(self, category="layout")
        self.txt_size_y.Bind(EVT_UNIT_CHANGED, lambda e: self._on_size('y'))
        self.btn_reset_h = ResetButton(self)
        self.btn_reset_h.callback = self._reset_size_y
        add_row(sizer, wx.StaticText(self, label="Height"), self.txt_size_y, self.btn_reset_h)

        self.chk_proportional = wx.CheckBox(self, label="Proportional")
        self.chk_proportional.Bind(wx.EVT_CHECKBOX, self._on_proportional)
        sizer.Add(self.chk_proportional, 0, wx.LEFT | wx.TOP, dip(28))

        # --- Scale ---
        add_section("Scale", self, sizer)

        self.txt_scale_x = FractionInput(self)
        self.txt_scale_x.Bind(EVT_UNIT_CHANGED, lambda e: self._on_scale('x'))
        self.btn_reset_sx = ResetButton(self)
        self.btn_reset_sx.callback = self._reset_scale_x
        add_row(sizer, wx.StaticText(self, label="X"), self.txt_scale_x, self.btn_reset_sx)

        self.txt_scale_y = FractionInput(self)
        self.txt_scale_y.Bind(EVT_UNIT_CHANGED, lambda e: self._on_scale('y'))
        self.btn_reset_sy = ResetButton(self)
        self.btn_reset_sy.callback = self._reset_scale_y
        add_row(sizer, wx.StaticText(self, label="Y"), self.txt_scale_y, self.btn_reset_sy)

        # --- Crop ---
        add_section("Crop", self, sizer)

        self.btn_crop = flat_button(self, "Edit Crop", size=(-1, dip(28)))
        self.btn_crop.Bind(wx.EVT_BUTTON, self._on_crop_toggle)
        sizer.Add(self.btn_crop, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, dip(5))

        self.btn_unset_crop = flat_button(self, "Unset Crop", size=(-1, dip(28)))
        self.btn_unset_crop.Bind(wx.EVT_BUTTON, self._on_unset_crop)
        sizer.Add(self.btn_unset_crop, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, dip(5))

        self._set_inspector_enabled(False)

    def update(self):
        texel = self._get_image_texel()
        if texel is not None:
            self.refresh(texel)
        else:
            self.clear()

    # ------------------------------------------------------------------

    def _set_inspector_enabled(self, enabled, has_crop=False):
        for w in (self.btn_replace, self.btn_export, self.txt_size_x, self.txt_size_y,
                  self.txt_scale_x, self.txt_scale_y,
                  self.chk_proportional, self.btn_crop, self.btn_unset_crop):
            w.Enable(enabled)
        self.btn_unset_crop.Enable(enabled and has_crop)

    def refresh(self, image):
        """Enable inspector and fill values from the Image texel."""
        self._updating     = True
        self._blob_id      = image.blob_id
        self._current_crop = image.crop
        get_image = getattr(self._view, 'get_image', None)
        if get_image:
            image_data = get_image(image.blob_id)
            if image_data:
                self._natural_w = image_data.width_px
                self._natural_h = image_data.height_px
        self.txt_size_x.SetValue(self._natural_w * image.scale_x)
        self.txt_size_y.SetValue(self._natural_h * image.scale_y)
        self.txt_scale_x.SetValue(image.scale_x)
        self.txt_scale_y.SetValue(image.scale_y)
        self.chk_proportional.SetValue(image.proportional)
        self._set_inspector_enabled(True, has_crop=image.crop is not None)
        modified_x = abs(image.scale_x - 1.0) > 1e-6
        modified_y = abs(image.scale_y - 1.0) > 1e-6
        self.btn_reset_w.set_x(modified_x)
        self.btn_reset_h.set_x(modified_y)
        self.btn_reset_sx.set_x(modified_x)
        self.btn_reset_sy.set_x(modified_y)
        self._updating = False

    def clear(self):
        """Disable inspector section (cursor is not on an Image texel)."""
        self._blob_id = None
        self._set_inspector_enabled(False)
        for btn in (self.btn_reset_w, self.btn_reset_h,
                    self.btn_reset_sx, self.btn_reset_sy):
            btn.set_x(False)

    # ------------------------------------------------------------------

    def _notify(self):
        if self._updating or self._blob_id is None:
            return
        index = self._view.index
        texel = next((t for _, _, t in get_path(self._view.edit_model.texel, index)
                      if isinstance(t, Image)), None)
        if texel is None:
            return
        scale_x = self.txt_scale_x.GetValue() or 1.0
        scale_y = self.txt_scale_y.GetValue() or 1.0
        self._view.set_texel_attributes(
            index, texel,
            blob_id=self._blob_id, scale_x=scale_x, scale_y=scale_y,
            proportional=self.chk_proportional.GetValue(),
            crop=self._current_crop)

    def _on_size(self, changed):
        if self._updating or self._blob_id is None:
            return
        proportional = self.chk_proportional.GetValue()
        if changed == 'x':
            v = self.txt_size_x.GetValue()
            if v is None:
                return
            scale_x = v / self._natural_w if self._natural_w else 1.0
            scale_y = scale_x if proportional else (self.txt_scale_y.GetValue() or 1.0)
        else:
            v = self.txt_size_y.GetValue()
            if v is None:
                return
            scale_y = v / self._natural_h if self._natural_h else 1.0
            scale_x = scale_y if proportional else (self.txt_scale_x.GetValue() or 1.0)
        self._update_fields(scale_x, scale_y)

    def _on_scale(self, changed):
        if self._updating or self._blob_id is None:
            return
        proportional = self.chk_proportional.GetValue()
        if changed == 'x':
            scale_x = self.txt_scale_x.GetValue()
            if scale_x is None:
                return
            scale_y = scale_x if proportional else (self.txt_scale_y.GetValue() or 1.0)
        else:
            scale_y = self.txt_scale_y.GetValue()
            if scale_y is None:
                return
            scale_x = scale_y if proportional else (self.txt_scale_x.GetValue() or 1.0)
        self._update_fields(scale_x, scale_y)

    def _update_fields(self, scale_x, scale_y):
        self._updating = True
        self.txt_scale_x.SetValue(scale_x)
        self.txt_scale_y.SetValue(scale_y)
        self.txt_size_x.SetValue(scale_x * self._natural_w)
        self.txt_size_y.SetValue(scale_y * self._natural_h)
        modified_x = abs(scale_x - 1.0) > 1e-6
        modified_y = abs(scale_y - 1.0) > 1e-6
        self.btn_reset_w.set_x(modified_x)
        self.btn_reset_h.set_x(modified_y)
        self.btn_reset_sx.set_x(modified_x)
        self.btn_reset_sy.set_x(modified_y)
        self._updating = False
        self._notify()

    def _reset_size_x(self):
        if self._natural_w:
            self.txt_size_x.SetValue(self._natural_w)
            self._on_size('x')

    def _reset_size_y(self):
        if self._natural_h:
            self.txt_size_y.SetValue(self._natural_h)
            self._on_size('y')

    def _reset_scale_x(self):
        self.txt_scale_x.SetValue(1.0)
        self._on_scale('x')

    def _reset_scale_y(self):
        self.txt_scale_y.SetValue(1.0)
        self._on_scale('y')

    def _on_proportional(self, event):
        self._notify()

    def _get_image_texel(self):
        """Return the Image texel at the current cursor position, or None."""
        return next((t for _, _, t in get_path(self._view.edit_model.texel, self._view.index)
                     if isinstance(t, Image)), None)

    def _on_crop_toggle(self, event):
        if not self._crop_active:
            if self._blob_id is not None:
                index = self._view.index
                path = get_path(self._view.edit_model.texel, index)
                for depth, (i1, i2, texel) in enumerate(path):
                    if isinstance(texel, Image):
                        editor = ImageCropController(self._view, i1, i2, depth)
                        self._view.install_editor(editor, texel)
                        break
        else:
            self._view.remove_editor()

    def _on_unset_crop(self, event):
        if self._blob_id is None:
            return
        self._current_crop = None
        self._notify()
        self.btn_unset_crop.Enable(False)

    def _load_image_file(self):
        """Open file dialog; return (blob_id, bytes) or (None, None)."""
        with wx.FileDialog(
            self, "Choose image",
            defaultDir=self._last_image_dir,
            wildcard="Images (*.png;*.jpg;*.jpeg)|*.png;*.jpg;*.jpeg",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return None, None
            path = dlg.GetPath()
        self._last_image_dir = os.path.dirname(path)
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
        index   = self._view.index
        scale_x = scale_y = 1.0
        image_data = self._view.get_image(blob_id)
        if image_data and image_data.width_px > 0:
            avail_w = self._view.get_rowwidth(index)
            if avail_w and image_data.width_px > avail_w:
                scale_x = scale_y = avail_w / image_data.width_px
        self._view.insert_texel(index, grouped([Image(blob_id, scale_x, scale_y)]))

    def _on_replace(self, event):
        if self._blob_id is None:
            return
        blob_id, data = self._load_image_file()
        if blob_id is None:
            return
        self._view.document.blobs[blob_id] = data
        self._blob_id = blob_id
        self._notify()

    def _on_export(self, event):
        if self._blob_id is None:
            return
        data = self._view.document.blobs.get(self._blob_id)
        if data is None:
            return
        ext = os.path.splitext(self._blob_id)[1].lower()
        wildcard = "Image files (*%s)|*%s|All files (*.*)|*.*" % (ext, ext)
        with wx.FileDialog(
            self, "Export Image",
            defaultDir=self._last_image_dir,
            defaultFile=self._blob_id,
            wildcard=wildcard,
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        ) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            path = dlg.GetPath()
        self._last_image_dir = os.path.dirname(path)
        with open(path, 'wb') as f:
            f.write(data)


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
