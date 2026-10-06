"""
Hyphenation with Frank Liang's algorithm (as in TeX), after Ned
Batchelder's hyphenate.py (public domain). The patterns come from the
TeX hyph-utf8 files in patterns/ (sources and licences: LICENSES.md).

    >>> hyphenate('Silbentrennung', 'de-1996')
    ['Sil', 'ben', 'tren', 'nung']
"""

import os
import re
import sys

PATTERN_DIR = os.path.join(os.path.dirname(__file__), 'patterns')

# languages with pattern files: minimum characters before and after a
# break (TeX's lefthyphenmin/righthyphenmin)
LANGUAGES = {'de-1996': (2, 2), 'en-us': (2, 3)}


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


def _path(language, ext):
    return os.path.join(PATTERN_DIR, 'hyph-%s.%s.txt' % (language, ext))


def has_patterns(language):
    """Is there a pattern file for language?"""
    return language in LANGUAGES and os.path.exists(_path(language, 'pat'))


def get_hyphenator(language):
    """The Hyphenator for language, None for a language without
    patterns. A missing pattern file of a known language (a packaging
    error) is reported once on stderr."""
    if language not in LANGUAGES:
        return None
    if language not in _hyphenators:
        if not has_patterns(language):
            print('Hyphenation patterns for %s not found: %s'
                  % (language, _path(language, 'pat')), file=sys.stderr)
            _hyphenators[language] = None
            return None

        def read(ext):
            if not os.path.exists(_path(language, ext)):
                return ''  # exceptions are optional
            with open(_path(language, ext), encoding='utf-8') as f:
                return f.read()
        left, right = LANGUAGES[language]
        _hyphenators[language] = Hyphenator(read('pat'), read('hyp'),
                                            left, right)
    return _hyphenators[language]


def hyphenate(word, language):
    """The pieces of word between its possible breaks in language."""
    hyphenator = get_hyphenator(language)
    return hyphenator.hyphenate(word) if hyphenator else [word]


def system_language(locale_name):
    """Hyphenation language for new documents from a locale name such as
    'de_DE.UTF-8': German for German locales, else American English."""
    if locale_name and locale_name.lower().startswith('de'):
        return 'de-1996'
    return 'en-us'
