"""Inline editors for DocumentView elements.

AUTHOR GUIDE — writing a new Editor subclass
=============================================

Registration
------------
Editors are registered in DocumentView.editor_registry (a flat list of
editor classes).  Two flags on the class control when an editor is activated:

  auto_installable  = True   Managed by update_editor(); installed when
                             condition() returns True after a cursor move.
  click_installable = True   Activated on mouse click.  The class must
                             provide detect(layout, i) -> adjusted_i | None.

install / reinstall
-------------------
`install(view, index)` is called once when the editor becomes active.
`index` is the document cursor position at activation time.

- Call `super().install(view, index)` only if `index` is guaranteed to fall
  exactly on a texel boundary (needed to resolve `self.texel`).  If the
  editor sits *inside* a multi-character texel (e.g. inside a table), skip
  super and set `self._drag_handle = None`, `self.view`, `self.index` manually.

`reinstall()` is called automatically after every model change
(properties_changed).  It re-runs `install` with the same index so the
editor can refresh its cached box/texel references against the new layout.

find_box
--------
Must return `(box, (x0, y0))` in document coordinates, or None.
It is called on every paint and every mouse event — never cache the result,
always read from the current layout so scroll and relayout are handled correctly.

Drag protocol
-------------
on_leftdown  →  hit_test(x, y)  →  start_drag(handle, x, y)
on_motion    →  compute new preview state, call self.view.refresh()
on_leftup    →  commit()  →  clear_drag()

`handle` (= _drag_handle) can be any value, including int 0.
Always check `_drag_handle is not None` — never use plain truthiness.

draw_overlay(gc)
----------------
`gc` is a painter whose origin is the document origin (scroll offset baked
in via dc.SetDeviceOrigin). Call find_box() to obtain the box position
(bx, by) and use document coordinates for all drawing.

position and index
------------------
`self.index` is the document cursor position at activation time.
`self.position` is the box's top-left corner in document coordinates, set
by `install()` and updated by `reinstall()`.

Both values are only valid as long as the model and layout are unchanged.
DocumentView guarantees this by:
- calling `reinstall()` after every `properties_changed` (style/attribute edits)
- calling `remove_editor()` before processing `inserted` or `removed` signals

Do not cache box references or positions across model changes beyond what
`install()` already stores.

Coordinates
-----------
All positions in Editor methods are in *document units* (pt/mm), not screen
pixels.  Convert pixel constants with `px_value / self.view.zoom`.
"""

import wx
from .table_boxes import TableBox
from .textmodel.texeltree import iter_childs

_HIT_RADIUS = 5   # hit detection radius in screen pixels


class Editor:
    view              = None
    index             = None
    position          = None    # top left corner in layout coordinates
    texel             = None    # the primary texel being edited
    hide_cursor        = False   # if True, default draw() skips draw_cursor
    auto_installable   = True    # managed by update_editor() / condition()
    click_installable  = False   # activated by mouse click via detect()

    box_index          = None    # document start position of the box
    texel_index        = None    # document start position of the texel
                                 # (differs from box_index for table fragments)

    _drag_handle      = None
    _drag_start       = None    # position where drag was started (box-local)
    _drag_last        = None    # last drag position (box-local), updated each motion event
    _total_dx         = 0.0
    _total_dy         = 0.0

    _HANDLE_PX    = 7    # handle size in screen pixels
    _HIT_PX       = 6    # hit radius in screen pixels

    def find_box(self):
        """Return (box, (x0, y0)) where (x0, y0) is the box position in document coords."""
        raise NotImplementedError()

    def install(self, view, index):
        """Install or reinstall the editor."""
        self._drag_handle = None
        self.view  = view
        self.index = index
        self.texel = get_texel_at(view.model.get_xtexel(), index)

    def reinstall(self):
        """Reinstall after a model change."""
        self.install(self.view, self.index)

    def draw(self, gc):
        """Draw cursor, selection, overlay, and handles.

        Override in subclasses that need full control (e.g. MatrixEditor).
        The default calls view.draw_cursor / view.draw_selection, then the
        editor-specific overlay and handles.  hide_cursor is honoured for
        backwards compatibility with editors that set it as a class attribute.
        """
        view = self.view
        if not self.hide_cursor:
            view.draw_cursor(gc)
        view.draw_selection(gc)
        self.draw_overlay(gc)
        self.draw_handles(gc)

    def draw_handles(self, gc):
        if self.position is None:
            return
        bx, by = self.position
        zoom = self.view.zoom
        lw = 1.0 / zoom
        hs = self._HANDLE_PX / zoom
        for name, hx, hy in self.get_handles():
            ax, ay = bx + hx - hs / 2, by + hy - hs / 2
            if name == self._drag_handle:
                gc.set_source_rgb(0.0, 0.4, 1.0)
            else:
                gc.set_source_rgb(1.0, 1.0, 1.0)
            gc.rectangle(ax, ay, hs, hs)
            gc.fill()
            gc.set_source_rgb(0.3, 0.3, 0.3)
            gc.set_line_width(lw)
            gc.rectangle(ax, ay, hs, hs)
            gc.stroke()

    def start_drag(self, handle, x, y):
        self._drag_start = x, y
        self._drag_handle = handle
        self.view.refresh()

    def clear_drag(self):
        self._drag_start  = None
        self._drag_handle = None

    def hit_test(self, x, y):
        """Returns either None or a handle name. (x, y) is in box-local coordinates."""
        hit_r = self._HIT_PX / self.view.zoom
        for name, hx, hy in self.get_handles():
            if abs(x - hx) <= hit_r and abs(y - hy) <= hit_r:
                return name
        return None

    def get_cursor(self, handle_id):
        """Return a wx cursor stock id for the given handle, or None for the default cursor."""
        return wx.CURSOR_SIZING

    ### Event handling

    def window_to_box(self, pos):
        """Convert window pixel position to box-local document coordinates."""
        x, y = self.view.window_to_content(pos)
        res = self.find_box()
        if res is None:
            return x, y
        box, (x0, y0) = res
        return x - x0, y - y0

    def on_leftdown(self, event):
        x, y = self.window_to_box(event.Position)
        handle = self.hit_test(x, y)
        if handle is None:
            return False
        self.start_drag(handle, x, y)
        return True

    def on_leftup(self, event):
        if self._drag_handle is not None:
            self.commit()
            self.clear_drag()

    def copy(self):
        self.view.copy()

    def cut(self):
        self.view.cut()

    def paste(self):
        self.view.paste()

    def on_key(self, keycode, event):
        if keycode == wx.WXK_ESCAPE:
            self.view.remove_editor()
            return True
        return False

    ### Editor specific methods which need to be implemented

    def on_motion(self, event):
        """Update the model parameters to reflect the drag."""
        pass

    def draw_overlay(self, gc):
        raise NotImplementedError

    def commit(self):
        raise NotImplementedError

    def get_handles(self):
        """Yield (name, x, y), where (x, y) is in box-local coordinates."""
        raise NotImplementedError
        # a dummy yield to make this an iterator
        yield 'nothing', 0, 0




def get_texel_at(texel, i):
    """Return the leaf texel which starts at absolute position i in
    the texel tree. In the case of a container starting at i, we
    return the container and not the child starting at the same
    position.

    """
    if i == 0 and texel.is_container:
        return texel
    if texel.is_group or texel.is_container:
        for i1, i2, child in iter_childs(texel):
            if i1 <= i < i2:
                return get_texel_at(child, i-i1)
    else:
        if i != 0:
            raise IndexError(i)
    return texel
