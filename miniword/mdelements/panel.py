# -*- coding: utf-8 -*-

"""
The Elements panel (develnotes/panels_concept.md): a palette inserting
the Markdown constructs that have no panel of their own; below, the
element at the cursor, named, and its settings (a code block's
language, expanding and collapsing an HTML block); elsewhere a hint.
"""

import wx
from ..core.utils import get_path
from ..ui.sidepanel import SidePanel
from ..ui.design import make_panel, add_section, flat_button, Card
from ..ui.flatbutton import FlatButton
from ..ui.colours import colours
from ..ui.icons import themed_icon
from . import texel_at
from .rule import Rule, insert_rule
from .checkbox import Checkbox, insert_checkbox
from .code import code_at, insert_code
from .rawhtml import html_at, toggle_html, insert_html
from .tag import Tag, insert_tag
from .colorize import colorizers

# key (icons/element_<key>.svg): caption, name, insert command
ELEMENTS = {'rule': ("Rule", "Horizontal rule", insert_rule),
            'checkbox': ("Task", "Checkbox", insert_checkbox),
            'code': ("Code", "Code block", insert_code),
            'tag': ("Tag", "HTML tag", insert_tag),
            'html': ("HTML", "HTML block", insert_html)}


def element_at(editor, j):
    """The key of the element at the cursor j (see ELEMENTS), or None."""
    code = code_at(editor, j)
    if code:
        return 'code' if code[1].kind == 'code' else 'html'
    if html_at(editor, j):
        return 'html'
    if any(isinstance(node, Tag) and i1 < j < i2
           for i1, i2, node in get_path(editor.target.texel, j)):
        return 'tag'
    if texel_at(editor, j, Checkbox):
        return 'checkbox'
    if texel_at(editor, j, Rule):
        return 'rule'
    return None


def hint(parent, text):
    """A grey hint, wrapped."""
    label = wx.StaticText(parent, label=text)
    colours.set(label, 'ForegroundColour', 'GRAYTEXT')
    label.Wrap(parent.FromDIP(200))
    return label


class ElementsPanel(SidePanel):

    def __init__(self, parent, frame):
        SidePanel.__init__(self, parent)
        self.editor = frame.editor
        self.add_model(self.editor)
        self.create()

    def create(self):
        sizer = make_panel(self, "ELEMENTS")
        dip = self.FromDIP
        add_section("Insert", self, sizer)
        palette = wx.WrapSizer(wx.HORIZONTAL)
        self.buttons = {}
        for key, (caption, name, insert) in ELEMENTS.items():
            # borderless, a large grey icon: as in a ribbon
            button = FlatButton(self, caption, size=(dip(50), dip(50)),
                                icon='element_%s.svg' % key)
            button.icon_size = (26, 26)
            colours.set(button, 'colour_icon', 'IconGrey')
            button.SetFont(button.GetFont().Scaled(0.85))
            button.SetToolTip(name)
            button.Bind(wx.EVT_BUTTON,
                        lambda event, f=insert: f(self.editor))
            palette.Add(button, 0, wx.ALL, dip(2))
            self.buttons[key] = button
        sizer.Add(palette, 0, wx.TOP, dip(5))

        sizer.AddSpacer(dip(16))
        add_section("Configure current element", self, sizer)
        sizer.AddSpacer(dip(4))
        card = self.card = Card(self)
        # inset as the buttons above
        sizer.Add(card, 0, wx.EXPAND | wx.TOP | wx.LEFT | wx.RIGHT, dip(2))
        content = card.sizer
        self.icon = wx.StaticBitmap(card)
        self.current = wx.StaticText(card)
        self.current.SetFont(self.current.GetFont().Bold())
        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(self.icon, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, dip(6))
        row.Add(self.current, 0, wx.ALIGN_CENTER_VERTICAL)
        content.Add(row, 0, wx.BOTTOM, dip(6))
        content.Add(wx.StaticLine(card), 0, wx.EXPAND | wx.BOTTOM, dip(6))

        self.code_section = wx.BoxSizer(wx.HORIZONTAL)
        # the registered languages (colorized), others can be typed
        self.language = wx.ComboBox(
            card, style=wx.CB_DROPDOWN | wx.TE_PROCESS_ENTER)
        self.language.SetHint("e.g. python")
        for event in (wx.EVT_TEXT_ENTER, wx.EVT_COMBOBOX,
                      wx.EVT_KILL_FOCUS):
            self.language.Bind(event, self.on_language)
        self.code_section.Add(wx.StaticText(card, label="Language"), 1,
                              wx.ALIGN_CENTER_VERTICAL)
        self.code_section.Add(self.language, 0, wx.ALIGN_CENTER_VERTICAL)
        content.Add(self.code_section, 0, wx.EXPAND)

        # "Expand" a collapsed block, "Collapse" an expanded one
        self.toggle = flat_button(card, "Expand", size=(-1, dip(24)))
        self.toggle.Bind(wx.EVT_BUTTON, self.on_toggle)
        content.Add(self.toggle, 0, wx.EXPAND)

        self.no_settings = hint(card, "No settings.")
        content.Add(self.no_settings, 0)
        self.hint = hint(card, "Place the cursor at an element to see it "
                         "here, with its settings.")
        content.Add(self.hint, 0)

    def update(self):
        editor = self.editor
        key = element_at(editor, editor.index)
        if key:
            self.current.SetLabel(ELEMENTS[key][1])
            self.icon.SetBitmap(themed_icon('element_%s.svg' % key,
                                            colours.get('IconGrey')))
        else:
            self.current.SetLabel("\u2013")
        self.icon.Show(bool(key))
        code = code_at(editor, editor.index)
        self.code_section.ShowItems(key == 'code')
        if key == 'code':
            names = sorted(colorizers)  # plugins may add some
            if self.language.GetStrings() != names:
                self.language.Set(names)
            self.language.ChangeValue(code[1].lang)
        self.toggle.Show(key == 'html')
        self.toggle.label = "Collapse" if code else "Expand"
        self.toggle.Refresh()
        self.no_settings.Show(key in ('rule', 'checkbox', 'tag'))
        self.hint.Show(key is None)
        self.card.Layout()
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
