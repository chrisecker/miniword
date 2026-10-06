# -*- coding: utf-8 -*-

"""
Tests for hyphenation, following develnotes/hyphenation_concept.md.
Each test's docstring starts with its ID (HY-n).

Run with: python runtests.py miniword/tests/test_hyphenation.py
"""

from ..hyphenation import Hyphenator, hyphenate, system_language


def test_HY_1():
    "HY-1: German words are split at their syllables"
    assert hyphenate('Silbentrennung', 'de-1996') == \
        ['Sil', 'ben', 'tren', 'nung']
    assert hyphenate('Rechtschreibung', 'de-1996') == \
        ['Recht', 'schrei', 'bung']


def test_HY_2():
    "HY-2: umlauts and ß are handled"
    assert hyphenate('Häuser', 'de-1996') == ['Häu', 'ser']
    assert hyphenate('Straße', 'de-1996') == ['Stra', 'ße']


def test_HY_3():
    "HY-3: English words, and the exceptions file"
    assert hyphenate('hyphenation', 'en-us') == ['hy', 'phen', 'ation']
    assert hyphenate('table', 'en-us') == ['ta', 'ble']    # exception
    assert hyphenate('project', 'en-us') == ['project']   # exception


def test_HY_4():
    "HY-4: the case of the word is kept; it doesn't change the breaks"
    assert hyphenate('SILBENTRENNUNG', 'de-1996') == \
        ['SIL', 'BEN', 'TREN', 'NUNG']
    assert hyphenate('silbentrennung', 'de-1996') == \
        ['sil', 'ben', 'tren', 'nung']


def test_HY_5():
    "HY-5: no break within the language's minimum lengths"
    # patterns allowing a break before b, c and d
    h = Hyphenator('1b 1c 1d', left=2, right=2)
    assert h.hyphenate('abcde') == ['ab', 'c', 'de']
    h = Hyphenator('1b 1c 1d', left=1, right=3)
    assert h.hyphenate('abcde') == ['a', 'b', 'cde']


def test_HY_6():
    "HY-6: patterns and exceptions in unicode"
    h = Hyphenator('ä1b', exceptions='öl-ber', left=1, right=1)
    assert h.hyphenate('äbä') == ['ä', 'bä']
    assert h.hyphenate('ölber') == ['öl', 'ber']


def test_HY_7():
    "HY-7: words with other characters and unknown languages stay whole"
    assert hyphenate('Trennung2', 'de-1996') == ['Trennung2']
    assert hyphenate('Silbentrennung', 'fr') == ['Silbentrennung']
    assert hyphenate('', 'de-1996') == ['']


def test_HY_8():
    "HY-8: the system language for new documents"
    assert system_language('de_DE.UTF-8') == 'de-1996'
    assert system_language('de_AT') == 'de-1996'
    assert system_language('en_GB.UTF-8') == 'en-us'
    assert system_language('fr_FR') == 'en-us'
    assert system_language(None) == 'en-us'


# ---------------------------------------------------------------------
# Line breaking (layout/linewrap.py) - TESTDEVICE: every char 1 wide
# ---------------------------------------------------------------------

from ..layout.boxes import TextBox, HyphenBox
from ..layout.linewrap import simple_linewrap
from ..layout.testdevice import TESTDEVICE


def german(word):
    return hyphenate(word, 'de-1996')


def wrap(text, width, **kw):
    """Rows of text wrapped at width, each as the texts of its boxes."""
    rows = simple_linewrap([TextBox(text, device=TESTDEVICE)], width, **kw)
    return [[box.text for box in row] for row in rows]


def test_HY_9():
    "HY-9: the word sticking out is hyphenated before it is moved"
    rows = wrap('Die Silbentrennung ist gut', 12, hyphenate=german)
    assert rows[0] == ['Die Silben', '-']
    assert ''.join(rows[1]).startswith('trennung')


def test_HY_10():
    "HY-10: without a hyphenate function the line breaks as before"
    # as before: the word moves, then is broken without a hyphen
    assert wrap('Die Silbentrennung ist gut', 12) == \
        [['Die '], ['Silbentrennu'], ['ng ist gut']]


def test_HY_11():
    "HY-11: a word that can't be hyphenated in time moves on whole"
    # 'Die Sil-' would need 8 > 7: the word moves to the next line
    rows = wrap('Die Silbentrennung', 7, hyphenate=german)
    assert rows[0] == ['Die ']
    rows = wrap('Die xxxxxxxx', 7, hyphenate=german)  # no break points
    assert rows[0] == ['Die ']


