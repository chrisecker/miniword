import wx
from wx.lib.newevent import NewEvent

from ..textmodel.viewbase import ViewBase
from ..textmodel.texeltree import length
from ..ui.threestate import ColourButton
from ..ui.icons import icon
from ..ui.design import TEXT_MUTED, muted_button, make_panel, add_section
from ..ui.documentview import get_path
from .tables import Table, empty_table

TableCreatedEvent, EVT_TABLE_CREATED = NewEvent()

COLS = 10
ROWS = 8

CELL_SIZE = 16
CELL_GAP  = 3
PADDING   = 8

COL_BG      = wx.Colour(245, 245, 245)
COL_NORMAL  = wx.Colour(210, 210, 210)
COL_BORDER  = wx.Colour(170, 170, 170)
COL_SEL     = wx.Colour(100, 160, 220)
COL_SEL_BDR = wx.Colour(60,  110, 180)
COL_TEXT    = wx.Colour(38,  38,  36)
COL_MUTED   = wx.Colour(160, 160, 156)
COL_HOVER   = wx.Colour(220, 235, 250)


class _TableGrid(wx.Panel):
    """Cell grid — fixed COLS×ROWS, cell size derived from target width."""

    _LABEL_H = 24   # room for combined title line

    def __init__(self, parent, target_w):
        # back-calculate cell size so grid fills target_w exactly
        cell = (target_w - 2 * PADDING - (COLS - 1) * CELL_GAP) // COLS
        self._cell = max(cell, 8)
        w = 2 * PADDING + COLS * self._cell + (COLS - 1) * CELL_GAP
        h = self._LABEL_H + ROWS * self._cell + (ROWS - 1) * CELL_GAP + PADDING
        super().__init__(parent, size=(w, h))
        self.SetMinSize((w, h))
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)   # suppress default erase → no flicker
        self._col = 0
        self._row = 0

        self.Bind(wx.EVT_PAINT,        self._on_paint)
        self.Bind(wx.EVT_MOTION,       self._on_motion)
        self.Bind(wx.EVT_LEFT_UP,      self._on_click)
        self.Bind(wx.EVT_LEAVE_WINDOW, self._on_leave)

    def _cell_origin(self, col, row):
        x = PADDING + col * (self._cell + CELL_GAP)
        y = self._LABEL_H + row * (self._cell + CELL_GAP)
        return x, y

    def _hit(self, px, py):
        for row in range(ROWS):
            for col in range(COLS):
                x, y = self._cell_origin(col, row)
                if x <= px < x + self._cell and y <= py < y + self._cell:
                    return col + 1, row + 1
        return 0, 0

    def _on_paint(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(COL_BG))
        dc.Clear()

        # Combined title + dimension
        if self._col:
            label = f"Insert table: {self._col} \u00d7 {self._row}"
            dc.SetTextForeground(COL_TEXT)
        else:
            label = "Insert table"
            dc.SetTextForeground(COL_MUTED)
        dc.DrawText(label, PADDING, 4)

        # Cells
        for row in range(ROWS):
            for col in range(COLS):
                x, y = self._cell_origin(col, row)
                if col < self._col and row < self._row:
                    dc.SetBrush(wx.Brush(COL_SEL))
                    dc.SetPen(wx.Pen(COL_SEL_BDR))
                else:
                    dc.SetBrush(wx.Brush(COL_NORMAL))
                    dc.SetPen(wx.Pen(COL_BORDER))
                dc.DrawRectangle(x, y, self._cell, self._cell)

    def _on_motion(self, event):
        col, row = self._hit(event.GetX(), event.GetY())
        if col == 0:
            return  # cursor in gap between cells — keep last selection
        if col != self._col or row != self._row:
            self._col = col
            self._row = row
            self.Refresh()

    def _on_click(self, event):
        if self._col > 0:
            wx.PostEvent(self, TableCreatedEvent(cols=self._col, rows=self._row))

    def _on_leave(self, event):
        if self._col:
            self._col = 0
            self._row = 0
            self.Refresh()


