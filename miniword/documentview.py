from contextlib import contextmanager

from .wxtextview.wxtextview import WXTextView
from .textmodel.iterators import iter_newlines
from .builder import Factory, Builder
from .cairodevice import CairoDevice
from .annotation import highlight, squiggle
from .builder import trace
from .table_editors import TableEditor, _find_table_at
from .image_editors import ImageSizeEditor, find_image_at, find_image_near
from .texels import BR
from .textmodel.texeltree import transform, iter_childs, grouped


import wx


def _transform_typed(texel, i, cls, fun):
    """Walk the texel tree and apply fun to the ancestor of type cls at pos i."""
    if isinstance(texel, cls):
        return fun(texel)
    if texel.is_group:
        result = []
        for j1, j2, child in iter_childs(texel):
            if j1 <= i < j2:
                result.append(_transform_typed(child, i - j1, cls, fun))
            else:
                result.append(child)
        return grouped(result)
    if texel.is_container:
        result = []
        for j1, j2, child in iter_childs(texel):
            if j1 <= i < j2:
                result.append(_transform_typed(child, i - j1, cls, fun))
            else:
                result.append(child)
        return texel.set_childs(result)
    return texel


class DocumentView(WXTextView):

    highlights = []  # list of (i1, i2) or (i1, i2, color)
    squiggles  = []  # list of (i1, i2) or (i1, i2, color)

    # (detect(layout, i) -> adjusted_i | None,  EditorClass)
    _click_editors = [(find_image_near, ImageSizeEditor)]
    # (detect(layout, i) -> truthy | None,       EditorClass)
    _index_editors = [(_find_table_at, TableEditor)]

    min_zoom = 0.2
    max_zoom = 5.0
    zoom_step = 0.1

    active_editor = None

    def __init__(self, parent, document):
        self.document = document
        super().__init__(parent)
        self.Bind(wx.EVT_MOUSEWHEEL, self.on_mousewheel)
        self.Bind(wx.EVT_LEFT_UP, self.on_leftup)
        self.set_model(document.textmodel)
        self.add_model(document.charstyles)
        self.add_model(document.liststyles)
        self.add_model(document.basestyles)
        self.add_model(document)

        actions = self.actions.copy()
        del actions[(18, True, False)]  # remove Ctrl+R → redo
        actions[25, True, False]           = 'redo'            # Ctrl+Y
        actions[wx.WXK_LEFT,  False, True] = 'dedent_par'      # Alt+Left
        actions[wx.WXK_RIGHT, False, True] = 'indent_par'      # Alt+Right
        actions[wx.WXK_UP,    False, True] = 'move_par_up'     # Alt+Up
        actions[wx.WXK_DOWN,  False, True] = 'move_par_down'   # Alt+Down
        actions[20, True, False]           = 'cycle_list_type'  # Ctrl+T
        actions[116, False, True]          = 'cycle_basestyle'  # Alt+T
        actions[84,  False, True]          = 'cycle_basestyle'  # Shift+Alt+T
        self.actions = actions

    def insert_texel(self, i, texel):
        tmp = self.model.create_textmodel()
        tmp.texel = texel
        return self.insert(i, tmp)

    def indent_par(self, direction, i1, i2):
        model = self.model
        if direction > 0:
            old = model.increase_indent(i1, i2)
        else:
            old = model.decrease_indent(i1, i2)
        self.add_undo((self.restore_indents, i1, i2, old))

    def restore_indents(self, i1, i2, indents):
        old = self.model.set_indents(i1, i2, indents)
        return self.restore_indents, i1, i2, old

    def swap_paragraph(self, direction):
        model = self.model
        row, col = model.index2position(self.index)
        other_row = row + direction
        if other_row < 0 or other_row >= model.nlines() - 1:
            return
        a, b = min(row, other_row), max(row, other_row)
        a_start = model.linestart(a)
        a_end   = model.lineend(a) + 1
        b_start = model.linestart(b)
        b_end   = model.lineend(b) + 1
        para_a = model.copy(a_start, a_end)
        para_b = model.copy(b_start, b_end)
        with self.atomic():
            self.remove(b_start, b_end)
            self.remove(a_start, a_end)
            self.insert(a_start, para_b)
            self.insert(a_start + len(para_b), para_a)
        new_start = model.linestart(other_row)
        self.set_index(min(new_start + col, model.lineend(other_row)))

    def cycle_list_type(self, s1, s2):
        types = ['normal', 'list', 'numbered']
        current = self.model.get_parstyle(self.index).get('paragraph_type', 'normal')
        try:
            idx = types.index(current)
        except ValueError:
            idx = 0
        self.set_parproperties(s1, s2, paragraph_type=types[(idx + 1) % len(types)])

    def cycle_basestyle(self, s1, s2, reverse=False):
        keys = self.document.basestyles.keys()
        if not keys:
            return
        current = self.model.get_parstyle(self.index).get('base', 'normal')
        idx = keys.index(current) if current in keys else 0
        delta = -1 if reverse else 1
        self.set_parproperties(s1, s2, base=keys[(idx + delta) % len(keys)])

    def _set_texel_attributes(self, i, kwds, cls=None):
        old = dict()
        def fun(texel, new=kwds, old=old):
            for key, value in new.items():
                old[key] = getattr(texel, key)
                setter = getattr(texel, 'set_'+key)
                texel = setter(value)
            return texel
        model = self.model
        if cls is not None:
            model.texel = _transform_typed(model.texel, i, cls, fun)
        else:
            model.texel = transform(model.texel, i, i+1, fun, True)
        model.notify_views('properties_changed', i, i+1)
        return self._set_texel_attributes, i, old, cls

    def set_texel_attributes(self, i, cls=None, **kwds):
        """Set attributes on the texel at position i and record undo.

        cls -- if given, find the ancestor of that type at i (needed for
               container texels like Table that transform() would descend into).
        """
        info = self._set_texel_attributes(i, kwds, cls)
        self.add_undo(info)

    
    

    def get_rowwidth(self, i):
        """Return the available content width at position i.

        Traverses the layout to find the innermost Row containing i and
        returns its content width (row.width - row.start[0]).  Works
        recursively, so inside a table cell the column width is returned.
        """
        from .pagegen import Row
        result = None
        def search(box, i0):
            nonlocal result
            if isinstance(box, Row):
                result = box.width - box.start[0]
            for b1, b2, _, _, child in box.iter_boxes(i0, 0, 0):
                if b1 <= i <= b2:
                    search(child, b1)
                    break
        search(self.layout, 0)
        return result

    # ------------------------------------------------------------------
    # Editor management
    # ------------------------------------------------------------------

    def install_editor(self, editor, index):
        self.active_editor = editor
        editor.install(self, index)
        self.notify_views('editor_changed', editor)
        self.refresh()

    def remove_editor(self):
        if self.active_editor:
            self.active_editor = None
            self.notify_views('editor_changed', None)
            self.refresh()

    def properties_changed(self, model, i1, i2):
        super().properties_changed(model, i1, i2)
        editor = self.active_editor
        if editor is not None:
            self.ensure_index()
            editor.reinstall()

    # ------------------------------------------------------------------
    # Mouse events with editor routing
    # ------------------------------------------------------------------
        
    def on_leftdown(self, event):
        if self.active_editor:
            if self.active_editor.on_leftdown(event):
                self.SetFocus()
                return
        x, y = self._window_to_content(event.Position)
        i = self.compute_index(x, y)
        if i is not None and not event.ShiftDown():
            for detect, EditorClass in self._click_editors:
                j = detect(self.layout, i)
                if j is not None:
                    self.set_index(j)
                    self.install_editor(EditorClass(), j)
                    self.active_editor.on_leftdown(event)
                    self.SetFocus()
                    return
        if i is not None:
            self.set_index(i, extend=event.ShiftDown())
        self.SetFocus()

    def on_motion(self, event):
        if self.active_editor and self.active_editor._drag_handle is not None:
            self.active_editor.on_motion(event)
            handle = self.active_editor._drag_handle
            cursor = self.active_editor.get_cursor(handle)
            self.SetCursor(wx.Cursor(cursor))
            return
        # Hover cursor shape near handles
        if not event.LeftIsDown() and self.active_editor:
            x, y = self.active_editor.window_to_box(event.Position)
            hit = self.active_editor.hit_test(x, y)
            cursor = wx.CURSOR_IBEAM if hit is None else self.active_editor.get_cursor(hit)
            self.SetCursor(wx.Cursor(cursor))
        if not event.LeftIsDown():
            return event.Skip()
        x, y = self._window_to_content(event.Position)
        i = self.layout.get_index(x, y)
        if i is not None:
            self.set_index(i, extend=True)

    def on_leftup(self, event):
        if self.active_editor and self.active_editor._drag_handle is not None:
            self.active_editor.on_leftup(event)
            self.SetCursor(wx.Cursor(wx.CURSOR_IBEAM))

    def on_mousewheel(self, event):
        if not event.ControlDown():
            return event.Skip()  # scroll
        old_zoom = self.zoom
        factor = 1.1 if event.GetWheelRotation() > 0 else 1 / 1.1
        new_zoom = max(0.2, min(5.0, old_zoom * factor))

        cw, ch = self.GetClientSize()
        rx, ry = self._scrollrate
        sx, sy = self.GetViewStart()
        scroll_x = sx * rx
        scroll_y = sy * ry

        # Content-center in old zoom
        cx_content = (scroll_x + cw / 2) / old_zoom
        cy_content = (scroll_y + ch / 2) / old_zoom

        # new scroll so that content-center does not change
        new_scroll_x = cx_content * new_zoom - cw / 2
        new_scroll_y = cy_content * new_zoom - ch / 2

        self.set_zoom(new_zoom)

        # VirtualSize must be updateted before Scroll()
        layout = self.layout
        self.SetVirtualSize((int(layout.width * new_zoom), int(layout.height * new_zoom)))
        self.SetScrollRate(rx, ry)

        self.Scroll(max(0, int(new_scroll_x / rx)),
                    max(0, int(new_scroll_y / ry)))        

    def _viewport_start(self):
        """Return the text index of the first character on the currently visible page."""
        rx, ry = self._scrollrate
        _, sy = self.GetViewStart()
        scroll_y = sy * ry / self.zoom
        for p1, p2, px, py, page in self.layout.iter_boxes(0, 0, 0):
            if py + page.height + page.depth >= scroll_y:
                return p1
        return 0

    def _viewport_bottom_y(self):
        """Return the bottom coordinate of the currently visible viewport."""
        rx, ry = self._scrollrate
        _, sy  = self.GetViewStart()
        ch     = self.GetClientSize()[1]
        return (sy * ry + ch) / self.zoom

    def ensure_viewport(self):
        """Safety net: build until viewport is covered (no dialog)."""
        layout = self.layout
        y = self._viewport_bottom_y()
        if layout.height + layout.depth < y and not layout.is_finished:
            import time
            t0 = time.time()
            self.builder.buildto_y(y)
            
    def ensure_index(self):
        """Safety net: build until index covered (no dialog)."""
        layout = self.layout
        index = self.index
        if len(layout) < index and not layout.is_finished:
            import time
            t0 = time.time()
            self.builder.buildto_index(index)
        
    def on_paint(self, event):
        self.ensure_viewport()
        self._update_scroll()
        self.keep_cursor_on_screen()

        pdc = wx.PaintDC(self)
        pdc.SetAxisOrientation(True, False)
        device = self.builder.get_device()
        if device.buffering:
            dc = wx.BufferedDC(pdc)
            if not dc.IsOk():
                return
        else:
            dc = pdc
        dc.SetBackgroundMode(wx.SOLID)
        dc.SetBackground(wx.Brush(self.GetBackgroundColour()))
        dc.Clear()
        region = self.GetUpdateRegion()
        rx, ry, rw, rh = region.Box
        dc.SetClippingRegion(rx - 1, ry - 1, rw + 2, rh + 2)
        painter = device.create_painter(dc)

        zoom = self.zoom
        layout = self.layout
        cw, ch = self.GetClientSize()
        vw = int(layout.width * zoom)
        vh = int(layout.height * zoom)

        px, py = self.CalcScrolledPosition((0, 0))
        if vw < cw:
            px = (cw - vw) // 2
        if vh < ch:
            py = (ch - vh) // 2
        x = px / zoom
        y = py / zoom

        layout.draw_background(x, y, painter)          # 1. white page fills

        for entry in self.highlights:
            i1, i2 = entry[:2]
            c = entry[2] if len(entry) > 2 else 'yellow'
            highlight(painter, layout, i1, i2, x, y, c)  # 2. colored backgrounds

        layout.draw(x, y, painter)                      # 3. text on top

        for entry in self.squiggles:
            i1, i2 = entry[:2]
            c = entry[2] if len(entry) > 2 else 'red'
            squiggle(painter, layout, i1, i2, x, y, c)   # 4. lines on top

        hide_cursor = self.active_editor and self.active_editor.hide_cursor
        if wx.Window.FindFocus() is self and self.index <= len(layout) and not hide_cursor:
            layout.draw_cursor(self.index, x, y, painter,
                               self.model.defaultstyle)
        for j1, j2 in self.get_selected():
            if j1 <= len(layout):
                layout.draw_selection(j1, min(j2, len(layout)), x, y, painter)
        editor = self.active_editor
        if editor:
            box, (bx, by) = editor.find_box()
            editor.draw_overlay(x+bx, y+by, painter)
            editor.draw_handles(x+bx, y+by, painter)
        dc = None
        painter = None

    # ------------------------------------------------------------------
    # Copy / paste
    # ------------------------------------------------------------------

    def copy(self):
        if not self.has_selection():
            return
        s1, s2 = sorted(self.selection)
        part = self._dispatch_copy(self.layout, s1, s2, 0)
        self.to_clipboard(part)

    def _dispatch_copy(self, box, i1, i2, offset):
        """Traverse layout to find a box with get_copy; fall back to model.copy."""
        if hasattr(box, 'get_copy'):
            return box.get_copy(i1, i2, self.model, offset)
        for j1, j2, x, y, child in box.iter_boxes(0, 0, 0):
            if j1 <= i1 and i2 <= j2:
                return self._dispatch_copy(child, i1 - j1, i2 - j1, offset + j1)
        return self.model.copy(offset + i1, offset + i2)

    # ------------------------------------------------------------------
    # Atomic style operations
    # ------------------------------------------------------------------

    _inhibit_depth = 0
    _pending_range = None  # (i1, i2, delta) accumulated while inhibited

    def _accumulate(self, i1, i2, delta=0):
        r = (i1, i2, delta)
        self._pending_range = accumulate(self._pending_range, r)

    @trace
    def rebuild_range(self, i1, i2, delta):
        """Marks the range from i1 to i2 as dirty. In an atomic
        context, updates are accumulated and deferred. Otherwise, the
        update is triggered immediately. The building will happen in
        the background. To enforce visibility the caller should use
        ensure_viewport oder builder.buildto_*. No progress dialog is
        shown.
        """
        if self._inhibit_depth > 0:
            self._accumulate(i1, i2, delta)
        else:
            self.builder.rebuild_range(i1, i2, delta)
            # Note 1: ensure_viewport() is intentionally NOT called
            # here.  on_paint() calls it before every draw, so the
            # visible area is always covered before it is needed.
            # Calling it here would build 1–2 pages synchronously
            # inside the EVT_CHAR handler (via the model.insert →
            # inserted → rebuild_range call chain), adding avoidable
            # latency to every keystroke.

            # Note 2: Do not use wx.Yield while handling a
            # notify-message. Otherwise, additional keyboard events
            # could "interleave" with the current handler, causing
            # unpredictable behavior and race conditions. We use
            # wx.CallAfter to ensure that any necessary yields occur
            # asynchronously after the current event cycle.

            wx.CallAfter(self.builder.build_background)
            self.refresh()

    @trace
    def rebuild(self):
        """Start a rebuild of the complete document and wait until
        viewport is completed."""
        self.builder.rebuild()
        self.ensure_viewport()
        self.builder.build_background()
        self.refresh()

    @contextmanager
    def atomic(self):
        """Group multiple model/stylesheet changes into one layout rebuild."""
        self.begin_undo_group()
        self._inhibit_depth += 1
        try:
            yield
        finally:
            self.end_undo_group()
            self._inhibit_depth -= 1
        if self._inhibit_depth == 0 and self._pending_range is not None:
            i1, i2, delta = self._pending_range
            self._pending_range = None
            self._rebuild_with_progress(i1, i2, delta)

    def _wait_with_progress(self):
        """Show progress dialog until viewport is covered."""
        layout = self.builder.layout
        y = self._viewport_bottom_y()
        index = self.index
        total = max(1, len(self.model))
        if layout.height + layout.depth >= y and index < len(layout):
            self.refresh()
            return
        self.Freeze()
        dlg = wx.ProgressDialog(
            "Building layout", "Please wait...",
            maximum=100, parent=self,
            style=wx.PD_APP_MODAL)
        def tick():
            dlg.Update(min(99, int(100 * len(layout) / total)))
            wx.SafeYield()
        try:
            self.builder.buildto_y(y, tick)
            self.builder.buildto_index(index, tick)
        finally:
            dlg.Destroy()
            self.Thaw()
        self.refresh()

    @trace
    def _rebuild_with_progress(self, i1, i2, delta):
        """Rebuild range and show progress dialog if viewport not yet covered."""
        self.builder.rebuild_range(i1, i2, delta)
        self._wait_with_progress()
        if not self.builder.layout.is_finished:
            self.builder.build_background()

    def _undo_stylesheet(self, name, restore_to, after_redo):
        """Undo/redo a stylesheet change.

        restore_to: style dict to restore, or None to delete the style.
        after_redo: style dict for the redo direction (or None to delete).
        Returns the complementary redo/undo entry.
        """
        if restore_to is None:
            self.document.basestyles.delete(name)
        else:
            self.document.basestyles.set(name, restore_to)
        return (self._undo_stylesheet, name, after_redo, restore_to)

    # ------------------------------------------------------------------
    # Stylesheet observer
    # ------------------------------------------------------------------

    def style_changed(self, stylesheet, key):
        j1 = j2 = None
        for i1, i2, nl in iter_newlines(self.model.get_xtexel(), 0):
            if nl.parstyle.get('base', 'normal') == key:
                if j1 is None:
                    j1 = i1
                j2 = i2
        if j1 is None:
            return
        self.clear_caches()
        if self._inhibit_depth > 0:
            self._accumulate(j1, j2)
        else:
            self._rebuild_with_progress(j1, j2, 0)

    _LAYOUT_SETTINGS = {
        'paper', 'paper_width', 'paper_height',
        'margin_top', 'margin_bottom', 'margin_left', 'margin_right',
    }

    @trace
    def setting_changed(self, doc, name, old):
        self.builder.settings = self.document.settings
        if name in self._LAYOUT_SETTINGS:
            self._rebuild_with_progress(0, len(self.model)+1, 0)
        else:
            self.refresh()

    @trace
    def style_removed(self, stylesheet, key):
        self.clear_caches()
        self.rebuild()

    def create_builder(self):
        factory = Factory(self.document.basestyles, device=CairoDevice())
        factory.blobs = self.document.blobs
        builder = Builder(self.model, factory)
        builder.settings = self.document.settings
        return builder

    def set_index(self, index, extend=False, update=True):
        self.builder.device.reset_blink()
        self.builder.buildto_index(index + 1)
        for detect, EditorClass in self._index_editors:
            if detect(self.layout, index):
                self.install_editor(EditorClass(), index)
                break
        else:
            if self.active_editor is not None and self.active_editor.index != index:
                self.remove_editor()
        WXTextView.set_index(self, index, extend, update)

    def export_pdf(self, path):
        import cairo
        self.builder.buildto_finish()
        pages = self.layout.childs
        if not pages:
            return
        device = self.builder.get_device()
        w, h = pages[0].width, pages[0].height
        surface = cairo.PDFSurface(path, w, h)
        ctx = cairo.Context(surface)
        for page in pages:
            page.draw_background(0, 0, ctx)
            page.draw_for_print(0, 0, ctx)
            ctx.show_page()
        surface.finish()

    def iter_rows(self):
        from .tables import TableBox, _TableNavRow
        for p1, p2, px, py, page in self.layout.iter_boxes(0, 0, 0):
            for r1, r2, rx, ry, row in page.iter_boxes(p1, px, py):
                # Descend into TableBox: yield one nav entry per table row
                tb = None
                for ci1, ci2, cx, cy, child in row.iter_boxes(r1, rx, ry):
                    if isinstance(child, TableBox):
                        tb, tbx, tby = child, cx, cy
                        break
                if tb is not None:
                    cy = tby
                    for tr in range(tb.n_rows):
                        yield r1, r2, tbx, cy, _TableNavRow(tb, tr)
                        cy += tb.row_heights[tr]
                else:
                    yield r1, r2, rx, ry, row

    def move_down(self, shift):
        index  = self.index
        layout = self.layout
        x, y   = layout.get_rect(index, 0, 0).items()[:2]
        for r1, r2, rx, ry, row in self.iter_rows():
            if ry > y:
                i = row.get_index(x - rx, row.height)
                return self.set_index(r1 + i, shift)

    def move_up(self, shift):
        index  = self.index
        layout = self.layout
        x, y   = layout.get_rect(index, 0, 0).items()[:2]
        prev   = None
        for r1, r2, rx, ry, row in self.iter_rows():
            if ry + row.height + row.depth > y:
                if not prev:
                    return
                r1, r2, rx, ry, row = prev
                i = row.get_index(x - rx, row.height)
                return self.set_index(r1 + i, shift)
            prev = r1, r2, rx, ry, row

    def move_page_down(self, shift):
        index    = self.index
        layout   = self.layout
        x, y     = layout.get_rect(index, 0, 0).items()[:2]
        _, ch    = self.GetClientSize()
        target_y = y + ch / self.zoom
        last     = None
        for r1, r2, rx, ry, row in self.iter_rows():
            if ry >= target_y:
                i = row.get_index(x - rx, row.height)
                return self.set_index(r1 + i, shift)
            last = r1, r2, rx, ry, row
        if last:
            r1, r2, rx, ry, row = last
            self.set_index(r2 - 1, shift)  # end of last row

    def move_page_up(self, shift):
        index    = self.index
        layout   = self.layout
        x, y     = layout.get_rect(index, 0, 0).items()[:2]
        _, ch    = self.GetClientSize()
        target_y = y - ch / self.zoom
        prev     = None
        for r1, r2, rx, ry, row in self.iter_rows():
            if ry + row.height + row.depth > target_y:
                if prev is None:
                    return self.set_index(0, shift)
                r1, r2, rx, ry, row = prev
                i = row.get_index(x - rx, row.height)
                return self.set_index(r1 + i, shift)
            prev = r1, r2, rx, ry, row

    def on_leftdclick(self, event):
        x, y = self._window_to_content(event.Position)
        i = self.layout.get_index(x, y) or 0
        img_res = find_image_at(self.layout, i)
        if img_res is not None:
            self.notify_views('image_dblclick', i)
            self.SetFocus()
            return
        super().on_leftdclick(event)

    def on_char(self, event):
        if self.active_editor:
            if self.active_editor.on_key(event.GetKeyCode(), event):
                return
        super().on_char(event)

    def handle_action(self, action, shift=False):
        i = self.index
        style = self.model.get_style(i)
        model = self.model
        if self.has_selection():
            s1, s2 = sorted(self.selection)
        else:
            s1 = s2 = i
        row2, col2 = model.index2position(s2)
        ps1 = model.linestart(model.index2position(s1)[0])
        ps2 = s2 if col2 == 0 else model.lineend(row2) + 1
        if action == 'insert_newline' and shift:
            self.insert_texel(i, BR(style))
        elif action == 'undo' and shift:
            self.redo()
        elif action == 'move_down':
            self.move_down(shift)
        elif action == 'move_up':
            self.move_up(shift)
        elif action == 'move_page_down':
            self.move_page_down(shift)
        elif action == 'move_page_up':
            self.move_page_up(shift)
        elif action == 'move_document_end':
            self.set_index(len(self.layout) - 1, shift)
        elif action == 'indent_par':
            self.indent_par(1, ps1, ps2)
        elif action == 'dedent_par':
            self.indent_par(-1, ps1, ps2)
        elif action == 'move_par_up':
            self.swap_paragraph(-1)
        elif action == 'move_par_down':
            self.swap_paragraph(1)
        elif action == 'cycle_list_type':
            self.cycle_list_type(ps1, ps2)
        elif action == 'cycle_basestyle':
            self.cycle_basestyle(ps1, ps2, reverse=shift)
        else:
            return WXTextView.handle_action(self, action, shift)



