import wx
from wx.lib.newevent import NewEvent

from ..textmodel.texeltree import length
from ..ui.sidepanel import SidePanel
from ..ui.threestate import ColourButton
from ..ui.icons import icon
from ..ui.design import muted_button, make_panel, add_section
from ..ui.colours import colours
from ..core.utils import get_path
from .tables import Table, empty_table

TableCreatedEvent, EVT_TABLE_CREATED = NewEvent()

COLS = 10
ROWS = 8

CELL_SIZE = 16
CELL_GAP  = 3
PADDING   = 8


class _TableGrid(wx.Panel):
    """Cell grid — fixed COLS×ROWS, cell size derived from target width."""

    _LABEL_H = 24   # room for combined title line (logical px)

    def __init__(self, parent, target_w):
        super().__init__(parent)
        dip = self.FromDIP
        self._padding = dip(PADDING)
        self._gap     = dip(CELL_GAP)
        self._label_h = dip(self._LABEL_H)
        # back-calculate cell size so grid fills target_w exactly
        cell = (target_w - 2 * self._padding - (COLS - 1) * self._gap) // COLS
        self._cell = max(cell, dip(8))
        w = 2 * self._padding + COLS * self._cell + (COLS - 1) * self._gap
        h = self._label_h + ROWS * self._cell + (ROWS - 1) * self._gap + self._padding
        self.SetSize((w, h))
        self.SetMinSize((w, h))
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)   # suppress default erase → no flicker
        self._col = 0
        self._row = 0

        self.Bind(wx.EVT_PAINT,        self._on_paint)
        self.Bind(wx.EVT_MOTION,       self._on_motion)
        self.Bind(wx.EVT_LEFT_UP,      self._on_click)
        self.Bind(wx.EVT_LEAVE_WINDOW, self._on_leave)

    def _cell_origin(self, col, row):
        x = self._padding + col * (self._cell + self._gap)
        y = self._label_h + row * (self._cell + self._gap)
        return x, y

    def _hit(self, px, py):
        for row in range(ROWS):
            for col in range(COLS):
                x, y = self._cell_origin(col, row)
                if x <= px < x + self._cell and y <= py < y + self._cell:
                    return col + 1, row + 1
        return 0, 0

    def _on_paint(self, event):
        gc        = wx.SystemSettings.GetColour
        btnface   = gc(wx.SYS_COLOUR_BTNFACE)
        highlight = gc(wx.SYS_COLOUR_HIGHLIGHT)
        shadow    = gc(wx.SYS_COLOUR_BTNSHADOW)
        wintext   = gc(wx.SYS_COLOUR_WINDOWTEXT)
        graytext  = gc(wx.SYS_COLOUR_GRAYTEXT)

        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(btnface))
        dc.Clear()

        if self._col:
            label = f"Insert table: {self._col} \u00d7 {self._row}"
            dc.SetTextForeground(wintext)
        else:
            label = "Insert table"
            dc.SetTextForeground(graytext)
        dc.DrawText(label, self._padding, self.FromDIP(4))

        for row in range(ROWS):
            for col in range(COLS):
                x, y = self._cell_origin(col, row)
                if col < self._col and row < self._row:
                    dc.SetBrush(wx.Brush(highlight.ChangeLightness(150)))
                    dc.SetPen(wx.Pen(highlight))
                else:
                    dc.SetBrush(wx.Brush(shadow.ChangeLightness(130)))
                    dc.SetPen(wx.Pen(shadow))
                dc.DrawRectangle(x, y, self._cell, self._cell)

    def _on_motion(self, event):
        col, row = self._hit(event.GetX(), event.GetY())
        if col != 0 and (col != self._col or row != self._row):
            self._col = col
            self._row = row
            wx.CallAfter(self.Refresh)
        event.Skip()

    def _on_click(self, event):
        if self._col > 0:
            wx.PostEvent(self, TableCreatedEvent(cols=self._col, rows=self._row))
        event.Skip()

    def _on_leave(self, event):
        if self._col:
            self._col = 0
            self._row = 0
            wx.CallAfter(self.Refresh)
        event.Skip()


class _CustomItem(wx.Panel):
    """Clickable 'Insert custom table'."""

    def __init__(self, parent):
        super().__init__(parent)
        colours.set(self, 'BackgroundColour', 'BTNFACE')
        lbl = wx.StaticText(self, label="Insert custom table")
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(lbl, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, self.FromDIP(6))
        self.SetSizer(sizer)

        self.SetCursor(wx.Cursor(wx.CURSOR_HAND))
        for w in (self, lbl):
            w.Bind(wx.EVT_ENTER_WINDOW, self._on_enter)
            w.Bind(wx.EVT_LEAVE_WINDOW, self._on_leave)
            w.Bind(wx.EVT_LEFT_UP,      self._on_click)

    def _on_enter(self, event):
        gc = wx.SystemSettings.GetColour
        self.SetBackgroundColour(gc(wx.SYS_COLOUR_HIGHLIGHT).ChangeLightness(185))
        self.Refresh()

    def _on_leave(self, event):
        self.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_BTNFACE))
        self.Refresh()

    def _on_click(self, event):
        # cols=0, rows=0 signals "custom"
        wx.PostEvent(self, TableCreatedEvent(cols=0, rows=0))


