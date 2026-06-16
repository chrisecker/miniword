# -*- coding: utf-8 -*-
import wx
from .sidepanel import SidePanel
from .design import make_panel, add_section, flat_button

NUMBERING_CHOICES = ["Numbers", "Letters", "Roman", "Custom Label"]
NUMBERING_KEYS    = ["numbers", "letters", "roman", "custom"]


class LinksPanel(SidePanel):

    def __init__(self, parent, editor, document):
        SidePanel.__init__(self, parent)
        self.editor   = editor
        self.document = document
        self.add_model(editor)
        self.create()

    def create(self):
        dip     = self.FromDIP
        content = make_panel(self, "LINKS")

        add_section("Footnotes", self, content)
        content.AddSpacer(dip(6))

        btn_insert = flat_button(self, "Insert", size=(-1, dip(24)))
        content.Add(btn_insert, 0, wx.EXPAND | wx.BOTTOM, dip(8))

        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(wx.StaticText(self, label="Numbering"), 0,
                wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, dip(6))
        self.numbering = wx.Choice(self, choices=NUMBERING_CHOICES)
        row.Add(self.numbering, 1, wx.ALIGN_CENTER_VERTICAL)
        content.Add(row, 0, wx.EXPAND | wx.BOTTOM, dip(4))

        lbl_row = wx.BoxSizer(wx.HORIZONTAL)
        lbl_row.Add(wx.StaticText(self, label="Label"), 0,
                    wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, dip(6))
        self.label_ctrl = wx.TextCtrl(self)
        self.label_ctrl.SetHint("e.g. *")
        lbl_row.Add(self.label_ctrl, 1, wx.ALIGN_CENTER_VERTICAL)
        content.Add(lbl_row, 0, wx.EXPAND | wx.BOTTOM, dip(4))

        btn_insert.Bind(wx.EVT_BUTTON,     self.on_insert)
        self.numbering.Bind(wx.EVT_CHOICE, self.on_numbering_changed)
        self.label_ctrl.Bind(wx.EVT_TEXT,  self.on_label_changed)

        self.update()

    def active_footnote(self):
        editor = self.editor
        if getattr(editor, 'flow', 0) != 1:
            return None
        return getattr(editor, 'target', None)

    def get_texel(self, fn):
        from ..textmodel.submodel import Footnote
        from ..textmodel.utils import iter_leafes
        for i1, i2, t in iter_leafes(fn.root.texel, 0, True):
            if isinstance(t, Footnote) and i1 == fn.anchor:
                return t
        return None

    def update(self):
        fn     = self.active_footnote()
        has_fn = fn is not None
        self.numbering.Enable(has_fn)
        if not has_fn:
            self.label_ctrl.Enable(False)
            return
        texel = self.get_texel(fn)
        if texel is None:
            return
        if texel.label is not None:
            self.numbering.SetSelection(NUMBERING_KEYS.index('custom'))
            self.label_ctrl.Enable(True)
            self.label_ctrl.ChangeValue(texel.label)
        else:
            key = texel.numbering
            idx = NUMBERING_KEYS.index(key) if key in NUMBERING_KEYS else 0
            self.numbering.SetSelection(idx)
            self.label_ctrl.Enable(False)
            self.label_ctrl.ChangeValue('')

    def on_insert(self, event=None):
        from ..textmodel.submodel import Footnote
        from ..textmodel.texeltree import ENDMARK, length
        from ..textmodel.utils import iter_leafes
        editor = self.editor
        with editor.atomic():
            editor.remove()
            anchor = editor.abs_idx(editor.index)
            editor.insert_texel(Footnote(ENDMARK))
        fn_offset = 0
        for i1, i2, texel in iter_leafes(editor.root.texel, 0, True):
            if not isinstance(texel, Footnote):
                continue
            if i1 == anchor:
                editor.switch_target(1, fn_offset)
                editor.set_index(editor.local_idx(fn_offset))
                if editor.canvas:
                    wx.CallAfter(editor.canvas.adjust_viewport)
                break
            fn_offset += length(texel.content)

    def on_numbering_changed(self, event=None):
        fn = self.active_footnote()
        if fn is None:
            return
        key = NUMBERING_KEYS[self.numbering.GetSelection()]
        if key == 'custom':
            self.label_ctrl.Enable(True)
            self.label_ctrl.SetFocus()
        else:
            self.label_ctrl.Enable(False)
            self.label_ctrl.ChangeValue('')
            fn.update_host(lambda t: t.set_numbering(key).set_label(None))

    def on_label_changed(self, event=None):
        fn = self.active_footnote()
        if fn is None or not self.label_ctrl.IsEnabled():
            return
        text = self.label_ctrl.GetValue()
        fn.update_host(lambda t: t.set_label(text))
