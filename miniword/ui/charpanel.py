# -*- coding: utf-8 -*-

"""
The Characters panel: special characters to insert (prototypes in
dev_charpanel/). One scrolling list in sections - similar characters
(quotes, dashes, spaces) as rows with a name and their shortcut, the
others as a grid -; a pulldown jumps to a section. A search finds
characters by what they look like ("->", "<=", '"', "a", "1/2"), by
German and English words and by their Unicode name.

The characters are shown in the font at the cursor; those it lacks are
grey (Miniword takes them from a fallback font, named in the info line).

Characters can get shortcuts (right click): they are saved in the
configuration (char_shortcuts) and listed in Insert > Characters. The
main window recognizes them itself, with keys_of as the dialog that
records them: menu accelerators (GTK) compare the character a key gives,
so Shift+< (">") would never match "Shift+<".
"""

import unicodedata
import wx
import wx.lib.scrolledpanel as scrolled
from .sidepanel import SidePanel
from .design import make_panel, section_label, Card
from .colours import colours
from ..core.config import get_config
from ..core.fontfinder import resolve_font_path, find_fallback_info

NBSP, NNBSP, THIN, SHY, NBHY = ' ', ' ', ' ', '­', '‑'
ENSP, EMSP, FIGSP, ZWSP, WJ = ' ', ' ', ' ', '​', '⁠'

