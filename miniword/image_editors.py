import wx
from .editorbase import Editor
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
                    return child, (cx, cy)
    return None


def find_image_near(layout, i):
    """Return adjusted index if an image is at i or i-1, else None.

    ImageBox.get_index returns 1 for right-half clicks, placing the cursor
    one past the image end.  Trying i-1 corrects for this.
    """
    if find_image_at(layout, i) is not None:
        return i
    if i > 0 and find_image_at(layout, i - 1) is not None:
        return i - 1
    return None


_HANDLE_DEFS = [
    # (name, x_factor, y_factor)  — factor in [0, 0.5, 1] of image rect
    ('NW', 0.0, 0.0), ('N', 0.5, 0.0), ('NE', 1.0, 0.0),
    ('E',  1.0, 0.5),
    ('SE', 1.0, 1.0), ('S', 0.5, 1.0), ('SW', 0.0, 1.0),
    ('W',  0.0, 0.5),
]

# For each handle: (dx_sign, dy_sign) where positive means "scale up"
_HANDLE_SCALE = {
    'NW': (-1, -1), 'N': (0, -1), 'NE': (1, -1),
    'E':  (1,  0),
    'SE': (1,  1),  'S': (0,  1), 'SW': (-1, 1),
    'W':  (-1, 0),
}


class ImageSizeEditor(Editor):
    """Resize images by dragging handles on the image border.

    During drag only a preview is drawn; the model is not touched.
    The scale change is committed to the texel on mouse-release.
    """

    hide_cursor       = True
    auto_installable  = False
    click_installable = True

    _state = None

    @staticmethod
    def condition(view, index_texels, sel_texels):
        return find_image_near(view.layout, view.index) is not None

    def install(self, view, index):
        adj = find_image_near(view.layout, index)
        if adj is not None:
            index = adj
        super().install(view, index)
        res = find_image_at(view.layout, index)
        if res is None:
            self.box = None
            return
        self.box, self.position = res
        self.clear_drag()
        self.state = self.compute_state()

    def compute_state(self):
        """Compute the state from box."""        
        # Our model state consists of:
        # - lower left corner (default: 0,0)
        # - image width
        # - image height
        w = self.box.width
        h = self.box.height        
        return (0, 0), w, h
        
    def find_box(self):
        return find_image_at(self.view.layout, self.index)

    def get_handles(self):
        tb = self.box
        (x, y), w, h = self.state
        for name, fx, fy in _HANDLE_DEFS:
            yield name, x+fx * w, y+fy * h

    def on_motion(self, event):
        if not self._drag_handle:
            return

        # 1. Aktuelle Mausposition und Differenz zum Start
        p = self.window_to_box(event.Position)
        dx = p[0] - self._drag_start[0]
        dy = p[1] - self._drag_start[1]

        # 2. Faktoren aus der Definition holen
        # Wir suchen das Tupel (name, x_f, y_f)
        h_name, x_f, y_f = next(h for h in _HANDLE_DEFS if h[0] == self._drag_handle)

        # compute the initial state from box
        (x, y), w, h = self.compute_state()

        # compute new state from the drag
        new_x, new_y, new_w, new_h = x, y, w, h
        # 3. Logik für X-Achse
        if x_f == 0.0:   # Linke Kante (W)
            diff = min(dx, w - 1) # Nicht kleiner als 1px
            new_x += diff
            new_w -= diff
        elif x_f == 1.0: # Rechte Kante (E)
            new_w = max(1, w + dx)

        # 4. Logik für Y-Achse
        if y_f == 0.0:   # Obere Kante (N)
            diff = min(dy, h - 1)
            new_y += diff
            new_h -= diff
        elif y_f == 1.0: # Untere Kante (S)
            new_h = max(1, h + dy)

        # 5. Proportionaler Resize
        if self.texel.proportional or event.ShiftDown():
            aspect = w / h
            if x_f == 0.5:          # N oder S: Höhe treibt
                new_w = max(1, new_h * aspect)
                new_x = (w - new_w) / 2
            elif y_f == 0.5:        # E oder W: Breite treibt
                new_h = max(1, new_w / aspect)
                new_y = (h - new_h) / 2
            else:                   # Ecke: dominante Achse
                if abs(dx) >= abs(dy):
                    new_h = max(1, new_w / aspect)
                    if y_f == 0.0:
                        new_y = h - new_h
                else:
                    new_w = max(1, new_h * aspect)
                    if x_f == 0.0:
                        new_x = w - new_w

        self.state = ((new_x, new_y), new_w, new_h)
        self.view.refresh()
    

    _CURSOR_MAP = {
        'N':  wx.CURSOR_SIZENS,   'S':  wx.CURSOR_SIZENS,
        'E':  wx.CURSOR_SIZEWE,   'W':  wx.CURSOR_SIZEWE,
        'NE': wx.CURSOR_SIZENESW, 'SW': wx.CURSOR_SIZENESW,
        'NW': wx.CURSOR_SIZENWSE, 'SE': wx.CURSOR_SIZENWSE,
    }

    def get_cursor(self, handle_id):
        return self._CURSOR_MAP.get(handle_id, wx.CURSOR_SIZING)

    def draw_overlay(self, gc):
        if self.position is None:
            return
        bx, by = self.position
        zoom = self.view.zoom
        lw = 1.0 / zoom
        (x, y), w, h = self.state

        # Outline at preview size
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
            self.view.set_texel_attributes(
                self.index, Image, scale_x=new_scale_x, scale_y=new_scale_y)
        self.state = self.compute_state()


