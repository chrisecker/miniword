# Example plugin: Word Count
# Install: copy into the plugins directory (see README.md, "Plugins").
#
# A plugin is a Python module in that directory. A module with a function
# run(frame) appears in the Tools menu under its `name`; frame is the main
# window, frame.editor the editor of the document.
#
# This one counts the words of the document - main text and footnotes -
# and of the selection. A word has at least one letter or digit, so
# placeholders of images or footnote anchors don't count.

import wx

from miniword.textmodel.texeltree import get_text
from miniword.footnotes.footnotes import iter_footnotes

name = "Word Count"


def count_words(text):
    return sum(1 for word in text.split()
               if any(c.isalnum() for c in word))


def run(frame):
    editor = frame.editor
    model = editor.root
    main = count_words(model.get_text())
    notes = sum(count_words(get_text(chain[-1][1].content))
                for offset, chain, anchor in iter_footnotes(model.texel))
    msg = "Document: %i words\n(main text %i, footnotes %i)" \
        % (main + notes, main, notes)
    if editor.has_selection():
        # the selection is in the current flow: main text or a footnote
        i1, i2 = sorted(editor.selection)
        msg += "\nSelection: %i words" \
            % count_words(editor.target.get_text(i1, i2))
    wx.MessageBox(msg, name, wx.OK | wx.ICON_INFORMATION, frame)