def accumulate(r1, r2):
    """Combine two consecutive update ranges into one.

    r1 = (i1, i2, delta) in original model coordinates.
    r2 = (b1, b2, d2)    in model coordinates after r1 was applied.

    Returns a merged (i1, i2, delta) in original model coordinates that
    covers both changes and carries the combined delta.
    """
    if r1 is None:
        return r2
    elif r2 is None:
        return r1
    
    pi1, pi2, pd = r1
    b1,  b2,  d2 = r2

    pi2_m0  = pi2 + max(0, -pd)   # M0 end: includes deleted chars if pd<0
    pi1_m1  = pi1 + max(0,  pd)   # first M1 position after the change

    if b1 > pi1_m1:                # r2 entirely after r1
        b1o = b1 - pd
        b2o = b2 - pd
    elif b2 < pi1:                 # r2 entirely before r1
        b1o = b1
        b2o = b2
    else:                          # overlap — conservative
        b1o = min(b1, pi1)
        b2o = max(b2 - pd, pi2_m0)

    return (min(pi1, b1o), max(pi2_m0, b2o), pd + d2)


def test_accumulate():
    "accumulate: combining two update ranges"
    # --- delta=0: property changes ---

    # r2 after r1, no overlap
    assert accumulate((2, 5, 0), (8, 12, 0)) == (2, 12, 0)

    # r2 before r1, no overlap
    assert accumulate((8, 12, 0), (2, 5, 0)) == (2, 12, 0)

    # r2 overlaps r1
    assert accumulate((2, 8, 0), (5, 12, 0)) == (2, 12, 0)

    # --- insertion (pd > 0) ---

    # r2 after r1: positions shift by pd (user's example)
    # insert 1 at 5, then insert 1 at 10-in-M1 (= 9 in M0)
    assert accumulate((5, 5, 1), (10, 10, 1)) == (5, 9, 2)

    # r2 before r1: no shift needed
    # insert 1 at 10, then insert 1 at 3-in-M1 (before change)
    assert accumulate((10, 10, 1), (3, 3, 1)) == (3, 10, 2)

    # r2 within inserted region (overlap)
    # insert 3 at 5; property change at pos 6-in-M1 (inside insertion)
    assert accumulate((5, 5, 3), (6, 6, 0)) == (5, 5, 3)

    # --- deletion (pd < 0) ---

    # r2 after deletion: shift right by |pd|, pi2_m0 covers deleted region
    # delete 3 at 5 (removes M0 positions 5-7); property change at 7-in-M1 (=10 in M0)
    assert accumulate((5, 5, -3), (7, 7, 0)) == (5, 10, -3)

    # r2 before deletion: pi2_m0 must include the deleted region
    # delete 3 at 5; property change at 2-3 in M1 (before deletion)
    assert accumulate((5, 5, -3), (2, 3, 0)) == (2, 8, -3)

    # insertion then deletion
    # insert 2 at 3; delete 4 at 8-in-M1 (= 6 in M0)
    assert accumulate((3, 3, 2), (8, 8, -4)) == (3, 6, -2)

    # --- straddle: b1 before, b2 after — only b2 needs shifting ---

    # insert 2 at 5; property change [3, 10] in M1 (b1 before, b2 after insert)
    # b1=3 → no shift; b2=10 → shift: 10-2=8
    assert accumulate((5, 5, 2), (3, 10, 0)) == (3, 8, 2)

    # delete 3 at 5; property change [3, 7] in M1 (b1 before, b2 after delete)
    # b1=3 → no shift; b2=7 → shift: 7+3=10; pi2_m0=8 → max(10,8)=10
    assert accumulate((5, 5, -3), (3, 7, 0)) == (3, 10, -3)