def _make_table_popup_content(popup, width):
    """Shared setup: grid + separator + custom item, returns (grid, custom)."""
    popup.custom = _CustomItem(popup)
    target_w = width or popup.custom.GetBestSize().width
    popup.grid = _TableGrid(popup, target_w)
    separator  = wx.StaticLine(popup)
    sizer = wx.BoxSizer(wx.VERTICAL)
    sizer.Add(popup.grid,   0, wx.EXPAND)
    sizer.Add(separator,    0, wx.EXPAND)
    sizer.Add(popup.custom, 0, wx.EXPAND)
    popup.SetSizer(sizer)
    popup.Fit()


class _TablePopup(wx.PopupWindow):
    """Grid popup for table insertion.

    Uses wx.PopupWindow instead of wx.PopupTransientWindow so that it
    receives keyboard focus on all platforms (PopupTransientWindow cannot
    become the key window on macOS).  Click-outside dismiss is handled
    via EVT_ACTIVATE rather than the transient mechanism.

    wx.PU_CONTAINS_CONTROLS is required for that: on MSW, a plain
    wx.PopupWindow never takes focus from its parent at all, so it can
    never receive EVT_ACTIVATE's deactivate transition either -- without
    this flag the popup is simply stuck open on Windows.
    """

    def __init__(self, parent, width):
        super().__init__(parent, wx.BORDER_SIMPLE | wx.PU_CONTAINS_CONTROLS)
        colours.set(self, 'BackgroundColour', 'BTNFACE')
        _make_table_popup_content(self, width)
        self._dismissed = False
        self.Bind(wx.EVT_ACTIVATE,  self._on_activate)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_key)

    def _on_activate(self, event):
        if not event.GetActive():
            self.Dismiss()
        event.Skip()

    def _on_key(self, event):
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.Dismiss()
        else:
            event.Skip()

    def Popup(self):
        self.Show()
        self.Raise()
        self.grid.SetFocus()

    def Dismiss(self):
        # Both the explicit dismiss (on selection) and EVT_ACTIVATE's
        # deactivate transition call Dismiss() -- e.g. "Insert custom
        # table" dismisses the popup and then opens a modal dialog, whose
        # focus grab re-triggers EVT_ACTIVATE on the (still alive, just
        # hidden) popup. Without this guard that schedules Destroy twice,
        # and the second one crashes with "wrapped C/C++ object ... has
        # been deleted" once the first has already run.
        if self._dismissed:
            return
        self._dismissed = True
        self.Hide()
        wx.CallAfter(self.Destroy)


class CustomTableDialog(wx.Dialog):
    """Dialog for specifying arbitrary table dimensions."""

    def __init__(self, parent):
        super().__init__(parent, title="Table size",
                         style=wx.DEFAULT_DIALOG_STYLE)
        colours.set(self, 'BackgroundColour', 'BTNFACE')

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


