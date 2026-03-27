import wx
from wx.lib.newevent import NewEvent
from .textmodel.viewbase import ViewBase
from .inspector import add_section

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


class TablePanel(wx.Panel, ViewBase):
    """Inspector panel for inserting and editing tables."""

    def __init__(self, parent, view):
        wx.Panel.__init__(self, parent)
        ViewBase.__init__(self)
        self.SetBackgroundColour(COL_BG)
        self._view = view
        self.add_model(view)

        sizer = wx.BoxSizer(wx.VERTICAL)

        hdr = wx.StaticText(self, label="TABELLE")
        hdr.SetForegroundColour(COL_MUTED)
        sizer.Add(hdr, 0, wx.LEFT | wx.TOP, 10)

        add_section("Einfügen", self, sizer)
        btn = TableCreatorButton(self)
        btn.Bind(EVT_TABLE_CREATED, self._on_insert)
        sizer.Add(btn, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 5)

        padded = wx.BoxSizer(wx.VERTICAL)
        padded.Add(sizer, 1, wx.EXPAND | wx.ALL, 8)
        self.SetSizer(padded)

    def _on_insert(self, event):
        if event.cols == 0:
            return  # custom dialog was cancelled
        from .tables import mk_table
        from .textmodel.texeltree import grouped
        table = mk_table([[''] * event.cols for _ in range(event.rows)])
        self._view.insert_texel(self._view.index, grouped([table]))

    def editor_changed(self, view, editor):
        pass


def demo_00():
    app = wx.App()
    frame = wx.Frame(None, title="TablePanel Demo", size=(300, 300))

    class _FakeView:
        def add_view(self, v): pass

    TablePanel(frame, view=_FakeView())
    frame.Show()
    app.MainLoop()


if __name__ == '__main__':
    demo_00()
