"""Editors are registered in DocumentView.editor_registry (a flat list of
editor classes).  Two flags on the class control when an editor is activated:

  auto_installable  = True   Managed by update_editor(); installed when
                             match() returns not None after a cursor move.
  click_installable = True   Activated on mouse click.

Editors are removed under the following conditions:
- The docview.cursor is moved
- the document signals "inserted" or "removed"
- the editor descides to be finished and calls docview.remove_editor

When the document signals "properties_changed", the editor is
validated and updated.

Since texels and boxes are immutable, every small parameter change
committed in the editor leads to a replacement of the texel and a
re-layout of the pages. Therefore, neither the texel nor the box
remains stable over the lifetime of the editor.

Docview calls "reinstall" whenever this occurs, allowing the editor to
update its cached versions of the texel and boxes.

It is assumed that the index positions and depth of the texel, as well
as the origin of the box, do not change during the editor's lifetime.

"""

import wx
from ..textmodel.texeltree import iter_childs



class TexelEditor:
    """Base class for all texel editors.
    """
    is_null            = False
    auto_installable   = True    # managed by update_editor() / condition()
    click_installable  = False   # activated by mouse click

    ### set in init
    docview            = None
    i1                 = None    # the start of the texel
    i2                 = None    # the end of the texel
    depth              = None    # the depth of the texel in the hierarchy

    ### set in install
    texel              = None    # the primary texel being edited
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

    def __init__(self, docview, i1, i2, depth):
        self.docview = docview
        self.i1 = i1
        self.i2 = i2
        self.depth = depth

    def find_box(self):
        """Return (box, (x0, y0)) — the box and its top-left in document coords.

        Called on every paint pass; do not cache.
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
    # Lifecycle

    @staticmethod
    def match(view, path):
        """Returns None or the matching (i1, i2, depth, texel)."""
        # NOTE: we can extend this mechanism later so that list of
        # options is returned, where the first entry is the preferend
        # one.
        return None

    def install(self, texel):
        """Attach the editor to index range i1..i2 for editing texel. """
        self.texel = texel
        i0, origin, box = self.find_box()
        self.i0_box = i0
        self.box_origin = origin
        self.box = box
        
    def reinstall(self, texel):
        """Refresh all cached references after a model change."""
        self.install(texel)

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
        self.docview.draw_selection(gc)
        
    def draw_cursor(self, gc):
        """Draw the insertion cursor. """
        self.docview.draw_cursor(gc)

    def draw_overlay(self, gc):
        """Draw editor-specific decorations (preview outlines, …)."""
        pass
        
    def draw_handles(self, gc):
        """Draw the standard square handles returned by get_handles()."""
        if self.box_origin is None:
            return
        bx, by = self.box_origin
        zoom = self.docview.zoom
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
        self.docview.refresh()

    def clear_drag(self):
        """Reset drag state after commit or cancel."""
        self._drag_start  = None
        self._drag_handle = None


    # ------------------------------------------------------------------
    # Hit testing

    def hit_test(self, x, y):
        """Return the handle name under (x, y) in box-local coords, or None."""
        hit_r = self._HIT_PX / self.docview.zoom
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
        the layout is stable between install() and the next model change.
        """
        x, y = self.docview.window_to_content(pos)
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
        if self._drag_handle is not None:
            self.docview.SetCursor(wx.Cursor(self.get_cursor(self._drag_handle)))
            p = self.window_to_box(event.Position)
            dx = p[0] - self._drag_start[0]
            dy = p[1] - self._drag_start[1]
            self.drag_handle(self._drag_handle, dx, dy, event.ShiftDown(), event.ControlDown())
            self.docview.refresh()
            return True
        
        # Hover cursor shape near handles
        if not event.LeftIsDown():
            x, y = self.window_to_box(event.Position)
            hit = self.hit_test(x, y)
            cursor = wx.CURSOR_IBEAM if hit is None else self.get_cursor(hit)
            self.docview.SetCursor(wx.Cursor(cursor))
        if not event.LeftIsDown():
            event.Skip() # XXX needed?
            return False
        docview = self.docview
        x, y = docview.window_to_content(event.Position)
        i = docview.layout.get_index(x, y)
        if i is not None:
            docview.set_index(i, extend=True)
        return True
                
    def on_key(self, keycode, event):
        """Handle a key press.  ESC removes the editor; returns True
        if consumed."""
        if keycode == wx.WXK_ESCAPE:
            self.docview.remove_editor()
            return True
        return False

    def handle_action(self, action, shift, ctx):
        return False

    # ------------------------------------------------------------------
    # Clipboard delegation

    def copy(self):
        """Delegate copy to the document view (subclasses may override)."""
        self.docview.copy()

    def cut(self):
        """Delegate cut to the document view (subclasses may override)."""
        self.docview.cut()

    def paste(self):
        """Delegate paste to the document view (subclasses may override)."""
        self.docview.paste()

    # ------------------------------------------------------------------
    # Queries — return None to fall back to DocumentView default

    def selected(self, i1, i2):
        """Return list of (i1, i2) ranges for the logical selection, or None.

        None → DocumentView uses layout.extend_range(i1, i2).
        Override in editors that need non-default selection semantics
        (e.g. MatrixEditor returns complete table cells).
        """
        return None

    def adjust_viewport(self):
        """Return a scroll target (x, y) in document coordinates, or None.

        None → DocumentView uses its default cursor-follow behaviour.
        Override when the editing location differs from the cursor position
        (e.g. FootnoteEditor scrolls to the footnote area, not the anchor).
        """
        return None