class TablePanel(SidePanel):
    """Inspector panel for inserting and editing tables."""

    def __init__(self, parent, view):
        SidePanel.__init__(self, parent)
        self._view = view
        self.add_model(view)
        self.create()

    def create(self):
        dip = self.FromDIP
        sizer = make_panel(self, "TABLES")

        # --- Section: Insert ---
        add_section("Insert", self, sizer)
        btn = TableCreatorButton(self)
        btn.Bind(EVT_TABLE_CREATED, self._on_insert)
        sizer.Add(btn, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, dip(5))

        # --- Section: Borders ---
        add_section("Borders", self, sizer)
        self._line_style = wx.Choice(self, choices=['Thin line', 'Thick line', 'Double line'])
        self._line_style.SetSelection(0)
        sizer.Add(self._line_style, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, dip(5))

        grid_sizer = wx.GridSizer(rows=2, cols=5, hgap=dip(2), vgap=dip(2))
        self._border_btns = []
        for icon_name, key in _BORDER_PRESETS:
            btn = wx.BitmapButton(self, bitmap=icon(icon_name + '.svg', (24, 24)),
                                  size=(dip(32), dip(32)))
            btn.preset_key = key
            btn.Bind(wx.EVT_BUTTON, self._on_border_preset)
            grid_sizer.Add(btn, 0, wx.EXPAND)
            self._border_btns.append(btn)
        sizer.Add(grid_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, dip(5))

        # --- Section: Rows && Columns ---
        add_section("Rows && Columns", self, sizer)
        row_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self._btn_row = wx.Button(self, label="Row ▾")
        self._btn_col = wx.Button(self, label="Column ▾")
        self._btn_row.Bind(wx.EVT_LEFT_DOWN, self.on_row_menu)
        self._btn_col.Bind(wx.EVT_LEFT_DOWN, self.on_col_menu)
        row_sizer.Add(self._btn_row, 1, wx.RIGHT, dip(4))
        row_sizer.Add(self._btn_col, 1)
        sizer.Add(row_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, dip(5))

        self._chk_header = wx.CheckBox(self, label="Header row")
        self._chk_header.Bind(wx.EVT_CHECKBOX, self._on_header)
        sizer.Add(self._chk_header, 0, wx.LEFT | wx.TOP, dip(5))

        # --- Section: Cell ---
        add_section("Cell", self, sizer)
        cell_sizer = wx.FlexGridSizer(rows=3, cols=2, hgap=dip(4), vgap=dip(4))
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

        sizer.Add(cell_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, dip(5))

        self._table_controls = (
            [self._btn_row, self._btn_col, self._chk_header, self._line_style,
             self._bgcolor_btn, self._valign]
            + self._border_btns
        )
        self._set_table_controls(False)

    def update(self):
        self._update_cell_inspector()

    def _on_insert(self, event):
        if event.cols == 0:
            return  # custom dialog was cancelled
        table = empty_table(event.rows, event.cols)
        self._view.insert_texel(table)


    def _set_table_controls(self, enabled):
        for w in self._table_controls:
            w.Enable(enabled)

    def _update_cell_inspector(self):
        table, ci1 = self._find_table_texel()
        self._set_table_controls(table is not None)
        if table is None:
            return
        self._chk_header.SetValue(table.nheader > 0)
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
        for abs_i1, abs_i2, node in get_path(self._view.target.texel, index):
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
        r2, c2 = table.get_coord(max(i1, i2))
        return min(r1, r2), min(c1, c2), max(r1, r2), max(c1, c2)

    def _replace_table(self, offset, table, new_table):
        """Replace table at offset with new_table, as one undo-able edit."""
        view = self._view
        new = view.target.create_textmodel()
        new.texel = new_table
        i = view.abs_idx(offset)
        n = length(table)
        with view.atomic():
            view.add_undo(view._remove(view.flow, i, i+n))
            view.add_undo(view._insert(view.flow, i, new))

    def _on_header(self, event):
        table, offset = self._find_table_texel()
        if table is None:
            return
        new_table = table.set_nheader(1 if event.IsChecked() else 0)
        if new_table is table:
            return
        self._replace_table(offset, table, new_table)

    def _apply_to_table(self, fn):
        """Find table, apply fn(table, r1, c1, r2, c2) → new_table, commit via undo."""
        table, offset = self._find_table_texel()
        if table is None:
            return
        r1, c1, r2, c2 = self._selected_cell_range(table, offset)
        new_table = fn(table, r1, c1, r2, c2)
        if new_table is table:
            return
        self._replace_table(offset, table, new_table)

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


def test_00():
    "table-size popup requests PU_CONTAINS_CONTROLS (needed to dismiss it on Windows)"
    app = wx.App()
    frame = wx.Frame(None)
    popup = _TablePopup(frame, 200)
    assert popup.GetWindowStyle() & wx.PU_CONTAINS_CONTROLS
    popup.Destroy()
    frame.Destroy()


def test_01():
    "calling Dismiss() more than once doesn't crash (e.g. selection dismiss + EVT_ACTIVATE)"
    app = wx.App()
    frame = wx.Frame(None)
    popup = _TablePopup(frame, 200)
    popup.Popup()
    popup.Dismiss()
    popup.Dismiss()   # must be a no-op, not a second wx.CallAfter(Destroy)
    app.ProcessPendingEvents()
    wx.MilliSleep(10)
    app.ProcessPendingEvents()   # runs the pending CallAfter(s); would raise if doubled
    frame.Destroy()


def demo_00():
    app = wx.App()
    frame = wx.Frame(None, title="TablePanel Demo", size=(300, 500))

    class _FakeView:
        index    = 0
        selection = None
        def add_view(self, v):    pass
        def has_selection(self):  return False
        def insert_texel(self, t): pass
        def remove(self):         pass
        def atomic(self):
            from contextlib import contextmanager
            @contextmanager
            def _ctx(): yield
            return _ctx()

    TablePanel(frame, view=_FakeView())
    frame.Show()
    app.MainLoop()


if __name__ == '__main__':
    demo_00()
