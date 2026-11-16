# Example plugin: Word Count in a dialog
# Install: copy into the plugins directory (see README.md, "Plugins").
#
# Like wordcount.py, but the counts stay open in a modeless dialog: keep
# editing and press Update. Counts the words of the document - main text
# and footnotes - and of the selection. A word is a run of non-whitespace
# characters with at least one letter or digit, so placeholders of
# images, rules or footnote anchors don't count.

import wx

from miniword.textmodel.texeltree import get_text
from miniword.footnotes.footnotes import iter_footnotes

name = "Word Count…"  # "…": opens a window


def count_words(text):
    return sum(1 for word in text.split()
               if any(c.isalnum() for c in word))


def document_words(model):
    """(words in the main text, words in the footnotes)"""
    main = count_words(model.get_text())
    notes = sum(count_words(get_text(chain[-1][1].content))
                for offset, chain, anchor in iter_footnotes(model.texel))
    return main, notes


def report(editor):
    main, notes = document_words(editor.root)
    lines = ["Document: %i words" % (main + notes)]
    if notes:
        lines.append("(main text %i, footnotes %i)" % (main, notes))
    if editor.has_selection():
        # the selection is in the current flow: main text or a footnote
        i1, i2 = sorted(editor.selection)
        n = count_words(editor.target.get_text(i1, i2))
        lines.append("Selection: %i words" % n)
    return "\n".join(lines)


def run(frame):
    """Modeless dialog, so the user can keep editing and press Update."""
    dlg = wx.Dialog(frame, title=name)
    label = wx.StaticText(dlg, label=report(frame.editor))
    update = wx.Button(dlg, label="Update")
    close = wx.Button(dlg, wx.ID_CLOSE)

    def on_update(event):
        label.SetLabel(report(frame.editor))
        dlg.Layout()
        dlg.Fit()

    update.Bind(wx.EVT_BUTTON, on_update)
    close.Bind(wx.EVT_BUTTON, lambda event: dlg.Destroy())
    dlg.Bind(wx.EVT_CLOSE, lambda event: dlg.Destroy())
    dlg.SetEscapeId(wx.ID_CLOSE)

    buttons = wx.BoxSizer(wx.HORIZONTAL)
    buttons.Add(update, 0, wx.RIGHT, 5)
    buttons.Add(close)
    sizer = wx.BoxSizer(wx.VERTICAL)
    sizer.Add(label, 0, wx.ALL, 10)
    sizer.Add(buttons, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
    dlg.SetSizerAndFit(sizer)
    dlg.Show()


def test_00():
    "count_words"
    assert count_words("") == 0
    assert count_words("Hallo Welt") == 2
    assert count_words("  Moby-Dick,\tz.B.\nÄpfel ") == 3
    assert count_words("a - b \x0c ― ￼") == 2


def test_01():
    "document_words with footnotes, nested ones counted once"
    from miniword.textmodel.textmodel import TextModel
    from miniword.textmodel.texeltree import T, grouped, ENDMARK
    from miniword.textmodel.submodel import Footnote
    inner = Footnote(grouped([T("tief unten"), ENDMARK]))
    outer = Footnote(grouped([T("eine Fußnote"), inner, T(" mehr"),
                              ENDMARK]))
    model = TextModel()
    model.set_xtexel(grouped([T("Ein kurzer Text"), outer, T(" Ende"),
                              ENDMARK]))
    assert document_words(model) == (4, 5)