# (title, kind, entries); entry: (char, label, search words - among
# them what it looks like on the keyboard); a label '': the Unicode
# name is enough (info line)
GROUPS = [
    ('Quotation marks', 'list', [
        ('„', 'German opening', '" ,, anfuehrungszeichen unten deutsch polnisch'),
        ('“', 'German closing, English opening', '" anfuehrungszeichen oben'),
        ('‚', 'German single opening', "' , einfach"),
        ('‘', 'German single closing', "' einfach"),
        ('»', 'guillemet » (German books)', '" >> guillemets chevrons'),
        ('«', 'guillemet « (French)', '" << guillemets chevrons'),
        ('›', 'single guillemet ›', "' > guillemet"),
        ('‹', 'single guillemet ‹', "' < guillemet"),
        ('”', 'English, Polish, Swedish closing', '" quote schwedisch'),
        ('’', 'English single closing, apostrophe', "' apostroph apostrophe"),
        ('"', 'straight (typewriter)', '" gerade'),
        ("'", 'straight single (typewriter)', "' gerade"),
    ]),
    ('Dashes & spaces', 'list', [
        ('–', 'en dash: Gedankenstrich', '- -- gedankenstrich halbgeviert bis'),
        ('—', 'em dash: Geviertstrich', '- --- geviertstrich'),
        ('‒', 'figure dash: in numbers', '- ziffernstrich telefon'),
        (NBHY, 'non-breaking hyphen', '- geschuetzt bindestrich'),
        (SHY, 'soft hyphen (invisible)', '- weich trennstrich shy'),
        ('−', 'minus sign', '- minus'),
        (NBSP, 'non-breaking space', 'geschuetzt leerzeichen nbsp space'),
        (NNBSP, 'narrow non-breaking: z. B.', 'schmal leerzeichen space'),
        (THIN, 'thin space', 'schmal leerzeichen space'),
        (FIGSP, 'figure space: as wide as a digit', 'ziffer leerzeichen space'),
        (ENSP, 'en space', 'halbgeviert leerzeichen space'),
        (EMSP, 'em space', 'geviert leerzeichen space'),
        (ZWSP, 'zero width space: may break here', 'null breite umbruch space'),
        (WJ, 'word joiner: no break here', 'verbinder kein umbruch'),
        ('·', 'middle dot', '. punkt mitte'),
        ('…', 'ellipsis: Auslassungspunkte', '... punkte'),
    ]),
    ('Punctuation', 'grid', [
        ('¡', 'Spanish opening !', '! spanisch'), ('¿', 'Spanish opening ?', '? spanisch'),
        ('‽', 'interrobang', '?! !? interrobang'),
        ('′', 'prime: minutes, feet', "' minuten fuss strich"),
        ('″', 'double prime: seconds, inches', '" sekunden zoll'),
        ('‴', 'triple prime', "''' strich"),
        ('‖', 'double vertical line', '|| doppelstrich'), ('¦', 'broken bar', '| unterbrochen'),
        ('⁂', 'asterism', '*** sternchen'), ('※', 'reference mark', '* hinweis'),
    ]),
    ('Symbols', 'grid', [
        ('§', 'section: Paragraf', 'paragraf paragraph section'),
        ('¶', 'pilcrow: Absatzmarke', 'absatz pilcrow'),
        ('©', 'copyright', '(c) copyright'),
        ('®', 'registered', '(r) registered'),
        ('™', 'trade mark', 'tm trademark marke'),
        ('℗', 'sound recording copyright', '(p) phonogramm'),
        ('°', 'degree: Grad', 'o grad degree'),
        ('†', 'dagger: Kreuz, gestorben', '+ kreuz dagger'),
        ('‡', 'double dagger', '++ dagger'),
        ('★', 'star: Stern', '* stern star'), ('☆', 'white star', '* stern star'),
        ('♥', 'heart: Herz', '<3 herz heart'), ('♦', 'diamond: Karo', 'karo'),
        ('♣', 'club: Kreuz', 'kreuz'), ('♠', 'spade: Pik', 'pik'),
        ('☞', 'pointing hand', 'hand zeiger'), ('✎', 'pencil', 'stift bleistift'),
        ('✉', 'envelope', 'brief mail'), ('☎', 'telephone', 'telefon'),
        ('⚠', 'warning', '! warnung achtung'),
    ]),
    ('Bullets & boxes', 'grid', [
        ('•', 'bullet: Aufzählungspunkt', '* punkt bullet'),
        ('◦', 'white bullet', 'o punkt bullet'), ('‣', 'triangular bullet', '> punkt'),
        ('⁃', 'hyphen bullet', '- punkt'), ('▪', 'small black square', 'quadrat'),
        ('▫', 'small white square', 'quadrat'), ('▸', 'small triangle', '> dreieck'),
        ('■', 'black square', 'quadrat'), ('□', 'white square', 'quadrat'),
        ('●', 'black circle', 'kreis'), ('○', 'white circle', 'o kreis'),
        ('◆', 'black diamond', 'raute'), ('◇', 'white diamond', 'raute'),
        ('☐', 'ballot box: Kästchen', '[] kaestchen checkbox'),
        ('☑', 'ballot box with check', '[x] kaestchen checkbox haken'),
        ('☒', 'ballot box with x', '[x] kaestchen checkbox kreuz'),
        ('✓', 'check mark: Haken', 'v haken check ok'),
        ('✗', 'ballot x: Kreuz', 'x kreuz falsch'),
    ]),
    ('Currency', 'grid', [
        ('€', 'euro', 'e euro'), ('£', 'pound: Pfund', 'l pfund pound'),
        ('¥', 'yen', 'y yen'), ('¢', 'cent', 'c cent'),
        ('$', 'dollar', 's dollar'), ('₹', 'rupee', 'rupie rupee'),
        ('₽', 'ruble', 'rubel ruble'), ('₺', 'Turkish lira', 'lira tuerkisch'),
        ('₴', 'hryvnia', 'hrywnja ukraine'), ('₩', 'won', 'won korea'),
        ('₪', 'shekel', 'schekel israel'), ('₿', 'bitcoin', 'b bitcoin'),
    ]),
    ('Arrows', 'grid', [
        ('→', 'arrow right', '-> pfeil rechts'), ('←', 'arrow left', '<- pfeil links'),
        ('↑', 'arrow up', '^ pfeil oben'), ('↓', 'arrow down', 'v pfeil unten'),
        ('↔', 'arrow left-right', '<-> pfeil'), ('↕', 'arrow up-down', 'pfeil'),
        ('⇒', 'double arrow right: daraus folgt', '=> pfeil folgt'),
        ('⇐', 'double arrow left', '<= pfeil'),
        ('⇔', 'double arrow left-right: genau dann', '<=> pfeil'),
        ('⟶', 'long arrow right', '--> pfeil lang'), ('⟹', 'long double arrow right', '==> pfeil lang'),
        ('↦', 'maps to', '|-> pfeil abbildung'), ('↗', 'arrow up right', '/ pfeil'),
        ('↘', 'arrow down right', '\\ pfeil'), ('↩', 'arrow back', 'pfeil zurueck'),
        ('↪', 'arrow hook right', 'pfeil'), ('⇄', 'arrows right and left', 'pfeil'),
        ('⇅', 'arrows up and down', 'pfeil'),
    ]),
    ('Mathematics', 'grid', [
        ('×', 'times: mal', 'x * mal'), ('÷', 'divided by: geteilt', '/ : geteilt'),
        ('⋅', 'dot operator: mal', '. * mal punkt'),
        ('±', 'plus-minus', '+- plusminus'), ('∓', 'minus-plus', '-+ minusplus'),
        ('≤', 'less or equal', '<= kleiner gleich'),
        ('≥', 'greater or equal', '>= groesser gleich'),
        ('≪', 'much less', '<< viel kleiner'), ('≫', 'much greater', '>> viel groesser'),
        ('≠', 'not equal: ungleich', '!= /= ungleich'),
        ('≈', 'almost equal: ungefähr', '~ ~= ungefaehr'),
        ('≡', 'identical', '=== identisch'), ('≅', 'congruent', '~= kongruent'),
        ('∝', 'proportional', '~ proportional'),
        ('∞', 'infinity: unendlich', 'oo unendlich'),
        ('√', 'square root: Wurzel', 'sqrt wurzel'), ('∑', 'sum: Summe', 'summe sum'),
        ('∫', 'integral', 'integral'), ('∂', 'partial', 'd partiell'),
        ('∇', 'nabla', 'nabla'), ('∆', 'increment: Delta', 'delta differenz'),
        ('∀', 'for all', 'A fuer alle'), ('∃', 'there exists', 'E existiert'),
        ('∈', 'element of', 'in element'), ('∉', 'not element of', '!in element'),
        ('∅', 'empty set', '{} leere menge'), ('∩', 'intersection', 'schnitt'),
        ('∪', 'union', 'vereinigung'), ('⊂', 'subset', 'teilmenge'),
        ('⊆', 'subset or equal', 'teilmenge'), ('∧', 'and', '/\\ und'),
        ('∨', 'or', '\\/ oder'), ('¬', 'not', '! nicht'),
        ('⌊', 'floor left', 'abrunden'), ('⌋', 'floor right', 'abrunden'),
        ('⌈', 'ceiling left', 'aufrunden'), ('⌉', 'ceiling right', 'aufrunden'),
        ('ℕ', 'natural numbers', 'N natuerlich'), ('ℤ', 'integers', 'Z ganz'),
        ('ℚ', 'rationals', 'Q rational'), ('ℝ', 'reals', 'R reell'),
        ('ℂ', 'complex numbers', 'C komplex'), ('µ', 'micro: mikro', 'u mikro micro'),
    ]),
    ('Superscript, subscript & fractions', 'grid',
     [(c, '', '^%s hoch' % n) for c, n in zip('⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿ',
                                               '0123456789+-=()n')]
     + [(c, '', '_%s tief' % n) for c, n in zip('₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎',
                                                 '0123456789+-=()')]
     + [(c, '', 'bruch') for c in '½⅓⅔¼¾⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞']),
    ('Units & keys', 'grid', [
        ('℃', 'degree Celsius', 'grad celsius c'), ('℉', 'degree Fahrenheit', 'grad fahrenheit f'),
        ('‰', 'per mille: Promille', '%o promille'),
        ('‱', 'per ten thousand', '%oo promille'), ('⌀', 'diameter: Durchmesser', 'o/ durchmesser'),
        ('№', 'numero', 'no nummer'), ('ℓ', 'litre', 'l liter'),
        ('⌘', 'command key (Mac)', 'cmd befehl mac taste'),
        ('⌥', 'option key (Mac)', 'opt alt mac taste'),
        ('⇧', 'shift key', 'shift umschalt taste'),
        ('⌫', 'backspace key', 'backspace loeschen taste'),
        ('⏎', 'return key', 'return enter eingabe taste'),
        ('↵', 'enter key', 'enter eingabe taste'),
        ('⇥', 'tab key', 'tab tabulator taste'), ('⎋', 'escape key', 'esc escape taste'),
    ]),
    ('Greek', 'grid', [(c, '', '') for c in 'αβγδεζηθικλμνξοπρστυφχψω'
                                             'ΓΔΘΛΞΠΣΦΨΩ']),
    ('Accented letters', 'grid', [(c, '', '')
                                  for c in 'àáâãäåæçèéêëìíîïñòóôõöøœùúûüýÿß'
                                           'ąćčďęěłńňřśšťůźżž'
                                           'ÀÁÂÄÅÆÇÉÈÊËÑÖØŒÜ']),
]

