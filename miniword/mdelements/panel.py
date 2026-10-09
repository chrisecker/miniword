# -*- coding: utf-8 -*-

"""
The Elements panel (develnotes/panels_concept.md): inserts the Markdown
constructs that have no panel of their own; below, the inspector of the
one at the cursor (a code block's language, expanding and collapsing an
HTML block).
"""

import wx
from ..ui.sidepanel import SidePanel
from ..ui.design import make_panel, add_section, add_row, flat_button
from .rule import insert_rule
from .checkbox import insert_checkbox
from .code import code_at, insert_code
from .rawhtml import html_at, toggle_html, insert_html


class ElementsPanel(SidePanel):

    def __init__(self, parent, frame):
        SidePanel.__init__(self, parent)
        self.frame = frame
        self.editor = frame.editor
        self.add_model(self.editor)
        self.create()

    def create(self):
        sizer = make_panel(self, "ELEMENTS")
        dip = self.FromDIP
        add_section("Insert", self, sizer)
        self.buttons = {}
        for key, label, insert in (
                ('rule', "Horizontal rule", insert_rule),
                ('checkbox', "Checkbox", insert_checkbox),
                ('code', "Code block", insert_code),
                ('html', "HTML…",
                 lambda editor: insert_html(editor, self.frame))):
            button = flat_button(self, label, size=(-1, dip(24)))
            button.Bind(wx.EVT_BUTTON,
                        lambda event, f=insert: f(self.editor))
            add_row(sizer, button)
            self.buttons[key] = button

        self.code_section = wx.BoxSizer(wx.VERTICAL)
        add_section("Code block", self, self.code_section)
        self.language = wx.TextCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.language.SetHint("e.g. python")
        for event in (wx.EVT_TEXT_ENTER, wx.EVT_KILL_FOCUS):
            self.language.Bind(event, self.on_language)
        add_row(self.code_section, wx.StaticText(self, label="Language"),
                self.language)
        sizer.Add(self.code_section, 0, wx.EXPAND)

        self.html_section = wx.BoxSizer(wx.VERTICAL)
        add_section("HTML block", self, self.html_section)
        self.expand = flat_button(self, "Expand", size=(-1, dip(24)))
        self.collapse = flat_button(self, "Collapse", size=(-1, dip(24)))
        for button in (self.expand, self.collapse):
            button.Bind(wx.EVT_BUTTON, self.on_toggle)
            add_row(self.html_section, button)
        sizer.Add(self.html_section, 0, wx.EXPAND)

    def update(self):
        editor = self.editor
        code = code_at(editor, editor.index)
        html = html_at(editor, editor.index)
        kind = code[1].kind if code else None
        self.code_section.ShowItems(kind == 'code')
        if kind == 'code' and not self.language.HasFocus():
            self.language.ChangeValue(code[1].lang)
        self.html_section.ShowItems(bool(html) or kind == 'html')
        self.expand.Show(bool(html))
        self.collapse.Show(kind == 'html')
        self.Layout()

    def on_language(self, event):
        event.Skip()
        editor = self.editor
        index = editor.index
        found = code_at(editor, index)
        lang = self.language.GetValue().strip()
        if found and found[1].lang != lang:
            i, code = found
            editor.set_texel_attributes(editor.abs_idx(i), code, lang=lang)
            editor.set_index(index)  # the cursor stays in the code

    def on_toggle(self, event):
        toggle_html(self.editor, self.editor.index)
