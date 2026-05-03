import wx
from ..textmodel.viewbase import ViewBase
from .design import BAR_BG, add_header, add_section, add_row

from .unitentry import LengthInput, EVT_UNIT_CHANGED
from ..core.document import settings_default
from ..core.styles import updated


from ..core.papersizes import PAPER_SIZES
PAPER_CHOICES = list(PAPER_SIZES) + ['custom']


class SettingsInspector(wx.Panel, ViewBase):
    """Inspector panel for document settings (page setup, metadata)."""

    def __init__(self, parent, document):
        wx.Panel.__init__(self, parent)
        ViewBase.__init__(self)
        self.SetBackgroundColour(BAR_BG)
        self._updating = False
        self.model = document
        self.create()

    def create(self):
        outer = wx.BoxSizer(wx.VERTICAL)
        add_header("SETTINGS", self, outer)

        scrolled = wx.ScrolledWindow(self, style=wx.VSCROLL | wx.BORDER_NONE)
        scrolled.SetScrollRate(0, 10)
        scrolled.SetBackgroundColour(BAR_BG)
        form = wx.BoxSizer(wx.VERTICAL)

        # --- Document Info ---
        add_section("Document Info", scrolled, form)

        self.txt_title = wx.TextCtrl(scrolled, style=wx.TE_PROCESS_ENTER)
        self.txt_title.Bind(wx.EVT_KILL_FOCUS, self._on_title)
        self.txt_title.Bind(wx.EVT_TEXT_ENTER, self._on_title)
        form.Add(wx.StaticText(scrolled, label="Title"),
                 0, wx.LEFT | wx.TOP, 5)
        form.Add(self.txt_title, 0, wx.EXPAND | wx.ALL, 5)

        self.txt_author = wx.TextCtrl(scrolled, style=wx.TE_PROCESS_ENTER)
        self.txt_author.Bind(wx.EVT_KILL_FOCUS, self._on_author)
        self.txt_author.Bind(wx.EVT_TEXT_ENTER, self._on_author)
        form.Add(wx.StaticText(scrolled, label="Author"),
                 0, wx.LEFT | wx.TOP, 5)
        form.Add(self.txt_author, 0, wx.EXPAND | wx.ALL, 5)

        # --- Page ---
        add_section("Page", scrolled, form)

        lbl = wx.StaticText(scrolled, label="Paper")
        self.choice_paper = wx.Choice(scrolled, choices=PAPER_CHOICES)
        self.choice_paper.Bind(wx.EVT_CHOICE, self._on_paper)
        add_row(form, lbl, self.choice_paper)

        self._lbl_width = wx.StaticText(scrolled, label="Width")
        self.inp_width = LengthInput(scrolled, category="layout")
        self.inp_width.Bind(EVT_UNIT_CHANGED, self._on_paper_width)
        add_row(form, self._lbl_width, self.inp_width)

        self._lbl_height = wx.StaticText(scrolled, label="Height")
        self.inp_height = LengthInput(scrolled, category="layout")
        self.inp_height.Bind(EVT_UNIT_CHANGED, self._on_paper_height)
        add_row(form, self._lbl_height, self.inp_height)

        # --- Margins ---
        add_section("Margins", scrolled, form)

        self._margin_inputs = {}
        for key, label_text in [
            ('margin_top',    'Top'),
            ('margin_bottom', 'Bottom'),
            ('margin_left',   'Left'),
            ('margin_right',  'Right'),
        ]:
            lbl = wx.StaticText(scrolled, label=label_text)
            inp = LengthInput(scrolled, category="layout")
            self._margin_inputs[key] = inp
            inp.Bind(EVT_UNIT_CHANGED,
                     lambda e, k=key: self._on_margin(k, e.value))
            add_row(form, lbl, inp)

        form.AddStretchSpacer()
        padded = wx.BoxSizer(wx.VERTICAL)
        padded.Add(form, 1, wx.EXPAND | wx.ALL, 8)
        scrolled.SetSizer(padded)
        outer.Add(scrolled, 1, wx.EXPAND)
        self.SetSizer(outer)
        self._refresh()

    def dpi_changed(self):
        self.DestroyChildren()
        self.create()
        self.Layout()

    # ------------------------------------------------------------------
    # ViewBase
    # ------------------------------------------------------------------

    def setting_changed(self, doc, name, old):
        self._refresh()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_props(self):
        return updated(settings_default, self.model.settings)

    def _set_prop(self, **kwargs):
        if self._updating:
            return
        for name, value in kwargs.items():
            self.model.set_setting(name, value)

    def _refresh(self):
        self._updating = True
        props = self._get_props()
        self.txt_title.SetValue(props['title'])
        self.txt_author.SetValue(props['author'])
        paper = props['paper']
        idx = PAPER_CHOICES.index(paper) if paper in PAPER_CHOICES else 0
        self.choice_paper.SetSelection(idx)
        self.inp_width.SetValue(props['paper_width'])
        self.inp_height.SetValue(props['paper_height'])
        for key, inp in self._margin_inputs.items():
            inp.SetValue(props[key])
        self._show_custom(paper == 'custom')
        self._updating = False

    def _show_custom(self, visible):
        for w in (self._lbl_width, self.inp_width,
                  self._lbl_height, self.inp_height):
            w.Show(visible)
        self.Layout()

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_title(self, event):
        self._set_prop(title=self.txt_title.GetValue())
        event.Skip()

    def _on_author(self, event):
        self._set_prop(author=self.txt_author.GetValue())
        event.Skip()

    def _on_paper(self, event):
        paper = PAPER_CHOICES[self.choice_paper.GetSelection()]
        self._show_custom(paper == 'custom')
        self._set_prop(paper=paper)

    def _on_paper_width(self, event):
        self._set_prop(paper_width=event.value_pt)

    def _on_paper_height(self, event):
        self._set_prop(paper_height=event.value_pt)

    def _on_margin(self, key, value_pt):
        self._set_prop(**{key: value_pt})