ENTRIES = {c: (label, words) for _, _, entries in GROUPS
           for c, label, words in entries}

# the Insert menu's characters with fixed shortcuts: (char, menu label)
BUILTIN = [(NBSP, "Non-breaking &space\tCtrl+Shift+Space"),
           (NBHY, "Non-breaking &hyphen\tCtrl+Shift+-"),
           (SHY, "Soft h&yphen\tCtrl+Alt+-")]

# how invisible characters are shown
DISPLAY = {NBSP: 'NBSP', NNBSP: 'NNBSP', THIN: 'THIN', SHY: 'SHY',
           ENSP: 'ENSP', EMSP: 'EMSP', FIGSP: 'FIGSP', ZWSP: 'ZWSP',
           WJ: 'WJ'}

RECENT = 7  # characters in the Recent row


def base_letters(c):
    """c without accents, lower case (é -> e, ß -> ss, ½ -> 1/2)."""
    s = unicodedata.normalize('NFKD', c)
    s = ''.join(x for x in s if not unicodedata.combining(x))
    s = s.replace('⁄', '/')  # fraction slash
    return {'ß': 'ss', 'æ': 'ae', 'œ': 'oe', 'ø': 'o', 'ł': 'l'}.get(
        c.lower(), s.lower())


def search(query):
    """Characters matching query, the best first: what it looks like or
    a search word exactly, then a search word's start, then the label
    or the Unicode name."""
    q = query.strip().lower()
    if not q:
        return []
    ranked = []
    for c, (label, words) in ENTRIES.items():
        tokens = words.lower().split()
        if q == c or q in tokens or q == base_letters(c):
            rank = 0
        elif len(q) >= 2 and any(t.startswith(q) for t in tokens):
            rank = 1
        elif len(q) >= 3 and (q in label.lower()
                              or q in unicodedata.name(c, '').lower()):
            rank = 2
        else:
            continue
        ranked.append((rank, c))
    return [c for _, c in sorted(ranked, key=lambda rc: rc[0])]