class _CustomItem(wx.Panel):
    """Clickable 'Insert custom table'."""

    def __init__(self, parent):
        super().__init__(parent)
        self.SetBackgroundColour(COL_BG)
        lbl = wx.StaticText(self, label="Insert custom table")
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(lbl, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 6)
        self.SetSizer(sizer)

        self.SetCursor(wx.Cursor(wx.CURSOR_HAND))
        for w in (self, lbl):
            w.Bind(wx.EVT_ENTER_WINDOW, self._on_enter)
            w.Bind(wx.EVT_LEAVE_WINDOW, self._on_leave)
            w.Bind(wx.EVT_LEFT_UP,      self._on_click)

    def _on_enter(self, event):
        self.SetBackgroundColour(COL_HOVER)
        self.Refresh()

    def _on_leave(self, event):
        self.SetBackgroundColour(COL_BG)
        self.Refresh()

    def _on_click(self, event):
        # cols=0, rows=0 signals "custom"
        wx.PostEvent(self, TableCreatedEvent(cols=0, rows=0))


class _TablePopup(wx.PopupTransientWindow):
    def __init__(self, parent, width):
        super().__init__(parent, wx.BORDER_SIMPLE)
        self.SetBackgroundColour(COL_BG)

        # Measure label width so the grid matches it exactly
        self.custom = _CustomItem(self)
        if width:
            target_w = width
        else:
            target_w    = self.custom.GetBestSize().width

        self.grid   = _TableGrid(self, target_w)
        separator   = wx.StaticLine(self)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self.grid,   0, wx.EXPAND)
        sizer.Add(separator,   0, wx.EXPAND)
        sizer.Add(self.custom, 0, wx.EXPAND)
        self.SetSizer(sizer)
        self.Fit()

        self.Bind(wx.EVT_CHAR_HOOK, self._on_key)

    def _on_key(self, event):
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.Dismiss()
        else:
            event.Skip()


class CustomTableDialog(wx.Dialog):
    """Dialog for specifying arbitrary table dimensions."""

    def __init__(self, parent):
        super().__init__(parent, title="Table size",
                         style=wx.DEFAULT_DIALOG_STYLE)
        self.SetBackgroundColour(COL_BG)

        lbl_cols = wx.StaticText(self, label="Columns")
        self.spin_cols = wx.SpinCtrl(self, value="2", min=1, max=50)

        lbl_rows = wx.StaticText(self, label="Rows")
        self.spin_rows = wx.SpinCtrl(self, value="2", min=1, max=50)

        btn_ok     = wx.Button(self, wx.ID_OK,     label="OK")
        btn_cancel = wx.Button(self, wx.ID_CANCEL, label="Cancel")
        btn_ok.SetDefault()

        form = wx.FlexGridSizer(rows=2, cols=2, hgap=8, vgap=8)
        form.AddGrowableCol(1)
        form.Add(lbl_cols,       0, wx.ALIGN_CENTER_VERTICAL)
        form.Add(self.spin_cols, 0, wx.EXPAND)
        form.Add(lbl_rows,       0, wx.ALIGN_CENTER_VERTICAL)
        form.Add(self.spin_rows, 0, wx.EXPAND)

        btn_row = wx.StdDialogButtonSizer()
        btn_row.AddButton(btn_ok)
        btn_row.AddButton(btn_cancel)
        btn_row.Realize()

        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(form,    0, wx.EXPAND | wx.ALL, 16)
        outer.Add(btn_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 16)
        self.SetSizerAndFit(outer)

    @property
    def cols(self):
        return self.spin_cols.GetValue()

    @property
    def rows(self):
        return self.spin_rows.GetValue()