def test_00():
    "modifying a basestyle updates the layout"
    import io
    from contextlib import redirect_stdout
    from einstein import get_einstein_model
    from .document import Document
    from .styles import style_default

    model = get_einstein_model()
    doc   = Document()
    doc.textmodel = model
    doc.basestyles.set('normal', dict(style_default))

    with redirect_stdout(io.StringIO()):
        app   = wx.App(redirect=False)
        frame = wx.Frame(None)
        view  = DocumentView(frame, doc)
        view.builder.nbefore = 0
        view.builder.nrest = 0

        new_normal = doc.basestyles.get('normal').copy()
        new_normal['font_size'] = 8
        doc.basestyles.set('normal', new_normal)
        view.builder.buildto_finish()
        stats = view.builder.get_updatestats()

    # are the styles updated?
    style = view.builder.factory.mk_style({})
    assert style['font_size'] == 8

    # is the layout updated?
    assert stats == (0, 1, 0)

    assert view.layout is view.builder.layout

    row = view.layout.childs[0].rows[0][-1]
    tb = row.childs[0]
    assert tb.style['font_size'] == 8

    
def test_01():
    "progress dialog is shown when viewport is not yet covered"
    import io
    from contextlib import redirect_stdout
    from unittest.mock import patch
    #from einstein import get_einstein_model as get_model
    from moby import get_moby_model as get_model
    from .document import Document
    from .styles import style_default

    with redirect_stdout(io.StringIO()):
        app  = wx.App(redirect=False)
        frame = wx.Frame(None)
        doc  = Document()
        doc.textmodel = get_model()
        doc.basestyles.set('normal', dict(style_default))
        view = DocumentView(frame, doc)
        view.builder.buildto_finish()

    # Pretend the viewport extends far below the built layout so the
    # dialog condition is always triggered.
    view._viewport_bottom_y = lambda: float('inf')

    dialogs = []
    ticks = []
    class TrackingDialog(wx.ProgressDialog):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            dialogs.append(self)
        def Update(self, x):
            super().Update(x)
            ticks.append(x)
            return True, False

    with patch('miniword.documentview.wx.ProgressDialog', TrackingDialog):
        with view.atomic():
            view.properties_changed(view.model, 0, 100)

    assert len(ticks)
    assert len(dialogs) > 0, "progress dialog should have been shown"

    view.index = len(view.model)
    del ticks[:]
    del dialogs[:]
    with patch('miniword.documentview.wx.ProgressDialog', TrackingDialog):
        with view.atomic():
            view.index = len(view.model)
            view.properties_changed(view.model, 0, len(view.model))
    
    print("ticks=", ticks)


def demo_00():
    from einstein import get_einstein_model
    from .styles import testsheet
    model = get_einstein_model()

    model.set_properties(0, 15, color='red')
    model.set_parproperties(0, 1000, paragraph_type='list')
    app   = wx.App(redirect=True)
    frame = wx.Frame(None)
    view  = DocumentView(frame, -1)
    view.model = model
    view.builder.device.zoom = 2
    testsheet.add_view(view)
    frame.Show()

    if 1:
        from .inspector import Inspector
        inspector = Inspector(view, None)
        inspector.Show()
    if 1:
        from .wxtextview import testing
        l = locals()
        l.update(globals())
        testing.pyshell(l)
    app.MainLoop()