_missing = {}  # {font family: the characters of ENTRIES it lacks}


def missing(family):
    """The characters of ENTRIES the font family lacks."""
    if family not in _missing:
        import uharfbuzz as hb
        path = resolve_font_path(family, False, False)
        font = hb.Font(hb.Face(hb.Blob.from_file_path(path)))
        _missing[family] = {c for c in ENTRIES
                            if font.get_nominal_glyph(ord(c)) is None}
    return _missing[family]


# --- shortcuts ---

def normalized(keys):
    """keys (e.g. 'shift+ctrl+2') as wx writes them, or None if wx
    can't read them."""
    entry = wx.AcceleratorEntry()
    if not keys or not entry.FromString(keys):
        return None
    return entry.ToString()


MODIFIER_KEYS = (wx.WXK_CONTROL, wx.WXK_ALT, wx.WXK_SHIFT, wx.WXK_RAW_CONTROL,
                 wx.WXK_WINDOWS_LEFT, wx.WXK_WINDOWS_RIGHT)


def keys_of(event):
    """The keys of a key event (EVT_CHAR_HOOK), e.g. 'Shift+Alt+<', or
    None for a modifier key alone."""
    code = event.GetKeyCode()
    if code in MODIFIER_KEYS:
        return None
    flags = event.GetModifiers()
    accel = (wx.ACCEL_CTRL if flags & wx.MOD_CONTROL else 0) \
        | (wx.ACCEL_ALT if flags & wx.MOD_ALT else 0) \
        | (wx.ACCEL_SHIFT if flags & wx.MOD_SHIFT else 0)
    return wx.AcceleratorEntry(accel, code).ToString()


def user_shortcuts():
    """{char: keys} the user gave characters (configuration)."""
    return dict(get_config().get('char_shortcuts') or {})


def set_user_shortcut(c, keys):
    """Give c the shortcut keys; None: none. Another character with
    these keys loses them."""
    shortcuts = {k: v for k, v in user_shortcuts().items()
                 if k != c and v != keys}
    if keys:
        shortcuts[c] = keys
    get_config().set('char_shortcuts', shortcuts)


def shortcuts():
    """{char: keys} of all characters with a shortcut."""
    result = user_shortcuts()
    for c, label in BUILTIN:
        result[c] = label.split('\t')[1]
    return result