class TableCreatorButton(wx.Button):
    """Button that opens a table-size picker on LEFT_DOWN.

    Fires EVT_TABLE_CREATED with .cols/.rows on the button.
    cols=0, rows=0 means "custom table".
    """

    def __init__(self, parent, label="Table ▾"):
        super().__init__(parent, label=label)
        self.Bind(wx.EVT_LEFT_DOWN, self.on_press)

    def on_press(self, _evt):
        popup = _TablePopup(self, self.Size[0])
        popup.grid.Bind(EVT_TABLE_CREATED,   lambda e: self.on_selected(popup, e))
        popup.custom.Bind(EVT_TABLE_CREATED, lambda e: self.on_selected(popup, e))
        popup.Position(self.GetScreenPosition(), (0, self.GetSize().height))
        popup.Popup()

    def on_selected(self, popup, event):
        popup.Dismiss()
        if event.cols == 0:
            self.show_custom_dialog()
        else:
            wx.PostEvent(self, TableCreatedEvent(cols=event.cols, rows=event.rows))

    def show_custom_dialog(self):
        with CustomTableDialog(self) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                wx.PostEvent(self, TableCreatedEvent(cols=dlg.cols, rows=dlg.rows))


# ---------------------------------------------------------------------------
# Border preset definitions
# ---------------------------------------------------------------------------

_BORDER_PRESETS = [
    ('border_none',    'none'),
    ('border_all',     'all'),
    ('border_outer',   'outer'),
    ('border_inner',   'inner'),
    ('border_inner_h', 'inner_h'),
    ('border_inner_v', 'inner_v'),
    ('border_left',    'left'),
    ('border_right',   'right'),
    ('border_top',     'top'),
    ('border_bottom',  'bottom'),
]


