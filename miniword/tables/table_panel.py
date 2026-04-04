import wx
from wx.lib.newevent import NewEvent

from ..textmodel.viewbase import ViewBase
from ..textmodel.texeltree import length
from ..ui.styleinspector import add_section
from ..ui.threestate import ColourButton
from ..ui.icons import icon
from .tables import Table, empty_table
from ..ui.documentview import find_texel, transform, get_path

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
            label = f"Tabelle einfügen: {self._col} x {self._row}"
            dc.SetTextForeground(COL_TEXT)
        else:
            label = "Tabelle einfügen"
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
    """Clickable 'Benutzerdefinierte Tabelle einfügen' row."""

    def __init__(self, parent):
        super().__init__(parent)
        self.SetBackgroundColour(COL_BG)
        lbl = wx.StaticText(self, label="Benutzerdefinierte Tabelle einfügen")
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
    def __init__(self, parent):
        super().__init__(parent, wx.BORDER_SIMPLE)
        self.SetBackgroundColour(COL_BG)

        # Measure label width so the grid matches it exactly
        self.custom = _CustomItem(self)
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
        super().__init__(parent, title="Größe der Tabelle",
                         style=wx.DEFAULT_DIALOG_STYLE)
        self.SetBackgroundColour(COL_BG)

        lbl_cols = wx.StaticText(self, label="Anzahl von Spalten")
        self.spin_cols = wx.SpinCtrl(self, value="2", min=1, max=50)

        lbl_rows = wx.StaticText(self, label="Anzahl von Zeilen")
        self.spin_rows = wx.SpinCtrl(self, value="2", min=1, max=50)

        btn_ok     = wx.Button(self, wx.ID_OK,     label="OK")
        btn_cancel = wx.Button(self, wx.ID_CANCEL, label="Abbrechen")
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
    """Button that opens a table-size picker dropdown.

    Fires EVT_TABLE_CREATED with .cols/.rows on the button.
    cols=0, rows=0 means "custom table".
    """

    def __init__(self, parent, label="Tabelle"):
        super().__init__(parent, label=label)
        self.Bind(wx.EVT_BUTTON, self._on_click)

    def _on_click(self, event):
        popup = _TablePopup(self)
        on_sel = lambda e: self._on_selected(popup, e)
        popup.grid.Bind(EVT_TABLE_CREATED,   on_sel)
        popup.custom.Bind(EVT_TABLE_CREATED, on_sel)
        pos  = self.GetScreenPosition()
        size = self.GetSize()
        popup.Position(pos, (0, size.height))
        popup.Popup()
        wx.CallAfter(popup.grid.SetFocus)

    def _on_selected(self, popup, event):
        popup.Dismiss()
        if event.cols == 0:
            self._show_custom_dialog()
        else:
            wx.PostEvent(self, TableCreatedEvent(cols=event.cols, rows=event.rows))

    def _show_custom_dialog(self):
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
        self.SetBackgroundColour(COL_BG)
        self._view = view
        self._table_index = None
        self._table_box = None
        self.add_model(view)

        sizer = wx.BoxSizer(wx.VERTICAL)

        hdr = wx.StaticText(self, label="TABELLE")
        hdr.SetForegroundColour(COL_MUTED)
        sizer.Add(hdr, 0, wx.LEFT | wx.TOP, 10)

        # --- Section: Einfügen ---
        add_section("Einfügen", self, sizer)
        btn = TableCreatorButton(self)
        btn.Bind(EVT_TABLE_CREATED, self._on_insert)
        sizer.Add(btn, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5)

        # --- Section: Rahmen ---
        add_section("Rahmen", self, sizer)
        self._line_style = wx.Choice(self, choices=['thin', 'thick', 'double', 'none'])
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

        # --- Section: Zeilen & Spalten ---
        add_section("Zeilen & Spalten", self, sizer)
        row_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self._btn_row = wx.Button(self, label="Zeile ▾")
        self._btn_col = wx.Button(self, label="Spalte ▾")
        self._btn_row.Bind(wx.EVT_BUTTON, self._on_row_menu)
        self._btn_col.Bind(wx.EVT_BUTTON, self._on_col_menu)
        row_sizer.Add(self._btn_row, 1, wx.RIGHT, 4)
        row_sizer.Add(self._btn_col, 1)
        sizer.Add(row_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5)

        # --- Section: Zelle ---
        add_section("Zelle", self, sizer)
        cell_sizer = wx.FlexGridSizer(rows=3, cols=2, hgap=4, vgap=4)
        cell_sizer.AddGrowableCol(1)

        cell_sizer.Add(wx.StaticText(self, label="Hintergrund"), 0, wx.ALIGN_CENTER_VERTICAL)
        self._bgcolor_btn = ColourButton(self)
        self._bgcolor_btn.callback = self._on_bgcolor
        cell_sizer.Add(self._bgcolor_btn, 0, wx.EXPAND)

        cell_sizer.Add(wx.StaticText(self, label="V-Ausricht."), 0, wx.ALIGN_CENTER_VERTICAL)
        self._valign = wx.Choice(self, choices=['top', 'middle', 'bottom'])
        self._valign.SetSelection(0)
        self._valign.Bind(wx.EVT_CHOICE, self._on_valign)
        cell_sizer.Add(self._valign, 0, wx.EXPAND)

        sizer.Add(cell_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5)

        padded = wx.BoxSizer(wx.VERTICAL)
        padded.Add(sizer, 1, wx.EXPAND | wx.ALL, 8)
        self.SetSizer(padded)
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

    def _update_cell_inspector(self):
        table, ci1 = self._find_table_texel()
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
        """Find table, apply fn(table, r1, c1, r2, c2) → new_table, commit."""
        table, offset = self._find_table_texel()
        if table is None:
            return
        r1, c1, r2, c2 = self._selected_cell_range(table, offset)
        new_table = fn(table, r1, c1, r2, c2)
        if new_table is table:
            return
        model = self._view.model
        _, _, depth = find_texel(model.texel, table, offset)
        model.texel = transform(model.texel, offset, depth, lambda t: new_table)
        model.notify_views('properties_changed', offset, offset + 1)

    def _apply_table_replace(self, new_table_fn):
        """Find table, replace it with new_table_fn(table) → new_table."""
        table, offset = self._find_table_texel()
        if table is None:
            return
        new_table = new_table_fn(table)
        if new_table is table:
            return
        model = self._view.model
        with self._view.atomic():
            model.remove(offset, offset + length(table))
            self._view.insert_texel(offset, new_table)

    # --- border preset ---

    def _on_border_preset(self, event):
        btn = event.GetEventObject()
        key = btn.preset_key
        line = self._line_style.GetStringSelection()

        def apply(table, r1, c1, r2, c2):
            if key == 'none':
                return table.set_cellattr(r1, c1, r2, c2,
                                          border_left='none', border_right='none',
                                          border_top='none', border_bottom='none')
            elif key == 'all':
                return table.set_cellattr(r1, c1, r2, c2,
                                          border_left=line, border_right=line,
                                          border_top=line, border_bottom=line)
            elif key == 'outer':
                t = table.set_cellattr(r1, c1, r2, c2,
                                       border_left='none', border_right='none',
                                       border_top='none', border_bottom='none')
                for r in range(r1, r2 + 1):
                    for c in range(c1, c2 + 1):
                        kwargs = {}
                        if r == r1:  kwargs['border_top'] = line
                        if r == r2:  kwargs['border_bottom'] = line
                        if c == c1:  kwargs['border_left'] = line
                        if c == c2:  kwargs['border_right'] = line
                        if kwargs:
                            t = t.set_cellattr(r, c, r, c, **kwargs)
                return t
            elif key == 'inner':
                t = table
                for r in range(r1, r2 + 1):
                    for c in range(c1, c2 + 1):
                        kwargs = {}
                        if r1 < r:   kwargs['border_top'] = line
                        if r < r2:   kwargs['border_bottom'] = line
                        if c1 < c:   kwargs['border_left'] = line
                        if c < c2:   kwargs['border_right'] = line
                        if kwargs:
                            t = t.set_cellattr(r, c, r, c, **kwargs)
                return t
            elif key == 'inner_h':
                t = table
                for r in range(r1 + 1, r2 + 1):
                    t = t.set_cellattr(r, c1, r, c2, border_top=line)
                return t
            elif key == 'inner_v':
                t = table
                for c in range(c1 + 1, c2 + 1):
                    t = t.set_cellattr(r1, c, r2, c, border_left=line)
                return t
            elif key == 'left':
                return table.set_cellattr(r1, c1, r2, c2, border_left=line)
            elif key == 'right':
                return table.set_cellattr(r1, c1, r2, c2, border_right=line)
            elif key == 'top':
                return table.set_cellattr(r1, c1, r2, c2, border_top=line)
            elif key == 'bottom':
                return table.set_cellattr(r1, c1, r2, c2, border_bottom=line)
            return table

        self._apply_to_table(apply)

    # --- row/column operations ---

    def _on_row_menu(self, event):
        menu = wx.Menu()
        menu.Append(1, "Zeile darunter einfügen")
        menu.Append(2, "Zeile darüber einfügen")
        menu.Append(3, "Zeile löschen")
        self.Bind(wx.EVT_MENU, self._on_row_action, id=1)
        self.Bind(wx.EVT_MENU, self._on_row_action, id=2)
        self.Bind(wx.EVT_MENU, self._on_row_action, id=3)
        self._btn_row.PopupMenu(menu)
        menu.Destroy()

    def _on_col_menu(self, event):
        menu = wx.Menu()
        menu.Append(4, "Spalte rechts einfügen")
        menu.Append(5, "Spalte links einfügen")
        menu.Append(6, "Spalte löschen")
        self.Bind(wx.EVT_MENU, self._on_col_action, id=4)
        self.Bind(wx.EVT_MENU, self._on_col_action, id=5)
        self.Bind(wx.EVT_MENU, self._on_col_action, id=6)
        self._btn_col.PopupMenu(menu)
        menu.Destroy()

    def _current_cell(self):
        table, ci1 = self._find_table_texel()
        if table is None:
            return None, None, None, None
        r1, c1, r2, c2 = self._selected_cell_range(table, ci1)
        return table, ci1, r1, c1

    def _on_row_action(self, event):
        eid = event.GetId()
        table, ci1, r, c = self._current_cell()
        if table is None:
            return
        if eid == 1:
            self._apply_table_replace(lambda t: t.insert_rows(r + 1, 1))
        elif eid == 2:
            self._apply_table_replace(lambda t: t.insert_rows(r, 1))
        elif eid == 3:
            self._apply_table_replace(lambda t: t.remove_rows(r, 1))

    def _on_col_action(self, event):
        eid = event.GetId()
        table, ci1, r, c = self._current_cell()
        if table is None:
            return
        if eid == 4:
            self._apply_table_replace(lambda t: t.insert_cols(c + 1, 1))
        elif eid == 5:
            self._apply_table_replace(lambda t: t.insert_cols(c, 1))
        elif eid == 6:
            self._apply_table_replace(lambda t: t.remove_cols(c, 1))

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
        table, offset = self._find_table_texel()
        if table is None:
            return
        r1, c1, r2, c2 = self._selected_cell_range(table, offset)
        new_table = table.set_cellattr(r1, c1, r2, c2, **{attr: value})
        model = self._view.model
        _, _, depth = find_texel(model.texel, table, offset)
        model.texel = transform(model.texel, offset, depth, lambda t: new_table)
        model.notify_views('properties_changed', offset, offset + 1)


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
