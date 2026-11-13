"""The words not marked by the spell check, in a table to see and edit:
those of the document and those of the user dictionary (see
texteditor/spellcheck.py)."""

import wx
import wx.grid

PLACES = ['Document', 'User']


class WordsDialog(wx.Dialog):
    def __init__(self, parent, document_words, user_words):
        super().__init__(parent, title="Spelling words",
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        rows = [(word, 'Document') for word in document_words] \
            + [(word, 'User') for word in user_words]
        rows.sort(key=lambda row: row[0].lower())
        grid = self.grid = wx.grid.Grid(self)
        grid.CreateGrid(0, 2)
        grid.SetColLabelValue(0, "Word")
        grid.SetColLabelValue(1, "Dictionary")
        grid.HideRowLabels()
        attr = wx.grid.GridCellAttr()
        attr.SetEditor(wx.grid.GridCellChoiceEditor(PLACES))
        grid.SetColAttr(1, attr)
        for word, place in rows:
            self.append(word, place)
        grid.SetColSize(0, self.FromDIP(220))
        grid.SetColSize(1, self.FromDIP(110))

        add = wx.Button(self, label="Add")
        remove = wx.Button(self, label="Remove")
        add.Bind(wx.EVT_BUTTON, self.on_add)
        remove.Bind(wx.EVT_BUTTON, self.on_remove)
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        buttons.Add(add)
        buttons.Add(remove, 0, wx.LEFT, self.FromDIP(6))
        buttons.AddStretchSpacer()
        buttons.Add(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL))
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(grid, 1, wx.EXPAND | wx.ALL, self.FromDIP(8))
        sizer.Add(buttons, 0, wx.EXPAND | wx.ALL, self.FromDIP(8))
        self.SetSizer(sizer)
        self.SetSize(self.FromDIP(wx.Size(380, 420)))

    def append(self, word, place):
        grid = self.grid
        grid.AppendRows(1)
        row = grid.GetNumberRows() - 1
        grid.SetCellValue(row, 0, word)
        grid.SetCellValue(row, 1, place)
        return row

    def on_add(self, event):
        row = self.append('', 'Document')
        self.grid.MakeCellVisible(row, 0)
        self.grid.SetGridCursor(row, 0)
        self.grid.EnableCellEditControl()

    def on_remove(self, event):
        grid = self.grid
        grid.DisableCellEditControl()
        rows = {row for block in grid.GetSelectedBlocks()
                for row in range(block.GetTopRow(), block.GetBottomRow() + 1)}
        if not rows and grid.GetNumberRows():
            rows = {grid.GetGridCursorRow()}
        for row in sorted(rows, reverse=True):
            grid.DeleteRows(row)

    def words(self):
        """(document words, user words): the words of the cells."""
        grid = self.grid
        grid.DisableCellEditControl()  # take the value being edited
        found = {place: set() for place in PLACES}
        for row in range(grid.GetNumberRows()):
            found[grid.GetCellValue(row, 1)].update(
                grid.GetCellValue(row, 0).split())
        return frozenset(found['Document']), found['User']


def test_00():
    "the table: both lists, edited, added, removed"
    app = wx.App.Get() or wx.App(False)
    frame = wx.Frame(None)
    dialog = WordsDialog(frame, {'Zorgle', 'miniword'}, {'Blorp'})
    grid = dialog.grid
    assert [grid.GetCellValue(row, 0) for row in range(3)] \
        == ['Blorp', 'miniword', 'Zorgle']
    assert dialog.words() == ({'Zorgle', 'miniword'}, {'Blorp'})
    grid.SetCellValue(1, 1, 'User')     # miniword to the user dictionary
    grid.SetCellValue(0, 0, ' Blörp ')  # edited
    dialog.append('', 'Document')       # empty: dropped
    dialog.append('Neu Alt', 'Document')  # two words
    assert dialog.words() == ({'Zorgle', 'Neu', 'Alt'},
                              {'miniword', 'Blörp'})
    grid.SetGridCursor(2, 0)            # Zorgle
    dialog.on_remove(None)
    assert dialog.words() == ({'Neu', 'Alt'}, {'miniword', 'Blörp'})
    dialog.Destroy()
    frame.Destroy()
