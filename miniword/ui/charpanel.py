# -*- coding: utf-8 -*-

"""
The Characters panel: special characters to insert (prototypes in
dev_charpanel/). One scrolling list in sections - similar characters
(quotes, dashes, spaces) as rows with a name and their shortcut, the
others as a grid -; a pulldown jumps to a section. A search finds
characters by what they look like ("->", "<=", '"', "a", "1/2"), by
words and by their Unicode name. Labels and words are English, to be
localized with the rest of Miniword (the German ones of the first
version: develnotes/charpanel_german.md).

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

# (title, kind, entries); entry: (char, label, look, words) - label and
# words in English, to be translated (a translation gives words of its
# own language, searched as well); look: what the character looks like
# on the keyboard, never translated. A label '': the Unicode name in
# the info line is enough.
GROUPS = [
    ('Quotation marks', 'list', [
        ('„', 'German opening', '" ,,', 'quotation mark low'),
        ('“', 'German closing, English opening', '"', 'quotation mark'),
        ('‚', 'German single opening', "' ,", 'quotation mark single low'),
        ('‘', 'German single closing, English single opening', "'", 'quotation mark single'),
        ('»', 'guillemet', '" >>', 'quotation mark guillemet chevron'),
        ('«', 'guillemet', '" <<', 'quotation mark guillemet chevron'),
        ('›', 'single guillemet', "' >", 'quotation mark guillemet single'),
        ('‹', 'single guillemet', "' <", 'quotation mark guillemet single'),
        ('”', 'English, Polish, Swedish closing', '"', 'quotation mark'),
        ('’', 'English single closing, apostrophe', "'", 'quotation mark apostrophe'),
        ('"', 'straight (typewriter)', '"', 'quotation mark straight typewriter'),
        ("'", 'straight single (typewriter)', "'", 'quotation mark straight typewriter'),
    ]),
    ('Dashes & spaces', 'list', [
        ('–', 'en dash', '- --', 'dash range'),
        ('—', 'em dash', '- ---', 'dash'),
        ('‒', 'figure dash: in numbers', '-', 'dash figure number telephone'),
        (NBHY, 'non-breaking hyphen', '-', 'hyphen non-breaking'),
        (SHY, 'soft hyphen (invisible)', '-', 'hyphen soft shy'),
        ('−', 'minus sign', '-', 'minus'),
        (NBSP, 'non-breaking space', '', 'space non-breaking nbsp'),
        (NNBSP, 'narrow non-breaking space', '', 'space narrow non-breaking'),
        (THIN, 'thin space', '', 'space thin narrow'),
        (FIGSP, 'figure space: as wide as a digit', '', 'space figure digit'),
        (ENSP, 'en space', '', 'space'),
        (EMSP, 'em space', '', 'space'),
        (ZWSP, 'zero width space: may break here', '', 'space zero width break'),
        (WJ, 'word joiner: no break here', '', 'joiner no break'),
        ('·', 'middle dot', '.', 'dot middle'),
        ('…', 'ellipsis', '...', 'ellipsis dots'),
    ]),
    ('Punctuation', 'grid', [
        ('¡', 'inverted exclamation mark', '!', 'spanish exclamation'),
        ('¿', 'inverted question mark', '?', 'spanish question'),
        ('‽', 'interrobang', '?! !?', 'interrobang'),
        ('′', 'prime: minutes, feet', "'", 'prime minutes feet'),
        ('″', 'double prime: seconds, inches', '"', 'prime seconds inches'),
        ('‴', 'triple prime', "'''", 'prime'),
        ('‖', 'double vertical line', '||', 'line double vertical'),
        ('¦', 'broken bar', '|', 'bar broken'),
        ('⁂', 'asterism', '***', 'asterism stars'),
        ('※', 'reference mark', '*', 'reference mark'),
    ]),
    ('Symbols', 'grid', [
        ('§', 'section sign', '', 'section paragraph law'),
        ('¶', 'pilcrow', '', 'pilcrow paragraph'),
        ('©', 'copyright', '(c)', 'copyright'),
        ('®', 'registered', '(r)', 'registered'),
        ('™', 'trade mark', 'tm', 'trademark'),
        ('℗', 'sound recording copyright', '(p)', 'phonogram copyright'),
        ('°', 'degree', 'o', 'degree'),
        ('†', 'dagger: died', '+', 'dagger cross died'),
        ('‡', 'double dagger', '++', 'dagger'),
        ('★', 'star', '*', 'star'), ('☆', 'white star', '*', 'star'),
        ('♥', 'heart', '<3', 'heart love'), ('♦', 'diamond', '', 'diamond cards'),
        ('♣', 'club', '', 'club cards'), ('♠', 'spade', '', 'spade cards'),
        ('☞', 'pointing hand', '', 'hand pointing'), ('✎', 'pencil', '', 'pencil write'),
        ('✉', 'envelope', '', 'envelope mail letter'), ('☎', 'telephone', '', 'telephone phone'),
        ('⚠', 'warning', '!', 'warning caution'),
    ]),
    ('Bullets & boxes', 'grid', [
        ('•', 'bullet', '*', 'bullet dot'),
        ('◦', 'white bullet', 'o', 'bullet'), ('‣', 'triangular bullet', '>', 'bullet triangle'),
        ('⁃', 'hyphen bullet', '-', 'bullet'), ('▪', 'small black square', '', 'square'),
        ('▫', 'small white square', '', 'square'), ('▸', 'small triangle', '>', 'triangle'),
        ('■', 'black square', '', 'square'), ('□', 'white square', '', 'square'),
        ('●', 'black circle', '', 'circle'), ('○', 'white circle', 'o', 'circle'),
        ('◆', 'black diamond', '', 'diamond'), ('◇', 'white diamond', '', 'diamond'),
        ('☐', 'ballot box', '[]', 'box checkbox'),
        ('☑', 'ballot box with check', '[x]', 'box checkbox check'),
        ('☒', 'ballot box with x', '[x]', 'box checkbox cross'),
        ('✓', 'check mark', 'v', 'check ok'),
        ('✗', 'ballot x', 'x', 'cross wrong'),
    ]),
    ('Currency', 'grid', [
        ('€', 'euro', 'e', 'euro'), ('£', 'pound', 'l', 'pound sterling'),
        ('¥', 'yen', 'y', 'yen yuan'), ('¢', 'cent', 'c', 'cent'),
        ('$', 'dollar', 's', 'dollar'), ('₹', 'rupee', '', 'rupee india'),
        ('₽', 'ruble', '', 'ruble russia'), ('₺', 'Turkish lira', '', 'lira turkey'),
        ('₴', 'hryvnia', '', 'hryvnia ukraine'), ('₩', 'won', '', 'won korea'),
        ('₪', 'shekel', '', 'shekel israel'), ('₿', 'bitcoin', 'b', 'bitcoin'),
    ]),
    ('Arrows', 'grid', [
        ('→', 'arrow right', '->', 'arrow right'), ('←', 'arrow left', '<-', 'arrow left'),
        ('↑', 'arrow up', '^', 'arrow up'), ('↓', 'arrow down', 'v', 'arrow down'),
        ('↔', 'arrow left-right', '<->', 'arrow'), ('↕', 'arrow up-down', '', 'arrow'),
        ('⇒', 'double arrow right: implies', '=>', 'arrow double implies'),
        ('⇐', 'double arrow left', '<=', 'arrow double'),
        ('⇔', 'double arrow left-right: if and only if', '<=>', 'arrow double iff'),
        ('⟶', 'long arrow right', '-->', 'arrow long'),
        ('⟹', 'long double arrow right', '==>', 'arrow long double'),
        ('↦', 'maps to', '|->', 'arrow maps'), ('↗', 'arrow up right', '/', 'arrow'),
        ('↘', 'arrow down right', '\\', 'arrow'), ('↩', 'arrow back', '', 'arrow back return'),
        ('↪', 'arrow hook right', '', 'arrow hook'), ('⇄', 'arrows right and left', '', 'arrows'),
        ('⇅', 'arrows up and down', '', 'arrows'),
    ]),
    ('Mathematics', 'grid', [
        ('×', 'multiplication sign', 'x *', 'times multiply'),
        ('÷', 'division sign', '/ :', 'divide'),
        ('⋅', 'dot operator', '. *', 'times dot multiply'),
        ('±', 'plus-minus', '+-', 'plus minus'), ('∓', 'minus-plus', '-+', 'minus plus'),
        ('≤', 'less or equal', '<=', 'less equal'),
        ('≥', 'greater or equal', '>=', 'greater equal'),
        ('≪', 'much less', '<<', 'less much'), ('≫', 'much greater', '>>', 'greater much'),
        ('≠', 'not equal', '!= /=', 'not equal'),
        ('≈', 'almost equal', '~ ~=', 'almost equal approximately'),
        ('≡', 'identical', '===', 'identical'), ('≅', 'congruent', '~=', 'congruent'),
        ('∝', 'proportional', '~', 'proportional'),
        ('∞', 'infinity', 'oo', 'infinity'),
        ('√', 'square root', '', 'root square sqrt'), ('∑', 'sum', '', 'sum sigma'),
        ('∫', 'integral', '', 'integral'), ('∂', 'partial', 'd', 'partial'),
        ('∇', 'nabla', '', 'nabla'), ('∆', 'increment', '', 'delta increment'),
        ('∀', 'for all', '', 'all for'), ('∃', 'there exists', '', 'exists'),
        ('∈', 'element of', '', 'element in'), ('∉', 'not element of', '', 'element not'),
        ('∅', 'empty set', '{}', 'empty set'), ('∩', 'intersection', '', 'intersection'),
        ('∪', 'union', '', 'union'), ('⊂', 'subset', '', 'subset'),
        ('⊆', 'subset or equal', '', 'subset'), ('∧', 'and', '/\\', 'and logical'),
        ('∨', 'or', '\\/', 'or logical'), ('¬', 'not', '!', 'not logical'),
        ('⌊', 'left floor', '', 'floor'), ('⌋', 'right floor', '', 'floor'),
        ('⌈', 'left ceiling', '', 'ceiling'), ('⌉', 'right ceiling', '', 'ceiling'),
        ('ℕ', 'natural numbers', 'N', 'natural numbers'), ('ℤ', 'integers', 'Z', 'integers'),
        ('ℚ', 'rational numbers', 'Q', 'rational'), ('ℝ', 'real numbers', 'R', 'real'),
        ('ℂ', 'complex numbers', 'C', 'complex'), ('µ', 'micro', 'u', 'micro'),
    ]),
    ('Superscript, subscript & fractions', 'grid',
     [(c, '', '^' + n, 'superscript') for c, n in zip('⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿ',
                                                       '0123456789+-=()n')]
     + [(c, '', '_' + n, 'subscript') for c, n in zip('₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎',
                                                       '0123456789+-=()')]
     + [(c, '', '', 'fraction') for c in '½⅓⅔¼¾⅕⅖⅗⅘⅙⅚⅛⅜⅝⅞']),
    ('Units & keys', 'grid', [
        ('℃', 'degree Celsius', 'c', 'degree celsius'),
        ('℉', 'degree Fahrenheit', 'f', 'degree fahrenheit'),
        ('‰', 'per mille', '%o', 'per mille'),
        ('‱', 'per ten thousand', '%oo', 'per'),
        ('⌀', 'diameter', 'o/', 'diameter'),
        ('№', 'numero', 'no', 'number'), ('ℓ', 'litre', 'l', 'litre liter'),
        ('⌘', 'command key (Mac)', '', 'cmd command key mac'),
        ('⌥', 'option key (Mac)', '', 'option alt key mac'),
        ('⇧', 'shift key', '', 'shift key'),
        ('⌫', 'backspace key', '', 'backspace delete key'),
        ('⏎', 'return key', '', 'return enter key'),
        ('↵', 'enter key', '', 'enter return key'),
        ('⇥', 'tab key', '', 'tab key'), ('⎋', 'escape key', '', 'esc escape key'),
    ]),
    ('Greek', 'grid', [(c, '', '', 'greek') for c in 'αβγδεζηθικλμνξοπρστυφχψω'
                                                     'ΓΔΘΛΞΠΣΦΨΩ']),
    ('Accented letters', 'grid', [(c, '', '', '')
                                  for c in 'àáâãäåæçèéêëìíîïñòóôõöøœùúûüýÿß'
                                           'ąćčďęěłńňřśšťůźżž'
                                           'ÀÁÂÄÅÆÇÉÈÊËÑÖØŒÜ']),
]

ENTRIES = {c: (label, look, words) for _, _, entries in GROUPS
           for c, label, look, words in entries}

# the Insert menu's characters with fixed shortcuts: (char, menu label)
BUILTIN = [(NBSP, "Non-breaking &space\tCtrl+Shift+Space"),
           (NBHY, "Non-breaking &hyphen\tCtrl+Shift+-"),
           (SHY, "Soft h&yphen\tCtrl+Alt+-")]

# how invisible characters are shown
DISPLAY = {NBSP: 'NBSP', NNBSP: 'NNBSP', THIN: 'THIN', SHY: 'SHY',
           ENSP: 'ENSP', EMSP: 'EMSP', FIGSP: 'FIGSP', ZWSP: 'ZWSP',
           WJ: 'WJ'}

RECENT = 7  # characters in the Recent row
ITEM_H = 28  # the height of rows and grid cells (DIP)


def simple(text):
    """text in lower case without accents (é -> e, ß -> ss, ½ -> 1/2):
    search words and the search compared alike, in any language."""
    text = unicodedata.normalize('NFKD', text.casefold())
    text = ''.join(x for x in text if not unicodedata.combining(x))
    return text.replace('\u2044', '/')  # fraction slash


def search(query):
    """Characters matching query, the best first: the character, what it
    looks like or a word exactly, then the start of a word, then a part
    of its label or Unicode name. Words: the English ones (later also
    those of a translation)."""
    q = simple(query.strip())
    if not q:
        return []
    ranked = []
    for c, (label, look, words) in ENTRIES.items():
        tokens = look.lower().split() + simple(words).split()
        if q in (c, simple(c)) or q in tokens:
            rank = 0
        elif len(q) >= 2 and any(t.startswith(q) for t in tokens):
            rank = 1
        elif len(q) >= 3 and (q in simple(label)
                              or q in simple(unicodedata.name(c, ''))):
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
        name = ENTRIES.get(c, ('',))[0] or unicodedata.name(c, '')
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
        self.search.SetDescriptiveText("Word or look-alike, e.g. arrow or ->")
        self.search.SetToolTip(
            "Type a word (arrow, euro, dash) or what the character looks "
            "like on the keyboard: -> for →, <= for ≤, 1/2 for ½, \" for "
            "quotation marks, a for à á ä.")
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
        # one height for all: small labels of invisible characters and
        # glyphs from fallback fonts would make rows lower or higher
        item.SetMinSize((-1 if keys is not None else dip(32), dip(ITEM_H)))
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
        sizer.Add(glyph, 0, wx.ALIGN_CENTRE_VERTICAL)
        widgets = [item, glyph]
        if keys is not None:
            text = wx.StaticText(item, label=ENTRIES.get(c, ('',))[0],
                                 style=wx.ST_ELLIPSIZE_END)
            text.SetMinSize((dip(20), -1))  # gives way to the shortcut
            sizer.Add(text, 1, wx.ALIGN_CENTRE_VERTICAL | wx.LEFT, dip(4))
            widgets.append(text)
            if keys:
                shortcut = wx.StaticText(item, label=keys)
                shortcut.SetFont(shortcut.GetFont().Scaled(0.85))
                colours.set(shortcut, 'ForegroundColour', 'GRAYTEXT')
                sizer.Add(shortcut, 0, wx.ALIGN_CENTRE_VERTICAL
                          | wx.LEFT | wx.RIGHT, dip(6))
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
        label = ENTRIES.get(c, ('',))[0]
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
    assert '–' in search('dash') and '→' in search('ARROW')
    assert search('') == []


def test_00b():
    "simple: words and search compared without case and accents, in any "
    "language; decomposed (½ -> 1/2)"
    assert simple('Größer') == 'grosser'
    assert simple('Anführungszeichen') == simple('anfuhrungszeichen')
    assert simple('Ça') == 'ca'
    assert simple('½') == '1/2' and simple('¹') == '1'


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
