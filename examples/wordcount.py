# Example plugin: Word Count
# Install: copy to ~/.miniword/plugins/wordcount.py

import wx

name = "Word Count…"


def run(app):
    text = app.document.textmodel.get_text()
    n_chars = len(text)
    n_words = len(text.split())
    n_lines = text.count('\n') + 1

    msg = f"Characters: {n_chars}\nWords:      {n_words}\nLines:      {n_lines}"
    wx.MessageBox(msg, "Word Count", wx.OK | wx.ICON_INFORMATION, app)