class ImageCropEditor(Editor):
    """Adjust image crop margins by dragging 4 edge handles.

    Shows the full image with cropped-out areas dimmed.
    Preview-only during drag; committed on release.
    """

    hide_cursor       = True
    auto_installable  = False
    click_installable = False
    _HIT_PX           = 8

    _preview_crop = None   # [left, right, top, bottom] while editing

    _CURSOR_MAP = {
        'L': wx.CURSOR_SIZEWE, 'R': wx.CURSOR_SIZEWE,
        'T': wx.CURSOR_SIZENS, 'B': wx.CURSOR_SIZENS,
    }

    def get_cursor(self, handle_id):
        return self._CURSOR_MAP.get(handle_id, wx.CURSOR_SIZING)

    def install(self, view, index):
        super().install(view, index)
        res = find_image_at(view.layout, index)
        if res is None:
            self.box = None
            return
        self.box, self.position = res
        self._src_w = self.box.src_w
        self._src_h = self.box.src_h
        self._preview_crop = list(self.texel.crop) if self.texel.crop else [0, 0, 0, 0]

    def find_box(self):
        return find_image_at(self.view.layout, self.index)

    def get_handles(self):
        for name, (hx, hy) in self._handle_positions(self._preview_crop).items():
            yield name, hx, hy

    def draw_handles(self, gc):
        pass   # handles are drawn inside draw_overlay

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
        self.view.refresh()

    def on_motion(self, event):
        if not self._drag_handle:
            return
        p = self.window_to_box(event.Position)
        self._total_dx = p[0] - self._drag_start[0]
        self._total_dy = p[1] - self._drag_start[1]
        sx, sy = self.texel.scale_x, self.texel.scale_y
        sw, sh = self._src_w, self._src_h
        cl, cr, ct, cb = self._drag_start_crop
        min_px = 1
        if self._drag_handle == 'L':
            cl = max(0, min(cl + self._total_dx / sx, sw - cr - min_px))
        elif self._drag_handle == 'R':
            cr = max(0, min(cr - self._total_dx / sx, sw - cl - min_px))
        elif self._drag_handle == 'T':
            ct = max(0, min(ct + self._total_dy / sy, sh - cb - min_px))
        elif self._drag_handle == 'B':
            cb = max(0, min(cb - self._total_dy / sy, sh - ct - min_px))
        self._preview_crop = [cl, cr, ct, cb]
        self.view.refresh()

    def draw_overlay(self, gc):
        if self.position is None:
            return
        tb = self.box
        bx, by = self.position
        sx, sy = self.texel.scale_x, self.texel.scale_y
        sw, sh = self._src_w, self._src_h
        zoom  = self.view.zoom
        lw    = 1.5 / zoom
        hs    = 7.0 / zoom

        cl, cr, ct, cb = self._preview_crop

        if self._drag_handle:
            orig_cl, _, orig_ct, _ = self._drag_start_crop
        else:
            orig_cl, orig_ct = cl, ct

        # position of the preview crop box in doc coords
        cx = bx + (cl - orig_cl) * sx
        cy = by + (ct - orig_ct) * sy
        cw = (sw - cl - cr) * sx
        ch = (sh - ct - cb) * sy

        # Full image position in doc coords
        fx = bx - orig_cl * sx
        fy = by - orig_ct * sy
        fw = sw * sx
        fh = sh * sy

        # White background
        gc.set_source_rgb(1.0, 1.0, 1.0)
        gc.rectangle(fx, fy, fw, fh)
        gc.fill()

        # Full (uncropped) bitmap dimmed
        full_bmp = tb.full_bitmap if tb.full_bitmap is not None else tb.bitmap
        if full_bmp is not None:
            tb.device.draw_bitmap(full_bmp, fx, fy, fw, fh, gc)
        else:
            gc.set_source_rgb(0.8, 0.8, 0.8)
            gc.rectangle(fx, fy, fw, fh)
            gc.fill()

        # Grey overlay on cropped-out margins
        gc.set_source_rgba(1.0, 1.0, 1.0, 0.65)
        for rx, ry, rw, rh in [
            (fx,      fy,      fw,         ct * sy),   # top
            (fx,      cy + ch, fw,         cb * sy),   # bottom
            (fx,      cy,      cl * sx,    ch),         # left
            (cx + cw, cy,      cr * sx,    ch),         # right
        ]:
            if rw > 0 and rh > 0:
                gc.rectangle(rx, ry, rw, rh)
                gc.fill()

        # Crop border
        gc.set_source_rgb(0.0, 0.4, 1.0)
        gc.set_line_width(lw)
        gc.rectangle(cx, cy, cw, ch)
        gc.stroke()

        # Handles (positions are box-local; add cx, cy to get doc coords)
        for name, (hx, hy) in self._handle_positions(self._preview_crop).items():
            ax, ay = cx + hx - hs / 2, cy + hy - hs / 2
            gc.set_source_rgb(1.0, 1.0, 1.0)
            gc.rectangle(ax, ay, hs, hs)
            gc.fill()
            gc.set_source_rgb(0.0, 0.4, 1.0)
            gc.set_line_width(lw)
            gc.rectangle(ax, ay, hs, hs)
            gc.stroke()

    def commit(self):
        crop = tuple(int(round(v)) for v in self._preview_crop)
        self.view.set_texel_attributes(self.index, Image, crop=crop)


def _setup_demo():
    import os
    import wx
    from .images import Image
    from .textmodel.texeltree import grouped, Text, NL
    from .document import Document
    from .documentview import DocumentView

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(here, 'test', 'red.png'), 'rb') as f:
        data = f.read()

    doc = Document()
    doc.blobs = {'red.png': data}
    doc.textmodel.texel = grouped([Text('Before '), Image('red.png'), Text(' after.'), NL])

    app   = wx.App(True)
    frame = wx.Frame(None, title='ImageSizeEditor demo', size=(420, 300))
    view  = DocumentView(frame, doc)
    view.builder.factory.blobs = doc.blobs
    return app, frame, view

def demo_00():
    """Image resize"""
    app, frame, view = _setup_demo()
    view.install_editor(ImageSizeEditor(), 7)
    frame.Show()
    app.MainLoop()

def demo_01():
    """Image crop"""
    app, frame, view = _setup_demo()
    view.install_editor(ImageCropEditor(), 7)
    frame.Show()
    app.MainLoop()
