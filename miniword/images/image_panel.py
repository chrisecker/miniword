import os
import wx
from .images import Image, image_extension
from .imageio import decode_cached, content_of, load_url, errors
from .images import fetch, is_url
from ..core.utils import get_path
from .image_controllers import ImageCropController
from ..textmodel.texeltree import grouped
from ..texteditor.controller import NullController
from ..ui.sidepanel import SidePanel
from ..ui.unitentry import LengthInput, FractionInput, EVT_UNIT_CHANGED
from ..ui.design import flat_button, make_panel, add_section, add_row
from ..ui.flatbutton import ResetButton


def link_source(text, base_dir):
    """The path to link for text entered, or None: a URL or relative path
    as it is, an absolute path relative to the document's folder
    base_dir if possible."""
    text = text.strip()
    if not text or is_url(text) or not os.path.isabs(text) \
            or not base_dir:
        return text or None
    try:
        return os.path.relpath(text, base_dir)
    except ValueError:  # Windows: another drive
        return text


def ask_link(parent, folder):
    """Dialog: a URL or file (Browse...) to link to; the text, or None."""
    dlg = wx.Dialog(parent, title="Link to Image")
    sizer = wx.BoxSizer(wx.VERTICAL)
    sizer.Add(wx.StaticText(dlg, label="URL or file:"), 0, wx.ALL, 8)
    text = wx.TextCtrl(dlg, size=(dlg.FromDIP(360), -1))
    browse = wx.Button(dlg, label="Browse\u2026")
    row = wx.BoxSizer(wx.HORIZONTAL)
    row.Add(text, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
    row.Add(browse, 0)
    sizer.Add(row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
    sizer.Add(dlg.CreateButtonSizer(wx.OK | wx.CANCEL), 0,
              wx.EXPAND | wx.ALL, 8)
    dlg.SetSizerAndFit(sizer)

    def on_browse(event):
        with wx.FileDialog(
                dlg, "Link to image", defaultDir=folder,
                wildcard="Images (*.png;*.jpg;*.jpeg;*.gif)"
                         "|*.png;*.jpg;*.jpeg;*.gif",
                style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as files:
            if files.ShowModal() == wx.ID_OK:
                text.SetValue(files.GetPath())
    browse.Bind(wx.EVT_BUTTON, on_browse)
    try:
        return text.GetValue() if dlg.ShowModal() == wx.ID_OK else None
    finally:
        dlg.Destroy()


def size_to_scale(changed, value, natural, scales, proportional):
    """Scale factors after entering size value for axis changed ('x' or
    'y'). natural is the image's natural (width, height), scales the
    current (scale_x, scale_y). With proportional both axes get the new
    factor, otherwise the other axis keeps its own."""
    k = 0 if changed == 'x' else 1
    new = value / natural[k] if natural[k] else 1.0
    if proportional:
        return new, new
    result = list(scales)
    result[k] = new
    return tuple(result)


class ImageInspector(SidePanel):
    """Image Tool: insert new images and inspect/edit existing ones.

    Top section (always active):   insert a new image from a file.
    Bottom section (active only when cursor is on an Image texel):
        replace, resize, and crop the image.
    """

    def __init__(self, parent, editor, document):
        SidePanel.__init__(self, parent)
        self.editor   = editor
        self.document = document
        self.add_model(editor)
        self._image         = None  # the Image texel shown, or None
        self._content       = None  # its data (replaced by 'Replace')
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

        # --- Insert (always active): embedded or linked, from a menu ---
        add_section("Insert", self, sizer)
        self.btn_insert = wx.Button(self, label="Insert Image \u25be")
        self.btn_insert.Bind(wx.EVT_BUTTON, self._on_insert_menu)
        sizer.Add(self.btn_insert, 0,
                  wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, dip(5))

        # --- Source: only for external (linked) images ---
        self._source = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self._source, 0, wx.EXPAND)
        add_section("Source", self, self._source)
        self.txt_path = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.txt_path.SetMinSize((dip(150), -1))
        self.txt_path.Bind(wx.EVT_TEXT_ENTER, self._on_path)
        add_row(self._source, wx.StaticText(self, label="Path"),
                self.txt_path)
        self.lbl_status = wx.StaticText(self, label='')
        add_row(self._source, self.lbl_status)
        self.btn_embed = flat_button(self, "Embed", size=(-1, dip(28)))
        self.btn_embed.Bind(wx.EVT_BUTTON, self._on_embed)
        self._source.Add(self.btn_embed, 0,
                         wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, dip(5))

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

        # --- File ---
        add_section("File", self, sizer)
        self.btn_export = flat_button(self, "Export Image\u2026",
                                      size=(-1, dip(28)))
        self.btn_export.Bind(wx.EVT_BUTTON, self._on_export)
        sizer.Add(self.btn_export, 0,
                  wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, dip(5))

        self._set_inspector_enabled(False)

    def update(self):
        texel = self._get_image_texel()
        if texel is not None:
            self.refresh(texel)
        else:
            self.clear()

    # ------------------------------------------------------------------

    def _set_inspector_enabled(self, enabled, has_crop=False):
        for w in (self.btn_export, self.txt_size_x, self.txt_size_y,
                  self.txt_scale_x, self.txt_scale_y,
                  self.chk_proportional, self.btn_crop, self.btn_unset_crop):
            w.Enable(enabled)
        self.btn_unset_crop.Enable(enabled and has_crop)
        linked = enabled and self._image is not None \
            and self._image.content is None and bool(self._image.path)
        self._source.ShowItems(linked)  # external images only
        self.Layout()

    def refresh(self, image):
        """Enable inspector and fill values from the Image texel."""
        self._updating     = True
        self._image        = image
        self._content      = image.content
        self._current_crop = image.crop
        image_data = decode_cached(content_of(image, self._base_dir()))
        if image_data:
            self._natural_w = image_data.width_px
            self._natural_h = image_data.height_px
        self.txt_size_x.SetValue(self._natural_w * image.scale_x)
        self.txt_size_y.SetValue(self._natural_h * image.scale_y)
        self.txt_scale_x.SetValue(image.scale_x)
        self.txt_scale_y.SetValue(image.scale_y)
        self.chk_proportional.SetValue(image.proportional)
        self.txt_path.SetValue(image.path or '')
        self.lbl_status.SetLabel(self._status(image))
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
        self._image        = None
        self._content      = None
        self._crop_active  = False
        self._set_inspector_enabled(False)
        self.txt_path.SetValue('')
        self.lbl_status.SetLabel('')
        for btn in (self.btn_reset_w, self.btn_reset_h,
                    self.btn_reset_sx, self.btn_reset_sy):
            btn.set_x(False)

    # ------------------------------------------------------------------

    def _notify(self):
        if self._updating or self._image is None:
            return
        index = self.editor.index
        texel = next((t for _, _, t in get_path(self.editor.target.texel, index)
                      if isinstance(t, Image)), None)
        if texel is None:
            return
        scale_x = self.txt_scale_x.GetValue() or 1.0
        scale_y = self.txt_scale_y.GetValue() or 1.0
        self.editor.set_texel_attributes(
            index, texel,
            content=self._content, scale_x=scale_x, scale_y=scale_y,
            proportional=self.chk_proportional.GetValue(),
            crop=self._current_crop)

    def _on_size(self, changed):
        if self._updating or self._image is None:
            return
        v = (self.txt_size_x if changed == 'x' else self.txt_size_y).GetValue()
        if v is None:
            return
        scale_x, scale_y = size_to_scale(
            changed, v, (self._natural_w, self._natural_h),
            (self.txt_scale_x.GetValue() or 1.0,
             self.txt_scale_y.GetValue() or 1.0),
            self.chk_proportional.GetValue())
        self._update_fields(scale_x, scale_y)

    def _on_scale(self, changed):
        if self._updating or self._image is None:
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

    def _base_dir(self):
        """The document's folder (linked images)."""
        canvas = self.editor.canvas
        return canvas.builder.factory.base_dir if canvas else ''

    def _status(self, image):
        """Of a linked image: 'Loaded', else why not; '' for embedded."""
        if image.content is not None or not image.path:
            return ''
        if content_of(image, self._base_dir()) is not None:
            return 'Loaded'
        if is_url(image.path):
            return errors.get(image.path, 'Not loaded')
        return fetch(image.path, self._base_dir())[1] or 'Not loaded'

    def _set(self, **attributes):
        """Change the image at the cursor (one undo step), show it."""
        texel = self._get_image_texel()
        if texel is not None:
            self.editor.set_texel_attributes(self.editor.index, texel,
                                             **attributes)
        self.update()

    def _on_embed(self, event):
        """An external image becomes embedded (its path stays origin)."""
        image = self._get_image_texel()
        if image is None:
            return
        data = content_of(image, self._base_dir())
        if data is None and is_url(image.path) and load_url(image.path):
            data = content_of(image)
        if data is None:  # the status tells why
            return wx.Bell()
        self._set(content=data)

    def _on_path(self, event):
        """Link the image to the path entered; a URL is loaded now."""
        path = self.txt_path.GetValue().strip()
        if self._get_image_texel() is None or not path:
            return
        if is_url(path):
            with wx.BusyCursor():
                load_url(path)
        self._set(path=path)

    def _get_image_texel(self):
        """Return the Image texel at the current cursor position, or None."""
        return next((t for _, _, t in get_path(self.editor.target.texel, self.editor.index)
                     if isinstance(t, Image)), None)

    def _on_crop_toggle(self, event):
        editor = self.editor
        if not self._crop_active:
            if self._image is None:
                return
            if editor.canvas is not None:
                # find_box() (called from the controller's __init__) needs
                # the layout built up to this index; the build is lazy.
                editor.canvas.builder.assure_index(
                    editor.abs_idx(editor.index), editor.flow)
            path = get_path(editor.target.texel, editor.index)
            for depth, (i1, i2, texel) in enumerate(path):
                if isinstance(texel, Image):
                    controller = ImageCropController(editor, texel, i1, i2, depth)
                    editor.set_controller(controller)
                    self._crop_active = True
                    break
        else:
            path = get_path(editor.target.get_xtexel(), editor.index)
            editor.set_controller(NullController.match(editor, path))
            self._crop_active = False

    def _on_unset_crop(self, event):
        if self._image is None:
            return
        self._current_crop = None
        self._notify()
        self.btn_unset_crop.Enable(False)

    def _load_image_file(self):
        """Open file dialog; return the file's bytes or None."""
        with wx.FileDialog(
            self, "Choose image",
            defaultDir=self._last_image_dir,
            wildcard="Images (*.png;*.jpg;*.jpeg)|*.png;*.jpg;*.jpeg",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return None
            path = dlg.GetPath()
        self._last_image_dir = os.path.dirname(path)
        with open(path, 'rb') as f:
            return f.read()

    def insert_menu(self):
        menu = wx.Menu()
        for label, handler in (
                ("Embed Image from File\u2026", self._on_insert),
                ("Link to Image (File or URL)\u2026", self._on_link)):
            item = menu.Append(wx.ID_ANY, label)
            self.Bind(wx.EVT_MENU, handler, item)
        return menu

    def _on_insert_menu(self, event):
        menu = self.insert_menu()
        pos = self.btn_insert.GetPosition()
        self.PopupMenu(menu, wx.Point(
            pos.x, pos.y + self.btn_insert.GetSize().height))
        menu.Destroy()

    def _on_insert(self, event):
        data = self._load_image_file()
        if data is None:
            return
        self.editor.insert_texel(grouped([Image(data)]))

    def _on_link(self, event):
        """Insert an external image: linked to a URL or file."""
        path = link_source(ask_link(self, self._last_image_dir) or '',
                           self._base_dir())
        if path is None:
            return
        if is_url(path):
            with wx.BusyCursor():
                load_url(path)
        else:
            self._last_image_dir = os.path.dirname(
                os.path.join(self._base_dir(), path))
        self.editor.insert_texel(grouped([Image(path=path)]))

    def _on_export(self, event):
        if self._image is None:
            return
        data = content_of(self._image, self._base_dir())
        if data is None:
            return
        ext = image_extension(data)
        wildcard = "Image files (*%s)|*%s|All files (*.*)|*.*" % (ext, ext)
        with wx.FileDialog(
            self, "Export Image",
            defaultDir=self._last_image_dir,
            defaultFile='image' + ext,
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
    """Show ImageInspector next to a canvas with an inline image."""
    import os
    from ..textmodel.texeltree import Text, NL
    from ..core.document import Document
    from ..core.stylesheet import testsheet
    from ..layout.rowfactory import Factory
    from ..layout.cairodevice import CairoDevice
    from ..layout.pagebuilder import PageBuilder
    from ..texteditor.editor import Editor
    from ..texteditor.textcanvas import TextCanvas

    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    with open(os.path.join(here, 'test', 'red.png'), 'rb') as f:
        data = f.read()

    doc = Document()
    doc.textmodel.texel = grouped([Text("Before "), Image(data), Text(" after."), NL])

    app   = wx.App(False)
    frame = wx.Frame(None, title="ImageInspector Demo", size=(700, 400))

    factory = Factory(testsheet, device=CairoDevice())
    builder = PageBuilder(doc.textmodel, factory)
    builder.rebuild()

    editor = Editor(doc.textmodel)
    canvas = TextCanvas(frame, doc.textmodel, builder, editor)
    editor.canvas = canvas
    editor.index  = 7  # land on the Image texel

    panel = ImageInspector(frame, editor, doc)

    sizer = wx.BoxSizer(wx.HORIZONTAL)
    sizer.Add(canvas, 1, wx.EXPAND)
    sizer.Add(panel,  0, wx.EXPAND)
    frame.SetSizer(sizer)

    panel.update()
    frame.Show()
    app.MainLoop()


if __name__ == '__main__':
    demo_00()
