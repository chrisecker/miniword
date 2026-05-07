import wx
from ..layout.editorbase import TexelEditor
from .images import Image, ImageBox


def find_image_at(layout, index):
    """Return (ImageBox, (cx, cy)) for the ImageBox adjacent to index, or None."""
    for p1, p2, px, py, page in layout.iter_boxes(0, 0, 0):
        if not (p1 <= index <= p2):
            continue
        for r1, r2, rx, ry, row in page.iter_boxes(p1, px, py):
            if not (r1 <= index <= r2):
                continue
            for ci1, ci2, cx, cy, child in row.iter_boxes(r1, rx, ry):
                if isinstance(child, ImageBox) and ci1 <= index < ci2:
                    return ci1, (cx, cy), child
    return None



_HANDLE_DEFS = [
    # (name, x_factor, y_factor)  — factor in [0, 0.5, 1] of image rect
    ('NW', 0.0, 0.0), ('N', 0.5, 0.0), ('NE', 1.0, 0.0),
    ('E',  1.0, 0.5),
    ('SE', 1.0, 1.0), ('S', 0.5, 1.0), ('SW', 0.0, 1.0),
    ('W',  0.0, 0.5),
]


class ImageEditor(TexelEditor):
    @staticmethod
    def match(view, path):
        for depth, (i1, i2, texel) in enumerate(path):
            if isinstance(texel, Image):
                return i1, i2, depth, texel

    def install(self, texel):
        super().install(texel)
        self.clear_drag()

    def find_box(self):
        return find_image_at(self.docview.layout, self.i1)

    def get_cursor(self, handle_id):
        return self._CURSOR_MAP.get(handle_id, wx.CURSOR_SIZING)

    def draw_cursor(self, painter):
        # supress the drawing of a cursor!
        pass
        

class ImageSizeEditor(ImageEditor):
    """Resize images by dragging handles on the image border.

    During drag only a preview is drawn; the model is not touched.
    The scale change is committed to the texel on mouse-release.
    """

    auto_installable  = False
    click_installable = True
    state             = None

    _CURSOR_MAP = {
        'N':  wx.CURSOR_SIZENS,   'S':  wx.CURSOR_SIZENS,
        'E':  wx.CURSOR_SIZEWE,   'W':  wx.CURSOR_SIZEWE,
        'NE': wx.CURSOR_SIZENESW, 'SW': wx.CURSOR_SIZENESW,
        'NW': wx.CURSOR_SIZENWSE, 'SE': wx.CURSOR_SIZENWSE,
    }

    def install(self, texel):
        super().install(texel)
        self.state = self.compute_state()

    def compute_state(self):
        """Compute the state from box."""
        w = self.box.width
        h = self.box.height
        return (0, 0), w, h

    def get_handles(self):
        (x, y), w, h = self.state
        for name, fx, fy in _HANDLE_DEFS:
            yield name, x+fx * w, y+fy * h

    def drag_handle(self, handle, dx, dy, shift, ctrl):
        h_name, x_f, y_f = next(h for h in _HANDLE_DEFS if h[0] == handle)

        (x, y), w, h = self.compute_state()

        new_x, new_y, new_w, new_h = x, y, w, h
        if x_f == 0.0:
            diff = min(dx, w - 1)
            new_x += diff
            new_w -= diff
        elif x_f == 1.0:
            new_w = max(1, w + dx)

        if y_f == 0.0:
            diff = min(dy, h - 1)
            new_y += diff
            new_h -= diff
        elif y_f == 1.0:
            new_h = max(1, h + dy)

        if self.texel.proportional or shift:
            aspect = w / h
            if x_f == 0.5:
                new_w = max(1, new_h * aspect)
                new_x = (w - new_w) / 2
            elif y_f == 0.5:
                new_h = max(1, new_w / aspect)
                new_y = (h - new_h) / 2
            else:
                if abs(dx) >= abs(dy):
                    new_h = max(1, new_w / aspect)
                    if y_f == 0.0:
                        new_y = h - new_h
                else:
                    new_w = max(1, new_h * aspect)
                    if x_f == 0.0:
                        new_x = w - new_w

        self.state = ((new_x, new_y), new_w, new_h)

    def draw_overlay(self, gc):
        bx, by = self.box_origin
        zoom = self.docview.zoom
        lw = 1.0 / zoom
        (x, y), w, h = self.state

        gc.set_source_rgb(0.3, 0.3, 0.3)
        gc.set_line_width(lw)
        gc.rectangle(bx + x, by + y, w, h)

        gc.stroke()
        
    def commit(self):
        _, w0, h0 = self.compute_state()
        _, w, h = self.state
        new_scale_x = (w / w0) * self.texel.scale_x
        new_scale_y = (h / h0) * self.texel.scale_y
        if abs(new_scale_x - self.texel.scale_x) > 1e-6 or \
           abs(new_scale_y - self.texel.scale_y) > 1e-6:
            self.docview.set_texel_attributes(
                self.i1, self.texel, scale_x=new_scale_x, scale_y=new_scale_y)
        self.state = self.compute_state()


