"""Spell checking, page by page and only in idle time.

Each page keeps the errors of the words touching it in page.spelling,
by flow ({0: main text, 1: its footnotes}), relative to the page's start
in the flow; None: not checked. The footnote flow is checked as a model
of the footnotes' contents in their order (see footnote_flow). A rebuilt page is a new
object and so unchecked, an unchanged page keeps its result. A word
across a page boundary is checked by both pages (the word cache makes
the second time cheap). The canvas draws the errors of the visible
pages (canvas.show_spelling), each page only its part, except the word
being typed; a rebuilt page has none until the next idle check. Code
is not checked: code blocks (Code containers) and text in a monospace
font (inline code).

Dictionary: enchant if installed (see develnotes/spellcheck_concept.md
for the backends still to decide). Without one nothing is marked.

Measuring: DEBUG prints the times of each idle step that checked
something; measure(path) checks all pages of a document without window:

    python -m miniword.texteditor.spellcheck test/moby.txl
"""

import re
import time
import wx
from ..core.document import settings_default
from ..textmodel.texeltree import EMPTYSTYLE, length
from ..textmodel.utils import iter_leafes

WORD = re.compile(r"\w+")  # words with digits or _ are skipped
MARGIN = 50     # chars read beyond the page, for words across its edges
DEBUG = False   # print the times of the idle steps
MONO = {'courier', 'courier new', 'monospace', 'consolas', 'menlo',
        'dejavu sans mono'}  # fonts of inline code


def find_dictionary(language):
    """An enchant dictionary for a language setting ('en-us',
    'de-1996'), None if there is none."""
    try:
        import enchant
    except ImportError:
        return None
    lang, _, region = language.partition('-')
    tags = enchant.list_languages()
    wanted = '%s_%s' % (lang, region.upper())
    if wanted not in tags:
        wanted = next((tag for tag in tags
                       if tag == lang or tag.startswith(lang + '_')), None)
    return enchant.Dict(wanted) if wanted else None


def iter_code(texel, a, b, offset=0):
    """(i1, i2) of the code in texel within [a, b): Code containers and
    text in a monospace font, also in other containers (table cells)."""
    for i1, i2, leaf in iter_leafes(texel, a - offset):
        i1, i2 = i1 + offset, i2 + offset
        if i1 >= b:
            break
        if getattr(leaf, 'txl_name', None) == 'code':
            yield i1, i2
        elif leaf.is_container:
            j = i1
            for child in leaf.childs:
                yield from iter_code(child, max(a, j), b, j)
                j += length(child)
        elif getattr(leaf, 'style', EMPTYSTYLE).get(
                'font_family', '').lower() in MONO:
            yield i1, i2


def page_items(layout):
    """Per page its items by flow: [(j1, j2, x, y, page), (j1, j2, x, y,
    footnote box) or None (no footnotes)], as layout.iter_boxes gives
    them."""
    k1 = 0
    for item in layout.iter_pages():
        footnotes = None
        if item[4].footnotebox is not None:
            x, y, box = item[4].footnotebox
            footnotes = k1, k1 + len(box), item[2] + x, item[3] + y, box
            k1 += len(box)
        yield [item, footnotes]


def visible_pages(canvas):
    """page_items of the pages in the viewport of canvas."""
    x1, y1, x2, y2 = canvas.get_viewport().items()
    return [items for items in page_items(canvas.layout)
            if items[0][3] < y2 and items[0][3] + items[0][4].height > y1]


def squiggles(canvas):
    """(item, i1, i2): the errors of the visible checked pages, absolute
    in their flow, with the item (page or footnote box, see page_items)
    they are drawn in; not the word being typed (the cursor at its end).
    A page draws only its part of an error."""
    editor = canvas.editor
    cursor = None
    if editor is not None:
        cursor = editor.flow, editor.abs_idx(editor.index)
    for items in visible_pages(canvas):
        for flow, errors in (items[0][4].spelling or {}).items():
            j1 = items[flow][0]
            for i1, i2 in errors:
                if (flow, j1 + i2) != cursor:
                    yield items[flow], j1 + i1, j1 + i2


def footnote_flow(model):
    """The footnote flow of model as a model of its own: the contents of
    the footnotes in their order (see iter_footnotes)."""
    from ..textmodel.textmodel import TextModel
    from ..textmodel.texeltree import Group
    from ..footnotes.footnotes import iter_footnotes
    flow = TextModel('')
    contents = [chain[-1][1].content
                for _, chain, _ in iter_footnotes(model.texel)]
    if contents:
        flow.texel = Group(contents)
    return flow


