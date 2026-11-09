"""Spell checking, page by page and only in idle time.

Each page keeps the errors of the words touching it in page.spelling,
relative to the page start; None: not checked. A rebuilt page is a new
object and so unchecked, an unchanged page keeps its result. A word
across a page boundary is checked by both pages (the word cache makes
the second time cheap). The visible errors go to canvas.squiggles,
except the word being typed.

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
from ..textmodel.viewbase import ViewBase

WORD = re.compile(r"\w+")  # words with digits or _ are skipped
MARGIN = 50     # chars read beyond the page, for words across its edges
DEBUG = False   # print the times of the idle steps


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


class SpellChecker(ViewBase):
    enabled = False
    budget = 0.005  # s of checking per idle step

    def __init__(self, canvas=None):
        ViewBase.__init__(self)
        self.canvas = canvas
        self.words = {}         # (language, word) -> correct?
        self.dictionaries = {}  # language -> dictionary or None
        self.stats = dict(pages=0, words=0, lookups=0, check=0.0)
        if canvas is not None:
            canvas.Bind(wx.EVT_IDLE, self.on_idle)
            canvas.Bind(wx.EVT_WINDOW_DESTROY, self.on_destroy)
            self.add_model(canvas.model)

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
        errors = []
        for m in WORD.finditer(text):
            w1, w2 = a + m.start(), a + m.end()
            word = m.group()
            if w2 <= j1 or w1 >= j2 or len(word) < 2 or word.isupper() \
                    or not word.isalpha():
                continue
            self.stats['words'] += 1
            if not self.correct(language, word):
                errors.append((w1 - j1, w2 - j1))
        self.stats['pages'] += 1
        return errors

    def check_pages(self, model, language, pages, deadline=None):
        """Check the unchecked pages [(j1, j2, page)] until deadline (a
        perf_counter time); False if time ran out first."""
        for j1, j2, page in pages:
            if page.spelling is None:
                if deadline is not None and time.perf_counter() > deadline:
                    return False
                t0 = time.perf_counter()
                page.spelling = self.check(model, language, j1, j2)
                self.stats['check'] += time.perf_counter() - t0
        return True

    # --- the canvas

    def enable(self, enabled):
        self.enabled = enabled
        if not enabled:
            self.show([])

    def visible_pages(self):
        canvas = self.canvas
        x1, y1, x2, y2 = canvas.get_viewport().items()
        return [(j1, j2, page)
                for j1, j2, x, y, page in canvas.layout.iter_pages()
                if y < y2 and y + page.height > y1]

    def squiggles(self, pages):
        """The errors of pages as absolute (i1, i2), without the word
        being typed (the cursor at its end)."""
        editor = self.canvas.editor
        cursor = None
        if editor is not None and editor.flow == 0:
            cursor = editor.abs_idx(editor.index)
        marks = set()
        for j1, j2, page in pages:
            for i1, i2 in page.spelling or ():
                if j1 + i2 != cursor:
                    marks.add((j1 + i1, j1 + i2))
        return sorted(marks)

    def show(self, marks):
        canvas = self.canvas
        if canvas.squiggles.get(0, []) != marks:
            canvas.squiggles = {0: marks}
            canvas.refresh()

    # --- text changes: until the next check the squiggles move along

    def inserted(self, model, i, n):
        self.shift(i, i, n)

    def removed(self, model, i, text):
        self.shift(i, i + len(text), -len(text))

    def shift(self, i1, i2, delta):
        """Move the squiggles behind a change of [i1, i2) by delta, drop
        those it touches."""
        marks = self.canvas.squiggles.get(0)
        if marks:
            self.canvas.squiggles = {0: [
                (j1, j2) if j2 < i1 else (j1 + delta, j2 + delta)
                for j1, j2 in marks if j2 < i1 or j1 > i2]}

    def on_destroy(self, event):
        event.Skip()
        if event.GetEventObject() is self.canvas:
            self.destroy()  # no longer observe the model

    def on_idle(self, event):
        event.Skip()
        canvas = self.canvas
        if not self.enabled or canvas.builder.generator is not None:
            return  # the layout first
        t0 = time.perf_counter()
        checked = self.stats['pages']
        pages = self.visible_pages()
        language = canvas.builder.settings.get(
            'language', settings_default['language'])
        if not self.check_pages(canvas.model, language, pages,
                                t0 + self.budget):
            event.RequestMore()
        t1 = time.perf_counter()
        self.show(self.squiggles(pages))
        if DEBUG and self.stats['pages'] > checked:
            print("spell: %d pages checked in %.2f ms, squiggles %.2f ms"
                  % (self.stats['pages'] - checked, (t1 - t0) * 1000,
                     (time.perf_counter() - t1) * 1000))


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
    pages = list(builder.layout.iter_childs())
    checker = SpellChecker()
    print("dictionary for %r: %s" % (language, checker.dictionary(language)))
    for run in ('cold', 'warm'):
        for j1, j2, page in pages:
            page.spelling = None
        checker.stats = dict(pages=0, words=0, lookups=0, check=0.0)
        checker.check_pages(doc.textmodel, language, pages)
        s = checker.stats
        errors = sum(len(page.spelling) for j1, j2, page in pages)
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
    "shift: squiggles behind a change move, touched ones are dropped"
    from types import SimpleNamespace
    checker = SpellChecker()
    checker.canvas = SimpleNamespace(squiggles={0: [(0, 3), (5, 8),
                                                     (10, 13)]})
    checker.inserted(None, 9, 1)             # between: only the last moves
    assert checker.canvas.squiggles[0] == [(0, 3), (5, 8), (11, 14)]
    checker.inserted(None, 8, 2)             # at the end of (5, 8): dropped
    assert checker.canvas.squiggles[0] == [(0, 3), (13, 16)]
    checker.removed(None, 3, 'xx')           # [3, 5): touches (0, 3)
    assert checker.canvas.squiggles[0] == [(11, 14)]


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


if __name__ == '__main__':
    import sys
    measure(sys.argv[1])