class ImageCropEditor(ImageEditor):
    """Adjust image crop margins by dragging 4 edge handles.

    Shows the full image with cropped-out areas dimmed.
    Preview-only during drag; committed on release.
    """

    auto_installable  = False
    click_installable = False
    _HIT_PX           = 8

    _preview_crop = None   # [left, right, top, bottom] while editing

    _CURSOR_MAP = {
        'L': wx.CURSOR_SIZEWE, 'R': wx.CURSOR_SIZEWE,
        'T': wx.CURSOR_SIZENS, 'B': wx.CURSOR_SIZENS,
    }

    def install(self, texel):
        super().install(texel)
        self._src_w = self.box.image_data.width_px
        self._src_h = self.box.image_data.height_px
        self._preview_crop = list(texel.crop) if texel.crop else [0, 0, 0, 0]

    def get_handles(self):
        cl, cr, ct, cb = self._preview_crop
        if self._drag_handle:
            orig_cl, _, orig_ct, _ = self._drag_start_crop
        else:
            orig_cl, orig_ct = cl, ct
        ox = (cl - orig_cl) * self.texel.scale_x
        oy = (ct - orig_ct) * self.texel.scale_y
        for name, (hx, hy) in self._handle_positions(self._preview_crop).items():
            yield name, ox + hx, oy + hy

    def _handle_positions(self, crop):
        """Return dict of handle_name → (x, y) in box-local coords."""
        sx, sy = self.texel.scale_x, self.texel.scale_y
        cl, cr, ct, cb = crop
        sw, sh = self._src_w, self._src_h
        cw = (sw - cl - cr) * sx
        ch = (sh - ct - cb) * sy
        mx = cw / 2
        my = ch / 2
        return {
            'L': (0,   my),
            'R': (cw,  my),
            'T': (mx,  0),
            'B': (mx,  ch),
        }

    def start_drag(self, handle, x, y):
        super().start_drag(handle, x, y)
        self._drag_start_crop = list(self._preview_crop)
        self.docview.refresh()

    def drag_handle(self, handle, dx, dy, shift, ctrl):
        sx, sy = self.texel.scale_x, self.texel.scale_y
        sw, sh = self._src_w, self._src_h
        cl, cr, ct, cb = self._drag_start_crop
        min_px = 1
        if handle == 'L':
            cl = max(0, min(cl + dx / sx, sw - cr - min_px))
        elif handle == 'R':
            cr = max(0, min(cr - dx / sx, sw - cl - min_px))
        elif handle == 'T':
            ct = max(0, min(ct + dy / sy, sh - cb - min_px))
        elif handle == 'B':
            cb = max(0, min(cb - dy / sy, sh - ct - min_px))
        self._preview_crop = [cl, cr, ct, cb]

    def draw_overlay(self, gc):
        tb = self.box
        bx, by = self.box_origin
        sx, sy = self.texel.scale_x, self.texel.scale_y
        sw, sh = self._src_w, self._src_h
        zoom  = self.docview.zoom
        lw    = 1.5 / zoom
        hs    = 7.0 / zoom

        cl, cr, ct, cb = self._preview_crop

        if self._drag_handle:
            orig_cl, _, orig_ct, _ = self._drag_start_crop
        else:
            orig_cl, orig_ct = cl, ct

        cx = bx + (cl - orig_cl) * sx
        cy = by + (ct - orig_ct) * sy
        cw = (sw - cl - cr) * sx
        ch = (sh - ct - cb) * sy

        fx = bx - orig_cl * sx
        fy = by - orig_ct * sy
        fw = sw * sx
        fh = sh * sy

        gc.set_source_rgb(1.0, 1.0, 1.0)
        gc.rectangle(fx, fy, fw, fh)
        gc.fill()

        full_bmp = tb.image_data.bitmap
        if full_bmp is not None:
            tb.device.draw_bitmap(full_bmp, fx, fy, fw, fh, gc)
        else:
            gc.set_source_rgb(0.8, 0.8, 0.8)
            gc.rectangle(fx, fy, fw, fh)
            gc.fill()

        gc.set_source_rgba(1.0, 1.0, 1.0, 0.65)
        for rx, ry, rw, rh in [
            (fx,      fy,      fw,         ct * sy),
            (fx,      cy + ch, fw,         cb * sy),
            (fx,      cy,      cl * sx,    ch),
            (cx + cw, cy,      cr * sx,    ch),
        ]:
            if rw > 0 and rh > 0:
                gc.rectangle(rx, ry, rw, rh)
                gc.fill()

        gc.set_source_rgb(0.0, 0.4, 1.0)
        gc.set_line_width(lw)
        gc.rectangle(cx, cy, cw, ch)
        gc.stroke()


    def commit(self):
        crop = tuple(int(round(v)) for v in self._preview_crop)
        self.docview.set_texel_attributes(self.i1, self.texel, crop=crop)


