"""BoxController extends ElementController with box, handle and drag support.

Texels and boxes are immutable: every committed change replaces the texel
and triggers a re-layout, so a cached box would become stale.  Controllers
are therefore not mutated in place — match() constructs a fresh instance
(with current texel, i1, i2, depth) after each such change, which re-queries
find_box() in __init__.

i1, i2 and depth are assumed to be stable over the controller's lifetime.
"""

import wx
from ..textmodel.texeltree import iter_childs
from .controller import ElementController



class BoxController(ElementController):
    """Base class for all texel controllers with wx-specific drag/handle support.
    """
    auto_installable   = True

    ### set in __init__, via find_box()
    box                = None    # the current box
    box_origin         = None    # top-left corner of the box in layout coordinates
    i0_box             = None    # document start position of the box (differs from
                                 # i1 for table fragments)

    ### attributes changed during drag
    _drag_handle      = None
    _drag_start       = None    # position where drag was started (box-local)
    _drag_last        = None    # last drag position (box-local)
    _total_dx         = 0.0
    _total_dy         = 0.0

    ### constants
    _HANDLE_PX    = 7    # handle size in screen pixels
    _HIT_PX       = 6    # hit radius in screen pixels

    # ------------------------------------------------------------------
    # Protocol — must override in subclasses

    def __init__(self, editor, texel, i1, i2, depth):
        super().__init__(editor, texel, i1, i2, depth)
        self.i0_box, self.box_origin, self.box = self.find_box()

    def find_box(self):
        """Return (i0, (x0, y0), box) — the box's document start position,
        its top-left corner in document coords, and the box itself.

        Called once from __init__; do not cache beyond the controller's lifetime.
        """
        raise NotImplementedError()

    def commit(self):
        """Persist the current preview state to the model."""
        raise NotImplementedError

    def get_handles(self):
        """Yield (name, x, y) for each drag handle in box-local coordinates."""
        raise NotImplementedError
        yield 'nothing', 0, 0

    # ------------------------------------------------------------------
    # Drawing

    def draw(self, gc):
        """Draw cursor, selection, overlay, handles.

        Override entirely in subclasses that need different rendering order
        (e.g. MatrixEditor suppresses the text cursor).
        """
        self.draw_selection(gc)
        self.draw_cursor(gc)
        self.draw_overlay(gc)
        self.draw_handles(gc)

    def draw_selection(self, gc):
        """Draw the selection. """
        self.editor.canvas.draw_selection(gc)

    def draw_cursor(self, gc):
        """Draw the insertion cursor. """
        self.editor.canvas.draw_cursor(gc)

    def draw_overlay(self, gc):
        """Draw editor-specific decorations (preview outlines, …)."""
        pass
        
    def draw_handles(self, gc):
        """Draw the standard square handles returned by get_handles()."""
        if self.box_origin is None:
            return
        bx, by = self.box_origin
        zoom = self.editor.canvas.zoom
        lw = 1.0 / zoom
        hs = self._HANDLE_PX / zoom
        for name, hx, hy in self.get_handles():
            ax, ay = bx + hx - hs / 2, by + hy - hs / 2
            gc.set_source_rgb(0.0, 0.4, 1.0) if name == self._drag_handle \
                else gc.set_source_rgb(1.0, 1.0, 1.0)
            gc.rectangle(ax, ay, hs, hs)
            gc.fill()
            gc.set_source_rgb(0.3, 0.3, 0.3)
            gc.set_line_width(lw)
            gc.rectangle(ax, ay, hs, hs)
            gc.stroke()

    # ------------------------------------------------------------------
    # Drag

    def start_drag(self, handle, x, y):
        """Begin a drag from box-local position (x, y) for the given handle."""
        self._drag_start = x, y
        self._drag_handle = handle
        self.editor.canvas.refresh()

    def clear_drag(self):
        """Reset drag state after commit or cancel."""
        self._drag_start  = None
        self._drag_handle = None


    # ------------------------------------------------------------------
    # Hit testing

    def hit_test(self, x, y):
        """Return the handle name under (x, y) in box-local coords, or None."""
        hit_r = self._HIT_PX / self.editor.canvas.zoom
        for name, hx, hy in self.get_handles():
            if abs(x - hx) <= hit_r and abs(y - hy) <= hit_r:
                return name
        return None

    def get_cursor(self, handle_id):
        """Return a wx cursor stock id appropriate for the given handle."""
        return wx.CURSOR_SIZING

    # ------------------------------------------------------------------
    # Coordinate conversion

    def window_to_box(self, pos):
        """Convert a window pixel position to box-local document coordinates.

        Uses the cached box_origin rather than re-querying find_box(), because
        the layout is stable for the lifetime of this controller instance.
        """
        x, y = self.editor.canvas.window_to_content(pos)
        x0, y0 = self.box_origin
        return x - x0, y - y0

    # ------------------------------------------------------------------
    # Events. Note: returns True (= event consumed) and False (otherwise)

    def on_leftdown(self, event):
        """Handle left-button press: hit-test and start a drag if a
        handle is hit.

        Returns True if the event was consumed, False otherwise.
        """
        x, y = self.window_to_box(event.Position)
        handle = self.hit_test(x, y)
        if handle is None:
            return False
        self.start_drag(handle, x, y)
        return True

    def on_leftup(self, event):
        """Commit and clear the drag on left-button release."""
        if self._drag_handle is not None:
            self.commit()
            self.clear_drag()
            return True
        return False

    def drag_handle(self, handle, dx, dy, shift, ctrl):
        """Update preview state while dragging. Override in subclasses."""
        pass

    def on_motion(self, event):
        """Update over cursor, update the preview state while dragging."""
        editor = self.editor
        flow = editor.flow
        canvas = editor.canvas
        if self._drag_handle is not None:
            canvas.SetCursor(wx.Cursor(self.get_cursor(self._drag_handle)))
            p = self.window_to_box(event.Position)
            dx = p[0] - self._drag_start[0]
            dy = p[1] - self._drag_start[1]
            self.drag_handle(self._drag_handle, dx, dy,
                             event.ShiftDown(), event.ControlDown())
            canvas.refresh()
            return True

        # Hover cursor shape near handles
        if not event.LeftIsDown():
            x, y = self.window_to_box(event.Position)
            hit = self.hit_test(x, y)
            cursor = wx.CURSOR_IBEAM if hit is None else self.get_cursor(hit)
            canvas.SetCursor(wx.Cursor(cursor))
        if not event.LeftIsDown():
            event.Skip() # XXX needed?
            return False
        x, y = canvas.window_to_content(event.Position)
        i = canvas.layout.get_index(x, y, flow)
        if i is not None:
            editor.set_index(editor.local_idx(i), extend=True)
        return True