def test_HY_12():
    "HY-12: the hyphen adds nothing to the text: length 0, clicks before it"
    rows = simple_linewrap([TextBox('Die Silbentrennung ist gut',
                                    device=TESTDEVICE)], 12, hyphenate=german)
    assert sum(len(box) for row in rows for box in row) == \
        len('Die Silbentrennung ist gut')
    hyphen = rows[0][-1]
    assert isinstance(hyphen, HyphenBox)
    assert len(hyphen) == 0 and hyphen.width == 1
    assert hyphen.get_index(0.9, 0) == 0


# ---------------------------------------------------------------------
# In the factory: document settings and the paragraph's hyphenate
# ---------------------------------------------------------------------

from ..core.document import settings_default
from ..core.styles import style_default
from ..core.utils import updated
from ..layout.rowfactory import State
from .test_rowfactory import generate, doc, par, flat


TEXT = 'Die Silbentrennung ist gut und trennt viele Wörter'


def rows_of(width=12, hyphenation=True, language='de-1996', **parstyle):
    state = State(width)
    state.settings = updated(settings_default, dict(
        hyphenation=hyphenation, language=language))
    paragraphs, _ = generate(doc(par(TEXT, **parstyle)), width, state=state)
    return [record[0] for record in flat(paragraphs)]


def test_HY_13():
    "HY-13: hyphenation is off by default and can be switched on"
    assert settings_default['hyphenation'] is False
    assert style_default['hyphenate'] is True
    assert not any(isinstance(b, HyphenBox)
                   for row in rows_of(hyphenation=False) for b in row.childs)
    assert any(isinstance(b, HyphenBox)
               for row in rows_of() for b in row.childs)


def test_HY_14():
    "HY-14: a paragraph style can switch it off; the language counts"
    assert not any(isinstance(b, HyphenBox)
                   for row in rows_of(hyphenate=False) for b in row.childs)
    assert not any(isinstance(b, HyphenBox)  # no patterns: no hyphens
                   for row in rows_of(language='xx') for b in row.childs)


def test_HY_15():
    "HY-15: justified, the hyphen isn't stretched and ends at the edge"
    rows = rows_of(alignment='justify')
    row = next(r for r in rows if isinstance(r.childs[-1], HyphenBox))
    assert row.childs[-1].width == 1
    assert abs(row.start[0] + row.width - 12) < 1e-9


def test_HY_16():
    "HY-16: right aligned, the hyphen ends at the right edge"
    rows = rows_of(alignment='right')
    row = next(r for r in rows if isinstance(r.childs[-1], HyphenBox))
    assert row.start[0] + row.width == 12


def test_HY_17():
    "HY-17: caret and clicks on a hyphenated row ignore the hyphen"
    row = next(r for r in rows_of()
               if isinstance(r.childs[-1], HyphenBox))
    x0 = row.start[0]
    for i in range(len(row) + 1):
        assert row.get_rect(i, 0, 0).x1 == x0 + i, i
    for i in range(len(row)):
        assert row.get_index(x0 + i + 0.2, 0) == i, i
    # a click on the hyphen gives the end of the row
    assert row.get_index(x0 + len(row) + 0.5, 0) == len(row)


# ---------------------------------------------------------------------
# Missing pattern files
# ---------------------------------------------------------------------

def test_HY_18():
    "HY-18: every language has its pattern file in the package"
    import os
    from .. import hyphenation
    for language in hyphenation.LANGUAGES:
        path = os.path.join(hyphenation.PATTERN_DIR,
                            'hyph-%s.pat.txt' % language)
        assert os.path.exists(path), path
        assert hyphenation.has_patterns(language)


def test_HY_19():
    "HY-19: missing patterns: no hyphenation, and one warning on stderr"
    import io
    from contextlib import redirect_stderr
    from .. import hyphenation
    saved = hyphenation.PATTERN_DIR, dict(hyphenation._hyphenators)
    hyphenation.PATTERN_DIR = '/nonexistent'  # e.g. not in the installer
    hyphenation._hyphenators.clear()
    try:
        err = io.StringIO()
        with redirect_stderr(err):
            assert not hyphenation.has_patterns('de-1996')
            assert hyphenation.get_hyphenator('de-1996') is None
            assert hyphenate('Silbentrennung', 'de-1996') == \
                ['Silbentrennung']
            hyphenation.get_hyphenator('de-1996')
        lines = err.getvalue().splitlines()
        assert len(lines) == 1 and 'de-1996' in lines[0]  # warned once
        assert hyphenation.get_hyphenator('xx') is None  # unknown: silent
    finally:
        hyphenation.PATTERN_DIR, cache = saved
        hyphenation._hyphenators.clear()
        hyphenation._hyphenators.update(cache)