class SpellChecker:
    budget = 0.005  # s of checking per idle step

    def __init__(self, canvas=None):
        self.canvas = canvas
        self.words = {}         # (language, word) -> correct?
        self.dictionaries = {}  # language -> dictionary or None
        self.footnotes = None, None  # (texel, its footnote_flow)
        self.stats = dict(pages=0, words=0, lookups=0, check=0.0)
        if canvas is not None:
            canvas.Bind(wx.EVT_IDLE, self.on_idle)

    def dictionary(self, language):
        if language not in self.dictionaries:
            self.dictionaries[language] = find_dictionary(language)
        return self.dictionaries[language]

    def correct(self, language, word):
        key = language, word
        if key not in self.words:
            d = self.dictionary(language)
            self.words[key] = d is None or d.check(word)
            self.stats['lookups'] += 1
        return self.words[key]

    def check(self, model, language, j1, j2):
        """The errors [(i1, i2)] of the words touching [j1, j2),
        relative to j1."""
        a = max(0, j1 - MARGIN)
        b = min(len(model), j2 + MARGIN)
        text = model.get_text(a, b)
        code = list(iter_code(model.get_xtexel(), a, b))
        errors = []
        for m in WORD.finditer(text):
            w1, w2 = a + m.start(), a + m.end()
            word = m.group()
            if w2 <= j1 or w1 >= j2 or len(word) < 2 or word.isupper() \
                    or not word.isalpha() \
                    or any(c1 <= w1 < c2 for c1, c2 in code):
                continue
            self.stats['words'] += 1
            if not self.correct(language, word):
                errors.append((w1 - j1, w2 - j1))
        self.stats['pages'] += 1
        return errors

    def footnote_flow(self, model):
        """footnote_flow(model), kept while model's text is the same."""
        if self.footnotes[0] is not model.texel:
            self.footnotes = model.texel, footnote_flow(model)
        return self.footnotes[1]

    def check_pages(self, model, language, pages, deadline=None):
        """Check the unchecked pages (see page_items) until deadline (a
        perf_counter time). Returns (done, found): done is False if time
        ran out first, found True if errors were found."""
        found = False
        for item, footnotes in pages:
            page = item[4]
            if page.spelling is None:
                if deadline is not None and time.perf_counter() > deadline:
                    return False, found
                t0 = time.perf_counter()
                page.spelling = {0: self.check(model, language,
                                               item[0], item[1])}
                if footnotes is not None:
                    page.spelling[1] = self.check(self.footnote_flow(model),
                                                  language, footnotes[0],
                                                  footnotes[1])
                self.stats['check'] += time.perf_counter() - t0
                found = found or any(page.spelling.values())
        return True, found

    # --- the canvas

    def enable(self, enabled):
        self.canvas.show_spelling = enabled
        self.canvas.refresh()

    def on_idle(self, event):
        event.Skip()
        canvas = self.canvas
        if not canvas.show_spelling or canvas.builder.generator is not None:
            return  # the layout first
        t0 = time.perf_counter()
        checked = self.stats['pages']
        language = canvas.builder.settings.get(
            'language', settings_default['language'])
        done, found = self.check_pages(canvas.model, language,
                                       visible_pages(canvas),
                                       t0 + self.budget)
        if not done:
            event.RequestMore()
        if found:
            canvas.refresh()
        if DEBUG and self.stats['pages'] > checked:
            print("spell: %d pages checked in %.2f ms"
                  % (self.stats['pages'] - checked,
                     (time.perf_counter() - t0) * 1000))


def measure(path):
    """Check all pages of the document at path, print the times."""
    from ..io.importexport import open_file
    from ..layout.pagebuilder import PageBuilder
    from ..layout.rowfactory import Factory
    from ..layout.cairodevice import CairoDevice
    app = wx.App.Get() or wx.App(False)  # kept alive until the end
    doc = open_file(path)
    builder = PageBuilder(doc.textmodel, Factory(doc.basestyles,
                                                 device=CairoDevice()))
    builder.settings = doc.settings
    builder.rebuild()
    builder.assure_finished()
    language = doc.settings.get('language', settings_default['language'])
    pages = list(page_items(builder.layout))
    checker = SpellChecker()
    print("dictionary for %r: %s" % (language, checker.dictionary(language)))
    for run in ('cold', 'warm'):
        for item, footnotes in pages:
            item[4].spelling = None
        checker.stats = dict(pages=0, words=0, lookups=0, check=0.0)
        checker.check_pages(doc.textmodel, language, pages)
        s = checker.stats
        errors = sum(len(errors) for item, footnotes in pages
                     for errors in item[4].spelling.values())
        print("%s: %d pages, %d words, %d lookups, %d errors, "
              "%.1f ms total, %.2f ms per page"
              % (run, s['pages'], s['words'], s['lookups'], errors,
                 s['check'] * 1000, s['check'] * 1000 / max(1, s['pages'])))


# --- tests

class FakeDictionary:
    def check(self, word):
        return word.lower() != 'teh'


def fake_checker():
    checker = SpellChecker()
    checker.dictionaries['en-us'] = FakeDictionary()
    return checker


def test_00():
    "errors relative to the page; words touching the page"
    from ..textmodel.textmodel import TextModel
    model = TextModel('teh cat and teh dog')
    checker = fake_checker()
    assert checker.check(model, 'en-us', 0, len(model)) == [(0, 3), (12, 15)]
    # a page starting within the second 'teh': it touches it
    assert checker.check(model, 'en-us', 13, len(model)) == [(-1, 2)]
    # a page ending before it: only the first
    assert checker.check(model, 'en-us', 0, 12) == [(0, 3)]