class TablePanel(wx.Panel, ViewBase):
    """Inspector panel for inserting and editing tables."""

    def __init__(self, parent, view):
        wx.Panel.__init__(self, parent)
        ViewBase.__init__(self)
        self._view = view
        self._table_index = None
        self._table_box = None
        self.add_model(view)

        sizer = make_panel(self, "TABLES")

        # --- Section: Insert ---
        add_section("Insert", self, sizer)
        btn = TableCreatorButton(self)
        btn.Bind(EVT_TABLE_CREATED, self._on_insert)
        sizer.Add(btn, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5)

        # --- Section: Borders ---
        add_section("Borders", self, sizer)
        self._line_style = wx.Choice(self, choices=['Thin line', 'Thick line', 'Double line'])
        self._line_style.SetSelection(0)
        sizer.Add(self._line_style, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5)

        grid_sizer = wx.GridSizer(rows=2, cols=5, hgap=2, vgap=2)
        self._border_btns = []
        for icon_name, key in _BORDER_PRESETS:
            btn = wx.BitmapButton(self, bitmap=icon(icon_name + '.svg', (24, 24)),
                                  size=(32, 32))
            btn.preset_key = key
            btn.Bind(wx.EVT_BUTTON, self._on_border_preset)
            grid_sizer.Add(btn, 0, wx.EXPAND)
            self._border_btns.append(btn)
        sizer.Add(grid_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5)

        # --- Section: Rows & Columns ---
        add_section("Rows & Columns", self, sizer)
        row_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self._btn_row = wx.Button(self, label="Row ▾")
        self._btn_col = wx.Button(self, label="Column ▾")
        self._btn_row.Bind(wx.EVT_LEFT_DOWN, self.on_row_menu)
        self._btn_col.Bind(wx.EVT_LEFT_DOWN, self.on_col_menu)
        row_sizer.Add(self._btn_row, 1, wx.RIGHT, 4)
        row_sizer.Add(self._btn_col, 1)
        sizer.Add(row_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5)

        # --- Section: Cell ---
        add_section("Cell", self, sizer)
        cell_sizer = wx.FlexGridSizer(rows=3, cols=2, hgap=4, vgap=4)
        cell_sizer.AddGrowableCol(1)

        cell_sizer.Add(wx.StaticText(self, label="Background"), 0, wx.ALIGN_CENTER_VERTICAL)
        self._bgcolor_btn = ColourButton(self)
        self._bgcolor_btn.callback = self._on_bgcolor
        cell_sizer.Add(self._bgcolor_btn, 0, wx.EXPAND)

        cell_sizer.Add(wx.StaticText(self, label="V-Align"), 0, wx.ALIGN_CENTER_VERTICAL)
        self._valign = wx.Choice(self, choices=['top', 'middle', 'bottom'])
        self._valign.SetSelection(0)
        self._valign.Bind(wx.EVT_CHOICE, self._on_valign)
        cell_sizer.Add(self._valign, 0, wx.EXPAND)

        sizer.Add(cell_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5)

        self._table_controls = (
            [self._btn_row, self._btn_col, self._line_style,
             self._bgcolor_btn, self._valign]
            + self._border_btns
        )
        self._set_table_controls(False)
        self.Bind(wx.EVT_SHOW, self.on_show)

    def on_show(self, event):
        event.Skip()
        if event.IsShown():
            self._update_cell_inspector()

    def _on_insert(self, event):
        if event.cols == 0:
            return  # custom dialog was cancelled
        table = empty_table(event.rows, event.cols)
        self._view.insert_texel(self._view.index, table)

    def editor_changed(self, view, editor):
        pass

    def index_changed(self, model):
        self._update_cell_inspector()

    def selection_changed(self, model):
        self._update_cell_inspector()

    def properties_changed(self, model, *args, **kwargs):
        self._update_cell_inspector()

    def _set_table_controls(self, enabled):
        for w in self._table_controls:
            w.Enable(enabled)

    def _update_cell_inspector(self):
        table, ci1 = self._find_table_texel()
        self._set_table_controls(table is not None)
        if table is None:
            return
        r1, c1, r2, c2 = self._selected_cell_range(table, ci1)
        cells = table.get_cells()

        def unique(attr):
            vals = {cells[r][c].get_attr(attr)
                    for r in range(r1, r2 + 1)
                    for c in range(c1, c2 + 1)}
            return vals.pop() if len(vals) == 1 else None

        bg = unique('cell_bgcolor')
        self._bgcolor_btn.set_colour(wx.Colour(bg) if bg is not None else None)

        valign_choices = ['top', 'middle', 'bottom']
        va = unique('valign')
        self._valign.Unbind(wx.EVT_CHOICE)
        self._valign.SetSelection(valign_choices.index(va) if va in valign_choices else 0)
        self._valign.Bind(wx.EVT_CHOICE, self._on_valign)

    # --- helpers to find current table ---

    def _find_table_texel(self):
        """Return (table_texel, offset) for the innermost Table at the cursor,
        or (None, None) if the cursor is not inside a table."""
        index = self._view.index
        result = None
        for abs_i1, abs_i2, node in get_path(self._view.model.texel, index):
            if isinstance(node, Table):
                result = node, abs_i1
        return result or (None, None)

    def _selected_cell_range(self, table, ci1):
        """Return (r1, c1, r2, c2) for current selection, clamped to table."""
        view = self._view
        if view.has_selection():
            s1, s2 = sorted(view.selection)
        else:
            s1 = s2 = view.index
        n = length(table)
        i1 = max(1, min(s1 - ci1, n - 1))
        i2 = max(1, min(s2 - ci1, n - 1))
        r1, c1 = table.get_coord(i1)
        r2, c2 = table.get_coord(max(i1, i2 - 1))
        return min(r1, r2), min(c1, c2), max(r1, r2), max(c1, c2)

    def _apply_to_table(self, fn):
        """Find table, apply fn(table, r1, c1, r2, c2) → new_table, commit via undo."""
        table, offset = self._find_table_texel()
        if table is None:
            return
        r1, c1, r2, c2 = self._selected_cell_range(table, offset)
        new_table = fn(table, r1, c1, r2, c2)
        if new_table is table:
            return
        with self._view.atomic():
            self._view.remove(offset, offset + length(table))
            self._view.insert_texel(offset, new_table)

    # --- border preset ---

    @staticmethod
    def _set_border(table, r1, c1, r2, c2, side, val):
        """Set one border side of a selection, keeping both adjacent cells in sync."""
        nrows, ncols = table.nrows, table.ncols
        t = table
        if side == 'left':
            t = t.set_cellattr(r1, c1, r2, c1, border_left=val)
            if c1 > 0:
                t = t.set_cellattr(r1, c1 - 1, r2, c1 - 1, border_right=val)
        elif side == 'right':
            t = t.set_cellattr(r1, c2, r2, c2, border_right=val)
            if c2 + 1 < ncols:
                t = t.set_cellattr(r1, c2 + 1, r2, c2 + 1, border_left=val)
        elif side == 'top':
            t = t.set_cellattr(r1, c1, r1, c2, border_top=val)
            if r1 > 0:
                t = t.set_cellattr(r1 - 1, c1, r1 - 1, c2, border_bottom=val)
        elif side == 'bottom':
            t = t.set_cellattr(r2, c1, r2, c2, border_bottom=val)
            if r2 + 1 < nrows:
                t = t.set_cellattr(r2 + 1, c1, r2 + 1, c2, border_top=val)
        elif side == 'inner_v':
            for c in range(c1 + 1, c2 + 1):
                t = t.set_cellattr(r1, c, r2, c, border_left=val)
                t = t.set_cellattr(r1, c - 1, r2, c - 1, border_right=val)
        elif side == 'inner_h':
            for r in range(r1 + 1, r2 + 1):
                t = t.set_cellattr(r, c1, r, c2, border_top=val)
                t = t.set_cellattr(r - 1, c1, r - 1, c2, border_bottom=val)
        return t

    def _on_border_preset(self, event):
        btn = event.GetEventObject()
        key = btn.preset_key
        s = self._line_style.Selection
        line = ['thin', 'thick', 'double'][s]
        sb = self._set_border

        def apply(table, r1, c1, r2, c2):
            if key == 'none':
                # Clear all 4 attributes on selection cells + sync all neighbors
                t = table.set_cellattr(r1, c1, r2, c2,
                                       border_left='none', border_right='none',
                                       border_top='none', border_bottom='none')
                if c1 > 0:
                    t = t.set_cellattr(r1, c1 - 1, r2, c1 - 1, border_right='none')
                if c2 + 1 < table.ncols:
                    t = t.set_cellattr(r1, c2 + 1, r2, c2 + 1, border_left='none')
                if r1 > 0:
                    t = t.set_cellattr(r1 - 1, c1, r1 - 1, c2, border_bottom='none')
                if r2 + 1 < table.nrows:
                    t = t.set_cellattr(r2 + 1, c1, r2 + 1, c2, border_top='none')
                return t
            elif key == 'all':
                t = table.set_cellattr(r1, c1, r2, c2,
                                       border_left=line, border_right=line,
                                       border_top=line, border_bottom=line)
                if c1 > 0:
                    t = t.set_cellattr(r1, c1 - 1, r2, c1 - 1, border_right=line)
                if c2 + 1 < table.ncols:
                    t = t.set_cellattr(r1, c2 + 1, r2, c2 + 1, border_left=line)
                if r1 > 0:
                    t = t.set_cellattr(r1 - 1, c1, r1 - 1, c2, border_bottom=line)
                if r2 + 1 < table.nrows:
                    t = t.set_cellattr(r2 + 1, c1, r2 + 1, c2, border_top=line)
                return t
            elif key == 'outer':
                t = sb(table, r1, c1, r2, c2, 'left',   line)
                t = sb(t,     r1, c1, r2, c2, 'right',  line)
                t = sb(t,     r1, c1, r2, c2, 'top',    line)
                t = sb(t,     r1, c1, r2, c2, 'bottom', line)
                return t
            elif key == 'inner':
                t = sb(table, r1, c1, r2, c2, 'inner_h', line)
                t = sb(t,     r1, c1, r2, c2, 'inner_v', line)
                return t
            elif key == 'inner_h':
                return sb(table, r1, c1, r2, c2, 'inner_h', line)
            elif key == 'inner_v':
                return sb(table, r1, c1, r2, c2, 'inner_v', line)
            elif key == 'left':
                return sb(table, r1, c1, r2, c2, 'left',   line)
            elif key == 'right':
                return sb(table, r1, c1, r2, c2, 'right',  line)
            elif key == 'top':
                return sb(table, r1, c1, r2, c2, 'top',    line)
            elif key == 'bottom':
                return sb(table, r1, c1, r2, c2, 'bottom', line)
            return table

        self._apply_to_table(apply)

    # --- row/column operations ---

    def on_row_menu(self, _evt):
        table, ci1, r, c = self._current_cell()
        menu = wx.Menu()
        m1 = menu.Append(wx.ID_ANY, "Insert row below")
        m2 = menu.Append(wx.ID_ANY, "Insert row above")
        m3 = menu.Append(wx.ID_ANY, "Delete row")
        self.Bind(wx.EVT_MENU, lambda e: self._apply_to_table(lambda t, *_: t.insert_rows(r + 1, 1)), m1)
        self.Bind(wx.EVT_MENU, lambda e: self._apply_to_table(lambda t, *_: t.insert_rows(r,     1)), m2)
        self.Bind(wx.EVT_MENU, lambda e: self._apply_to_table(lambda t, *_: t.remove_rows(r,     1)), m3)
        pos = self._btn_row.GetPosition()
        self.PopupMenu(menu, wx.Point(pos.x, pos.y + self._btn_row.GetSize().height))
        menu.Destroy()

    def on_col_menu(self, _evt):
        table, ci1, r, c = self._current_cell()
        menu = wx.Menu()
        m1 = menu.Append(wx.ID_ANY, "Insert column right")
        m2 = menu.Append(wx.ID_ANY, "Insert column left")
        m3 = menu.Append(wx.ID_ANY, "Delete column")
        self.Bind(wx.EVT_MENU, lambda e: self._apply_to_table(lambda t, *_: t.insert_cols(c + 1, 1)), m1)
        self.Bind(wx.EVT_MENU, lambda e: self._apply_to_table(lambda t, *_: t.insert_cols(c,     1)), m2)
        self.Bind(wx.EVT_MENU, lambda e: self._apply_to_table(lambda t, *_: t.remove_cols(c,     1)), m3)
        pos = self._btn_col.GetPosition()
        self.PopupMenu(menu, wx.Point(pos.x, pos.y + self._btn_col.GetSize().height))
        menu.Destroy()

    def _current_cell(self):
        table, ci1 = self._find_table_texel()
        if table is None:
            return None, None, None, None
        r1, c1, r2, c2 = self._selected_cell_range(table, ci1)
        return table, ci1, r1, c1

    # --- cell style ---

    def _on_bgcolor(self):
        colour = self._bgcolor_btn._colour
        if colour is not None:
            self._set_cell_attr('cell_bgcolor',
                                wx.Colour(colour).GetAsString(wx.C2S_HTML_SYNTAX))

    def _on_valign(self, event):
        choices = ['top', 'middle', 'bottom']
        val = choices[self._valign.GetSelection()]
        self._set_cell_attr('valign', val)

    def _set_cell_attr(self, attr, value):
        self._apply_to_table(
            lambda table, r1, c1, r2, c2: table.set_cellattr(r1, c1, r2, c2, **{attr: value})
        )


def demo_00():
    app = wx.App()
    frame = wx.Frame(None, title="TablePanel Demo", size=(300, 500))

    class _FakeView:
        def add_view(self, v): pass

    TablePanel(frame, view=_FakeView())
    frame.Show()
    app.MainLoop()


if __name__ == '__main__':
    demo_00()