### Register ImageSizeEditor. CropEditor does not need to be
### registered, because it is not automatically selected.

from ..ui.documentview import DocumentView
DocumentView.editor_registry.append(ImageSizeEditor)

        
def _setup_demo():
    import os
    import wx
    from .images import Image
    from ..textmodel.texeltree import grouped, Text, NL
    from ..core.document import Document
    from ..ui.documentview import DocumentView

    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    with open(os.path.join(here, 'test', 'red.png'), 'rb') as f:
        data = f.read()

    doc = Document()
    doc.blobs = {'red.png': data}
    doc.textmodel.texel = grouped([Text('Before '), Image('red.png'), Text(' after.'), NL])

    from ..ui.documentview import get_path, get_texel

    r = get_path(doc.textmodel.texel, 7)
    for x in r:
        print(x)
    print(get_texel(doc.textmodel.texel, 7, 1))

    app   = wx.App(True)
    frame = wx.Frame(None, title='ImageSizeEditor demo', size=(420, 300))
    view  = DocumentView(frame, doc)
    view.builder.factory.blobs = doc.blobs
    return app, frame, view

def demo_00():
    """Image resize"""
    from ..ui.documentview import get_texel
    app, frame, view = _setup_demo()
    editor = ImageSizeEditor(view, 7, 8, 1)
    texel = get_texel(view.model.texel, 7, 1)
    view.index = 7
    view.install_editor(editor, texel)
    frame.Show()
    app.MainLoop()

def demo_01():
    """Image crop"""
    from ..ui.documentview import get_texel
    app, frame, view = _setup_demo()
    editor = ImageCropEditor(view, 7, 8, 1)
    texel = get_texel(view.model.texel, 7, 1)
    view.index = 7
    view.install_editor(editor, texel)
    frame.Show()
    app.MainLoop()