def menu_shortcuts(menubar):
    """{keys: label} of the menu entries with shortcuts."""
    taken = {}

    def visit(menu):
        for item in menu.GetMenuItems():
            if item.GetSubMenu():
                visit(item.GetSubMenu())
            elif '\t' in item.GetItemLabel():
                keys = normalized(item.GetItemLabel().split('\t')[1])
                taken[keys] = item.GetItemLabelText()
    for i in range(menubar.GetMenuCount()):
        visit(menubar.GetMenu(i))
    return taken


def canvas_shortcuts(actions):
    """{keys: action} of a TextCanvas's key actions with Ctrl or Alt
    ({(keycode, ctrl, alt): action}; control characters: Ctrl+letter)."""
    taken = {}
    for (code, ctrl, alt), action in actions.items():
        if not (ctrl or alt):
            continue
        if ctrl and 1 <= code <= 26:
            code = ord('A') + code - 1
        flags = (wx.ACCEL_CTRL if ctrl else 0) | (wx.ACCEL_ALT if alt else 0)
        taken[wx.AcceleratorEntry(flags, code).ToString()] = action
    return taken


def conflict(keys, c, taken):
    """Why c can't have keys, or None: keys need Ctrl or Alt, must not
    be a command's (taken: {keys: name}); another character may lose
    them."""
    entry = wx.AcceleratorEntry()
    if not entry.FromString(keys) \
            or not entry.GetFlags() & (wx.ACCEL_CTRL | wx.ACCEL_ALT):
        return "Use Ctrl or Alt with a key."
    if normalized(keys) in taken:
        return "%s is taken: %s." % (keys, taken[normalized(keys)])
    return None


class ShortcutDialog(wx.Dialog):
    """Records a shortcut for a character: the keys pressed are shown,
    with what they're taken by. result: the keys, '' (remove) or None."""

    def __init__(self, parent, c, keys, taken):
        wx.Dialog.__init__(self, parent, title="Shortcut")
        self.c, self.taken, self.result = c, taken, None
        dip = self.FromDIP
        sizer = wx.BoxSizer(wx.VERTICAL)
        name = ENTRIES.get(c, ('', ''))[0] or unicodedata.name(c, '')
        text = wx.StaticText(self)
        text.SetLabelText("Press the keys for  %s  (%s)." % (
            DISPLAY.get(c, c), name))
        sizer.Add(text, 0, wx.ALL, dip(10))
        self.keys = wx.StaticText(self, label=keys or "–")
        self.keys.SetFont(self.keys.GetFont().Bold().Scaled(1.3))
        sizer.Add(self.keys, 0, wx.LEFT | wx.RIGHT, dip(10))
        self.note = wx.StaticText(self, label='')
        colours.set(self.note, 'ForegroundColour', 'GRAYTEXT')
        sizer.Add(self.note, 0, wx.ALL, dip(10))
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.ok = wx.Button(self, wx.ID_OK)
        self.ok.Disable()
        remove = wx.Button(self, label="Remove")
        remove.Enable(bool(keys))
        buttons.Add(remove, 0, wx.RIGHT, dip(20))
        buttons.Add(wx.Button(self, wx.ID_CANCEL), 0, wx.RIGHT, dip(6))
        buttons.Add(self.ok)
        sizer.Add(buttons, 0, wx.ALIGN_RIGHT | wx.ALL, dip(10))
        self.SetSizerAndFit(sizer)
        self.SetMinSize((dip(320), -1))
        self.Fit()
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        self.ok.Bind(wx.EVT_BUTTON, self.on_ok)
        remove.Bind(wx.EVT_BUTTON, self.on_remove)

    def on_key(self, event):
        keys = keys_of(event)
        if keys is None:
            return
        if not event.GetModifiers() and event.GetKeyCode() in (
                wx.WXK_ESCAPE, wx.WXK_RETURN, wx.WXK_TAB):
            event.Skip()  # the dialog's keys
            return
        self.keys.SetLabel(keys)
        why = conflict(keys, self.c, self.taken)
        self.note.SetLabel(why or "")
        self.ok.Enable(why is None)
        self.Layout()

    def on_ok(self, event):
        self.result = self.keys.GetLabel()
        self.EndModal(wx.ID_OK)

    def on_remove(self, event):
        self.result = ''
        self.EndModal(wx.ID_OK)


