"""
Hyphenation with Frank Liang's algorithm (as in TeX), after Ned
Batchelder's hyphenate.py (public domain). The patterns come from the
TeX hyph-utf8 files in patterns/ (sources and licences: LICENSES.md).

    >>> hyphenate('Silbentrennung', 'de-DE')
    ['Sil', 'ben', 'tren', 'nung']
"""

import os
import re
import sys
from ..core.language import normalize, lookup

PATTERN_DIR = os.path.join(os.path.dirname(__file__), 'patterns')

# languages with pattern files: the file's name, minimum characters
# before and after a break (TeX's lefthyphenmin/righthyphenmin); found
# by lookup (de-AT: de)
LANGUAGES = {'de': ('de-1996', 2, 2), 'en': ('en-us', 2, 3)}


class Hyphenator:
    """Breaks words at the points the patterns allow. patterns and
    exceptions are whitespace separated, as in TeX ('a1bc3d4',
    'ta-ble'); left and right are the minimum lengths of the first and
    last piece."""

    def __init__(self, patterns, exceptions='', left=2, right=2):
        self.left, self.right = left, right
        self.tree = {}
        for pattern in patterns.split():
            chars = re.sub(r'\d', '', pattern)
            points = [int(d or 0) for d in re.split(r'\D', pattern)]
            node = self.tree
            for c in chars:
                node = node.setdefault(c, {})
            node[None] = points
        self.exceptions = {ex.replace('-', ''): ex.split('-')
                           for ex in exceptions.lower().split()}
        self.cache = {}

    def hyphenate(self, word):
        """The pieces of word between its possible breaks, in the word's
        own case; [word] if it can't be broken."""
        if word not in self.cache:
            self.cache[word] = self._hyphenate(word)
        return self.cache[word]

    def _hyphenate(self, word):
        lower = word.lower()
        if not word.isalpha() or len(lower) != len(word):
            return [word]
        if lower in self.exceptions:
            pieces, i = [], 0
            for piece in self.exceptions[lower]:
                pieces.append(word[i:i + len(piece)])
                i += len(piece)
            return pieces
        work = '.' + lower + '.'
        points = [0] * (len(work) + 1)
        for i in range(len(work)):
            node = self.tree
            for c in work[i:]:
                if c not in node:
                    break
                node = node[c]
                for j, p in enumerate(node.get(None, ())):
                    points[i + j] = max(points[i + j], p)
        # points[k + 2] odd: a break after character k of word
        pieces = ['']
        for k, c in enumerate(word):
            pieces[-1] += c
            n = k + 1  # characters before the break
            if points[k + 2] % 2 and n >= self.left \
                    and len(word) - n >= self.right:
                pieces.append('')
        return pieces


_hyphenators = {}  # {language: Hyphenator or None}, loaded on first use


def _path(name, ext):
    return os.path.join(PATTERN_DIR, 'hyph-%s.%s.txt' % (name, ext))


def has_patterns(language):
    """Is there a pattern file for language (a code, see core.language)?"""
    key = lookup(language, LANGUAGES)
    return key is not None and os.path.exists(_path(LANGUAGES[key][0], 'pat'))


def get_hyphenator(language):
    """The Hyphenator for language, None for a language without
    patterns. A missing pattern file of a known language (a packaging
    error) is reported once on stderr."""
    key = lookup(language, LANGUAGES)
    if key is None:
        return None
    if key not in _hyphenators:
        name, left, right = LANGUAGES[key]
        if not has_patterns(key):
            print('Hyphenation patterns for %s not found: %s'
                  % (key, _path(name, 'pat')), file=sys.stderr)
            _hyphenators[key] = None
            return None

        def read(ext):
            if not os.path.exists(_path(name, ext)):
                return ''  # exceptions are optional
            with open(_path(name, ext), encoding='utf-8') as f:
                return f.read()
        _hyphenators[key] = Hyphenator(read('pat'), read('hyp'), left, right)
    return _hyphenators[key]


def hyphenate(word, language):
    """The pieces of word between its possible breaks in language."""
    hyphenator = get_hyphenator(language)
    return hyphenator.hyphenate(word) if hyphenator else [word]


def system_language(locale_name):
    """The language for new documents from a locale name such as
    'de_DE.UTF-8': its code if there are patterns for it, else
    American English."""
    if locale_name and has_patterns(locale_name):
        return normalize(locale_name)
    return 'en-US'
