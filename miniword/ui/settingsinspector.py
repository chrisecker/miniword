import wx
from .colours import colours
from .sidepanel import SidePanel
from .design import add_header, add_section, add_row

from .unitentry import LengthInput, EVT_UNIT_CHANGED
from ..core.document import settings_default
from ..core.styles import updated


from ..core.papersizes import PAPER_SIZES
from ..hyphenation import has_patterns
PAPER_CHOICES = list(PAPER_SIZES) + ['custom']

# hyphenation languages (see miniword.hyphenation.LANGUAGES)
LANGUAGE_CHOICES = [('English (US)', 'en-us'), ('German', 'de-1996')]

# header/footer fields: pulldown label and kind (see layout.page.field_text)
FIELD_KINDS = [
    ('(none)',       'none'),
    ('Page number',  'page'),
    ('Page / pages', 'page_pages'),
    ('Title',        'title'),
    ('Author',       'author'),
    ('Date',         'date'),
    ('Chapter',      'chapter'),
    ('Section',      'section'),
    ('Text',         'text'),
]


class SettingsInspector(SidePanel):
    """Inspector panel for document settings (page setup, metadata)."""

    def __init__(self, parent, document):
        SidePanel.__init__(self, parent)
        colours.set(self, 'BackgroundColour', 'BTNFACE')
        self._updating = False
        self.add_model(document)
        self.create()

    def create(self):
        outer = wx.BoxSizer(wx.VERTICAL)
        add_header("SETTINGS", self, outer)

        scrolled = wx.ScrolledWindow(self, style=wx.VSCROLL | wx.BORDER_NONE)
        scrolled.SetScrollRate(0, 10)
        colours.set(scrolled, 'BackgroundColour', 'BTNFACE')
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

        # --- Language: hyphenation ---
        add_section("Language", scrolled, form)
        self.choice_language = wx.Choice(
            scrolled, choices=[l for l, _ in LANGUAGE_CHOICES])
        self.choice_language.Bind(wx.EVT_CHOICE, lambda e: self._set_prop(
            language=LANGUAGE_CHOICES[
                self.choice_language.GetSelection()][1]))
        add_row(form, wx.StaticText(scrolled, label="Language"),
                self.choice_language)
        self.chk_hyphenation = wx.CheckBox(scrolled, label="Hyphenation")
        self.chk_hyphenation.Bind(
            wx.EVT_CHECKBOX, lambda e: self._set_prop(
                hyphenation=self.chk_hyphenation.GetValue()))
        add_row(form, self.chk_hyphenation)

        # --- Header and footer: a pulldown per field, 'Text' shows a
        # text field below it ---
        self.fields = {}  # {setting: (choice, textctrl)}
        for line in ('header', 'footer'):
            add_section(line.title(), scrolled, form)
            for side in ('left', 'center', 'right'):
                key = '%s_%s' % (line, side)
                choice = wx.Choice(scrolled,
                                   choices=[l for l, _ in FIELD_KINDS])
                choice.Bind(wx.EVT_CHOICE,
                            lambda e, k=key: self._on_field_kind(k))
                add_row(form, wx.StaticText(scrolled, label=side.title()),
                        choice)
                text = wx.TextCtrl(scrolled, style=wx.TE_PROCESS_ENTER)
                for binder in wx.EVT_KILL_FOCUS, wx.EVT_TEXT_ENTER:
                    text.Bind(binder,
                              lambda e, k=key: (self._on_field_text(k),
                                                e.Skip()))
                form.Add(text, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 5)
                self.fields[key] = choice, text

        self.chk_first_page = wx.CheckBox(scrolled, label="First page")
        self.chk_first_page.Bind(
            wx.EVT_CHECKBOX, lambda e: self._set_prop(
                header_footer_first_page=self.chk_first_page.GetValue()))
        add_row(form, self.chk_first_page)
        self.chk_mirror = wx.CheckBox(scrolled, label="Mirror on even pages")
        self.chk_mirror.Bind(
            wx.EVT_CHECKBOX, lambda e: self._set_prop(
                header_footer_mirror=self.chk_mirror.GetValue()))
        add_row(form, self.chk_mirror)

        form.AddStretchSpacer()
        padded = wx.BoxSizer(wx.VERTICAL)
        padded.Add(form, 1, wx.EXPAND | wx.ALL, 8)
        scrolled.SetSizer(padded)
        outer.Add(scrolled, 1, wx.EXPAND)
        self.SetSizer(outer)
        self._scrolled = scrolled
        self._refresh()

    def update(self):
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
        languages = [code for _, code in LANGUAGE_CHOICES]
        self.choice_language.SetSelection(  # -1: not in the list
            languages.index(props['language'])
            if props['language'] in languages else -1)
        self.chk_hyphenation.SetValue(props['hyphenation'])
        # without patterns for the language, hyphenation can't work
        patterns = has_patterns(props['language'])
        self.chk_hyphenation.Enable(patterns)
        self.chk_hyphenation.SetToolTip(
            None if patterns else
            "No hyphenation patterns for this language")
        kinds = [kind for _, kind in FIELD_KINDS]
        for key, (choice, text) in self.fields.items():
            kind, value = props[key]
            choice.SetSelection(kinds.index(kind))
            text.SetValue(value)
            text.Show(kind == 'text')
        self.chk_first_page.SetValue(props['header_footer_first_page'])
        self.chk_mirror.SetValue(props['header_footer_mirror'])
        self._relayout()
        self._updating = False

    def _relayout(self):
        self.Layout()
        self._scrolled.FitInside()  # fields shown/hidden: rescroll

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
        self._set_prop(paper_width=event.value)

    def _on_paper_height(self, event):
        self._set_prop(paper_height=event.value)

    def _on_field_kind(self, key):
        choice, text = self.fields[key]
        kind = FIELD_KINDS[choice.GetSelection()][1]
        text.Show(kind == 'text')
        self._relayout()
        self._set_prop(**{key: (kind, text.GetValue())})

    def _on_field_text(self, key):
        choice, text = self.fields[key]
        kind = FIELD_KINDS[choice.GetSelection()][1]
        self._set_prop(**{key: (kind, text.GetValue())})

    def _on_margin(self, key, value_pt):
        self._set_prop(**{key: value_pt})