class CharPanel(SidePanel):

    def __init__(self, parent, frame):
        SidePanel.__init__(self, parent)
        self.frame = frame
        self.editor = frame.editor
        self.family = None  # the font at the cursor
        self.headers = []  # (title, header label), in order
        self.add_model(self.editor)
        self.create()

    # --- building ---

    def create(self):
        dip = self.FromDIP
        content = make_panel(self, "CHARACTERS")
        self.search = wx.SearchCtrl(self)
        self.search.SetDescriptiveText('Search: "  ->  <=  a  1/2  euro')
        self.search.Bind(wx.EVT_TEXT, self.on_search)
        content.Add(self.search, 0, wx.EXPAND)

        self.recent_box = wx.BoxSizer(wx.HORIZONTAL)
        content.Add(self.recent_box, 0, wx.EXPAND | wx.TOP, dip(10))

        card = Card(self)  # the list: the pulldown above, scrolling
        self.jump = wx.Choice(card, choices=[g[0] for g in GROUPS])
        self.jump.SetSelection(0)
        self.jump.Bind(wx.EVT_CHOICE, self.on_jump)
        card.sizer.Add(self.jump, 0, wx.EXPAND | wx.BOTTOM, dip(6))
        self.list = scrolled.ScrolledPanel(card)
        colours.set(self.list, 'BackgroundColour', 'ButtonNormal')  # the card's
        self.list.Bind(wx.EVT_SCROLLWIN, self.on_scroll)
        self.list.Bind(wx.EVT_MOUSEWHEEL, self.on_scroll)
        card.sizer.Add(self.list, 1, wx.EXPAND)
        content.Add(card, 1, wx.EXPAND | wx.TOP, dip(10))

        info = Card(self)
        self.info = wx.StaticText(info, label='\n')
        info.sizer.Add(self.info, 0, wx.EXPAND)
        content.Add(info, 0, wx.EXPAND | wx.TOP, dip(8))
        self.family = self.family_at_cursor()
        self.fill()

    def fill(self):
        """The list: all sections, or the matches of the search."""
        query = self.search.GetValue().strip()
        self.list.DestroyChildren()
        self.headers = []
        sizer = wx.BoxSizer(wx.VERTICAL)
        if query:
            found = search(query)
            sizer.Add(self.header("%d found" % len(found) if found
                                  else "Nothing found"), 0, wx.EXPAND)
            self.add_chars(sizer, found[:40], 'list')
        else:
            for title, kind, entries in GROUPS:
                header = self.header(title)
                gap = self.FromDIP(10) if self.headers else 0
                self.headers.append((title, header))
                sizer.Add(header, 0, wx.EXPAND | wx.TOP, gap)
                self.add_chars(sizer, [e[0] for e in entries], kind)
        self.list.SetSizer(sizer)
        self.list.SetupScrolling(scroll_x=False, rate_y=10)
        self.update_recent()

    def header(self, title, parent=None):
        label = section_label('', parent or self.list)
        label.SetLabelText(title)  # '&' as it is
        return label

    def add_chars(self, sizer, chars, kind, parent=None):
        """Items for chars: rows (character, label, shortcut) or a grid."""
        parent = parent or self.list
        keys = shortcuts()
        if kind == 'list':
            for c in chars:
                sizer.Add(self.item(parent, c, keys.get(c, '')), 0, wx.EXPAND)
        else:
            grid = wx.WrapSizer()
            for c in chars:
                grid.Add(self.item(parent, c))
            sizer.Add(grid, 0, wx.EXPAND)

    def item(self, parent, c, keys=None, ground='ButtonNormal'):
        """A row (keys: its shortcut, '' none) or, keys None, a grid
        cell, on the colour ground (in the card; else the panel's,
        BTNFACE); grey if the font at the cursor lacks c. Highlighted
        under the mouse; a click inserts c, a right click sets its
        shortcut. Colours by name (colours): light and dark."""
        dip = self.FromDIP
        item = wx.Panel(parent)
        colours.set(item, 'BackgroundColour', ground)
        glyph = wx.StaticText(item, label=DISPLAY.get(c, c),
                              size=(dip(32), -1),
                              style=wx.ALIGN_CENTRE_HORIZONTAL)
        if c in DISPLAY:
            glyph.SetFont(glyph.GetFont().Scaled(0.6))
        else:
            glyph.SetFont(wx.Font(wx.FontInfo(15).FaceName(self.family)))
        if c in missing(self.family):
            colours.set(glyph, 'ForegroundColour', 'GRAYTEXT')
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(glyph, 0, wx.ALIGN_CENTRE_VERTICAL | wx.TOP | wx.BOTTOM,
                  dip(3))
        widgets = [item, glyph]
        if keys is not None:
            text = wx.StaticText(item, label=ENTRIES.get(c, ('', ''))[0],
                                 style=wx.ST_ELLIPSIZE_END)
            text.SetMinSize((dip(20), -1))  # gives way to the shortcut
            sizer.Add(text, 1, wx.ALIGN_CENTRE_VERTICAL | wx.LEFT, dip(4))
            widgets.append(text)
            if keys:
                shortcut = wx.StaticText(item, label=keys)
                shortcut.SetFont(shortcut.GetFont().Scaled(0.85))
                colours.set(shortcut, 'ForegroundColour', 'GRAYTEXT')
                sizer.Add(shortcut, 0, wx.ALIGN_CENTRE_VERTICAL | wx.RIGHT,
                          dip(6))
                widgets.append(shortcut)
        item.SetSizer(sizer)

        def hover(on):
            if not item:
                return
            colours.set(item, 'BackgroundColour',
                        'ButtonHover' if on else ground)
            if on:
                self.show_info(c)
        for w in widgets:
            w.Bind(wx.EVT_LEFT_UP, lambda e: self.insert(c))
            w.Bind(wx.EVT_RIGHT_UP, lambda e: self.shortcut_menu(c))
            w.Bind(wx.EVT_ENTER_WINDOW, lambda e: hover(True))
            w.Bind(wx.EVT_LEAVE_WINDOW, lambda e: hover(False))
        return item

    def update_recent(self):
        self.recent_box.Clear(delete_windows=True)
        recent = get_config().get('recent_chars') or []
        if recent:
            label = self.header("Recent", self)
            self.recent_box.Add(label, 0, wx.ALIGN_CENTRE_VERTICAL | wx.RIGHT,
                                self.FromDIP(8))
            for c in recent[:RECENT]:
                self.recent_box.Add(self.item(self, c, ground='BTNFACE'))
        self.Layout()

    # --- the font at the cursor ---

    def family_at_cursor(self):
        editor = self.editor
        sheet = editor.stylesheet()
        if sheet is None:
            return 'Sans'
        model, j = editor.target, editor.index
        style = model.get_style(max(0, j - 1)) if len(model) else None
        if style is None:
            return 'Sans'
        return sheet.mk_style(model.get_parstyle(j), style)['font_family']

    def update(self):
        family = self.family_at_cursor()
        if family != self.family:
            self.family = family
            self.fill()

    # --- actions ---

    def show_info(self, c):
        label = ENTRIES.get(c, ('', ''))[0]
        lines = ['%s   U+%04X   %s' % (DISPLAY.get(c, c), ord(c),
                                     unicodedata.name(c, '?').lower()),
                 label]
        if c in missing(self.family):
            fallback = find_fallback_info(ord(c))[1] or "no font"
            lines[1] = "Not in %s: shown in %s" % (self.family, fallback)
        self.info.SetLabelText('\n'.join(lines))
        self.info.Wrap(self.GetSize()[0] - self.FromDIP(40))
        self.Layout()

    def insert(self, c):
        self.frame.insert_char(c)
        self.frame.canvas.SetFocus()
        recent = [c] + [r for r in get_config().get('recent_chars') or []
                        if r != c]
        get_config().set('recent_chars', recent[:RECENT])
        self.update_recent()
        self.show_info(c)

    def shortcut_menu(self, c):
        """Right click: set or remove c's shortcut (not a fixed one)."""
        menu = wx.Menu()
        fixed = dict(BUILTIN)
        if c in fixed:
            item = menu.Append(wx.ID_ANY, "Shortcut %s (fixed)"
                               % fixed[c].split('\t')[1])
            item.Enable(False)
        else:
            item = menu.Append(wx.ID_ANY, "Set Shortcut…")
            self.Bind(wx.EVT_MENU, lambda e: self.set_shortcut(c), item)
            if c in user_shortcuts():
                remove = menu.Append(wx.ID_ANY, "Remove Shortcut")
                self.Bind(wx.EVT_MENU, lambda e: self.change_shortcut(c, None),
                          remove)
        self.PopupMenu(menu)
        menu.Destroy()

    def set_shortcut(self, c):
        taken = dict(canvas_shortcuts(self.frame.canvas.actions))
        taken.update(menu_shortcuts(self.frame.GetMenuBar()))
        with ShortcutDialog(self, c, user_shortcuts().get(c), taken) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                self.change_shortcut(c, dlg.result or None)

    def change_shortcut(self, c, keys):
        set_user_shortcut(c, keys)
        from .mainwindow import MainFrame
        for frame in wx.GetTopLevelWindows():  # all windows: their menus
            if isinstance(frame, MainFrame):
                frame.characters_changed()

    def on_search(self, event):
        self.jump.Show(not self.search.GetValue().strip())
        self.fill()
        self.Layout()

    def on_jump(self, event):
        """Scroll the chosen section to the top."""
        header = self.headers[self.jump.GetSelection()][1]
        _, rate = self.list.GetScrollPixelsPerUnit()
        y = header.GetPosition()[1] + self.list.GetViewStart()[1] * rate
        self.list.Scroll(0, y // rate)

    def on_scroll(self, event):
        event.Skip()
        wx.CallAfter(self.follow)

    def follow(self):
        """The pulldown shows the section at the top of the list."""
        if not self or not self.headers:
            return
        current = 0
        for i, (_, header) in enumerate(self.headers):
            if header.GetPosition()[1] <= self.FromDIP(4):
                current = i
        self.jump.SetSelection(current)


def test_00():
    "search by appearance, keyword, base letter and name"
    assert search('->')[0] == '→'
    assert set('≤⇐') <= set(search('<='))
    assert set('„“»«”"') <= set(search('"'))
    assert {'á', 'ä', 'å'} <= set(search('a')) and '„' not in search('a')
    assert search('1/2')[0] == '½'
    assert search('(c)') == ['©']
    assert search('euro')[0] == '€'
    assert '–' in search('gedankenstrich')
    assert search('') == []


def test_01():
    "missing: Liberation Serif lacks the non-breaking hyphen, DejaVu "
    "Serif has it"
    assert NBHY in missing('Liberation Serif')
    assert NBHY not in missing('DejaVu Serif')


def test_02():
    "conflict: Ctrl or Alt needed; a command's keys are refused"
    app = wx.App.Get() or wx.App(False)
    taken = canvas_shortcuts({(2, True, False): 'bold',
                              (wx.WXK_LEFT, False, True): 'dedent',
                              (wx.WXK_LEFT, False, False): 'move_left'})
    assert set(taken) == {normalized('Ctrl+B'), normalized('Alt+Left')}
    assert conflict('Ctrl+B', '„', taken) is not None
    assert conflict('Alt+Left', '„', taken) is not None
    assert conflict('Shift+A', '„', taken) is not None  # no Ctrl, Alt
    assert conflict('Ctrl+Shift+2', '„', taken) is None


def test_03():
    "a character's shortcut: saved, another character loses the keys, "
    "the Insert menu has it; removed again"
    from . import mainwindow
    from ..core import config
    app = wx.App.Get() or wx.App(False)
    saved = config._instance
    config._instance = config.Config.__new__(config.Config)
    config._instance._data = {}
    config._instance.set = lambda key, value: \
        config._instance._data.__setitem__(key, value)
    frame = mainwindow.MainFrame(mainwindow.new_document())
    try:
        panel = frame.char_panel
        panel.change_shortcut('„', 'Ctrl+Shift+2')
        panel.change_shortcut('“', 'Ctrl+Shift+2')  # takes them from „
        assert user_shortcuts() == {'“': 'Ctrl+Shift+2'}
        taken = menu_shortcuts(frame.GetMenuBar())
        assert normalized('Ctrl+Shift+2') not in taken  # a character's
        menu = frame.GetMenuBar().GetMenu(
            frame.GetMenuBar().FindMenu('Insert'))
        sub = next(i.GetSubMenu() for i in menu.GetMenuItems()
                   if i.GetSubMenu())
        labels = [i.GetItemLabel() for i in sub.GetMenuItems()]
        assert any(l.endswith('Ctrl+Shift+2') and '“' in l for l in labels)
        assert not any('\t' in l for l in labels)  # no accelerator (GTK)
        frame.ProcessWindowEvent(wx.CommandEvent(
            wx.wxEVT_MENU, sub.GetMenuItems()[0].GetId()))
        assert '“' in frame.document.textmodel.get_text()
        panel.change_shortcut('“', None)
        assert user_shortcuts() == {}
    finally:
        frame.Destroy()
        app.Yield()
        config._instance = saved