def test_01():
    "near the document start and end (page within the margin)"
    from ..textmodel.textmodel import TextModel
    model = TextModel('teh')
    checker = fake_checker()
    assert checker.check(model, 'en-us', 0, 1) == [(0, 3)]
    assert checker.check(model, 'en-us', 2, 3) == [(-2, 1)]
    assert checker.check(model, 'en-us', 0, 4) == [(0, 3)]  # end marker


def test_02():
    "the word cache asks the dictionary once per word"
    from ..textmodel.textmodel import TextModel
    model = TextModel('teh teh teh cat cat')
    checker = fake_checker()
    checker.check(model, 'en-us', 0, len(model))
    assert checker.stats['words'] == 5 and checker.stats['lookups'] == 2


def test_04():
    "squiggles: the checked visible pages, absolute, not the typed word"
    from types import SimpleNamespace as NS
    from ..layout.rect import Rect
    notes = type('Box', (), {'__len__': lambda self: 10})()
    pages = [(0, 10, NS(height=100, footnotebox=None,
                        spelling={0: [(-1, 2), (5, 8)]})),
             (10, 20, NS(height=100, footnotebox=(5, 80, notes),
                         spelling={0: [(-11, -8), (8, 12)], 1: [(0, 3)]})),
             (20, 30, NS(height=100, footnotebox=None, spelling=None)),
             (30, 40, NS(height=100, footnotebox=None,
                         spelling={0: [(0, 3)]}))]
    editor = NS(flow=0, index=22, abs_idx=lambda i: i)
    canvas = NS(editor=editor, get_viewport=lambda: Rect(0, 0, 100, 250),
                layout=NS(iter_pages=lambda: [
                    (j1, j2, 0, k * 100, page)
                    for k, (j1, j2, page) in enumerate(pages)]))
    # page 4 not visible, page 3 unchecked, (18, 22) is being typed
    found = [(item[:4], i1, i2) for item, i1, i2 in squiggles(canvas)]
    assert found == [((0, 10, 0, 0), -1, 2), ((0, 10, 0, 0), 5, 8),
                     ((10, 20, 0, 100), -1, 2),
                     ((0, 10, 5, 180), 0, 3)], found  # in the footnotes
    editor.flow, editor.index = 1, 3  # typed in the footnote
    assert len(list(squiggles(canvas))) == 4


def test_05():
    "not checked: code blocks, monospace text (also in a table)"
    from ..textmodel.textmodel import TextModel
    from ..textmodel.texeltree import Text, NL, grouped, EMPTYSTYLE
    from ..textmodel.styles import Style
    from ..mdelements.code import Code
    from ..tables.tables import Table
    checker = fake_checker()
    mono = Style(font_family='Courier New')
    model = TextModel('')
    model.texel = grouped([
        Text('teh '), Text('teh', mono), NL,
        Code.from_text('teh teh'), NL,
        Table((Text('teh', mono), EMPTYSTYLE), (Text('teh'), EMPTYSTYLE),
              ncols=2), NL,
        Text('teh'), NL])
    text = model.get_text()
    found = [text[i1:i2] for i1, i2 in
             checker.check(model, 'en-us', 0, len(model))]
    # the first, the plain cell, the last: at the right places
    assert found == ['teh'] * 3, found


def test_03():
    "skipped: single letters, all capitals, digits; no dictionary"
    from ..textmodel.textmodel import TextModel
    model = TextModel('a TEH teh2x')
    checker = fake_checker()
    assert checker.check(model, 'en-us', 0, len(model)) == []
    assert checker.stats['words'] == 0
    checker = SpellChecker()
    checker.dictionaries['en-us'] = None
    assert checker.check(TextModel('teh'), 'en-us', 0, 3) == []


def test_06():
    "footnotes: checked in the footnote flow, by the page's part of it"
    from types import SimpleNamespace as NS
    from ..textmodel.textmodel import TextModel
    from ..textmodel.texeltree import Text, NL, ENDMARK, grouped
    from ..textmodel.submodel import Footnote
    checker = fake_checker()
    first = Footnote(grouped([Text('a teh'), ENDMARK]))
    second = Footnote(grouped([Text('teh b'), ENDMARK]))
    model = TextModel('')
    model.texel = grouped([Text('cat'), first, Text(' dog'), second, NL])
    assert footnote_flow(model).get_text() == 'a teh\nteh b\n'
    assert checker.footnote_flow(model) is checker.footnote_flow(model)
    notes = type('Box', (), {'__len__': lambda self: 6})()
    one = NS(spelling=None, footnotebox=(0, 0, notes))
    two = NS(spelling=None, footnotebox=(0, 0, notes))
    pages = [[(0, 4, 0, 0, one), (0, 6, 0, 0, notes)],
             [(4, 10, 0, 0, two), (6, 12, 0, 0, notes)]]
    assert checker.check_pages(model, 'en-us', pages) == (True, True)
    assert one.spelling == {0: [], 1: [(2, 5)]}
    assert two.spelling == {0: [], 1: [(0, 3)]}


if __name__ == '__main__':
    import sys
    measure(sys.argv[1])