def _inspector():
    """A SettingsInspector for a new Document, in a frame."""
    from ..core.document import Document
    global _app
    if wx.App.Get() is None:
        _app = wx.App(False)  # keep a reference
    frame = wx.Frame(None, size=(330, 900))
    document = Document()
    return frame, SettingsInspector(frame, document), document


def _choose(choice, label):
    choice.SetSelection(choice.FindString(label))
    event = wx.CommandEvent(wx.wxEVT_CHOICE, choice.GetId())
    event.SetEventObject(choice)
    choice.ProcessWindowEvent(event)


def _enter(textctrl, text):
    textctrl.SetValue(text)
    event = wx.CommandEvent(wx.wxEVT_TEXT_ENTER, textctrl.GetId())
    event.SetEventObject(textctrl)
    textctrl.ProcessWindowEvent(event)


def _check(checkbox, value):
    checkbox.SetValue(value)
    event = wx.CommandEvent(wx.wxEVT_CHECKBOX, checkbox.GetId())
    event.SetEventObject(checkbox)
    event.SetInt(int(value))
    checkbox.ProcessWindowEvent(event)


def test_00():
    "custom paper width and height are set"
    frame, inspector, document = _inspector()
    try:
        _choose(inspector.choice_paper, 'custom')
        inspector.inp_width.text.SetValue("100 mm")
        inspector.inp_width._commit()
        wx.GetApp().ProcessPendingEvents()
        assert abs(document.settings['paper_width'] - 100 * 72 / 25.4) \
            < 1e-9
    finally:
        frame.Destroy()


def test_01():
    "a header/footer field is chosen from a pulldown"
    frame, inspector, document = _inspector()
    try:
        choice, text = inspector.fields['footer_center']
        assert choice.GetStringSelection() == 'Page number'
        assert not text.IsShown()
        _choose(inspector.fields['header_left'][0], 'Chapter')
        assert document.settings['header_left'] == ('chapter', '')
        _choose(choice, '(none)')
        assert document.settings['footer_center'] == ('none', '')
    finally:
        frame.Destroy()


def test_02():
    "'Text' shows a text field; its text is kept when the kind changes"
    frame, inspector, document = _inspector()
    try:
        choice, text = inspector.fields['header_right']
        _choose(choice, 'Text')
        assert text.IsShown()
        _enter(text, 'Firm {page}')
        assert document.settings['header_right'] == ('text', 'Firm {page}')
        _choose(choice, 'Date')
        assert not text.IsShown()
        assert document.settings['header_right'] == ('date', 'Firm {page}')
        _choose(choice, 'Text')
        assert text.GetValue() == 'Firm {page}'
        assert document.settings['header_right'] == ('text', 'Firm {page}')
    finally:
        frame.Destroy()


def test_03():
    "the first page and mirror options are check boxes"
    frame, inspector, document = _inspector()
    try:
        assert inspector.chk_first_page.GetValue()
        assert not inspector.chk_mirror.GetValue()
        _check(inspector.chk_first_page, False)
        _check(inspector.chk_mirror, True)
        assert document.settings['header_footer_first_page'] is False
        assert document.settings['header_footer_mirror'] is True
    finally:
        frame.Destroy()


def test_04():
    "the inspector shows settings changed elsewhere (e.g. undo, loading)"
    frame, inspector, document = _inspector()
    try:
        document.set_setting('footer_left', ('text', 'Draft'))
        document.set_setting('header_footer_mirror', True)
        inspector.update()
        choice, text = inspector.fields['footer_left']
        assert choice.GetStringSelection() == 'Text'
        assert text.IsShown() and text.GetValue() == 'Draft'
        assert inspector.chk_mirror.GetValue()
    finally:
        frame.Destroy()


def test_05():
    "language pulldown and hyphenation check box"
    frame, inspector, document = _inspector()
    try:
        assert inspector.choice_language.GetStringSelection() == \
            'English (US)'
        assert not inspector.chk_hyphenation.GetValue()
        _choose(inspector.choice_language, 'German')
        _check(inspector.chk_hyphenation, True)
        assert document.settings['language'] == 'de-1996'
        assert document.settings['hyphenation'] is True
        document.set_setting('language', 'en-us')
        inspector.update()
        assert inspector.choice_language.GetStringSelection() == \
            'English (US)'
    finally:
        frame.Destroy()


def test_06():
    "Hyphenation is greyed out for a language without patterns"
    frame, inspector, document = _inspector()
    try:
        assert inspector.chk_hyphenation.IsEnabled()
        document.set_setting('language', 'fr')  # e.g. from another file
        inspector.update()
        assert inspector.choice_language.GetSelection() == -1
        assert not inspector.chk_hyphenation.IsEnabled()
        _choose(inspector.choice_language, 'German')
        inspector.update()
        assert inspector.chk_hyphenation.IsEnabled()
    finally:
        frame.Destroy()
