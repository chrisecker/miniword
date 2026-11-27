"""Spell checking with the checker of the operating system: Windows
ISpellChecker, macOS NSSpellChecker, elsewhere libenchant. All through
ctypes, no other packages needed. Independent of MiniWord.

    >>> d = dictionary('en-us')
    >>> d.check('house'), d.check('hosue')
    (True, False)
    >>> 'house' in d.suggest('hosue')
    True

Language tags may be 'en-US', 'en_us', 'en' or 'de-1996'; without a
known region the main dictionary of the language is taken ('de' ->
'de-DE'). Use a Dictionary from one thread only (on Windows and macOS:
the thread of the user interface).
"""

import sys

try:
    if sys.platform == 'win32':
        from . import windows as backend
    elif sys.platform == 'darwin':
        from . import macos as backend
    else:
        from . import enchantlib as backend
    backend.init()
    error = None  # why there is no backend
except (ImportError, OSError, AttributeError) as e:
    backend, error = None, e


def normalized(tag):
    """'en_us' -> 'en-US'."""
    lang, _, rest = tag.replace('_', '-').partition('-')
    if len(rest) == 2:
        rest = rest.upper()
    return lang.lower() + '-' + rest if rest else lang.lower()


def match(language, tags):
    """The tag of tags that fits language best, None if none does."""
    found = {normalized(tag): tag for tag in tags}
    wanted = normalized(language)
    lang = wanted.partition('-')[0]
    candidates = [wanted, lang + '-' + lang.upper(), lang]
    candidates += sorted(t for t in found if t.startswith(lang + '-'))
    return next((found[c] for c in candidates if c in found), None)


def languages():
    """The tags of the system's dictionaries."""
    return backend.languages() if backend else []


def dictionary(language):
    """A Dictionary (check(word), suggest(word)) for language, None if
    there is none."""
    tag = match(language, languages())
    if tag is None:
        return None
    return backend.Dictionary(tag)


# --- tests

def test_00():
    "matching language tags"
    tags = ['de_AT', 'de_CH', 'de_DE', 'en', 'en_GB', 'en_US']
    assert normalized('en_us') == 'en-US'
    assert match('en-us', tags) == 'en_US'
    assert match('EN_GB', tags) == 'en_GB'
    assert match('de-1996', tags) == 'de_DE'
    assert match('de', ['de_CH', 'de_AT']) == 'de_AT'
    assert match('en-ZA', tags) == 'en'
    assert match('fr', tags) is None
    assert match('en', ['en-GB', 'en-US']) == 'en-GB'


def system_dictionary(language):
    """dictionary(language); None (with a note) where a system may lack
    it, an error on Windows and macOS, which have English always."""
    d = dictionary(language)
    if d is None:
        assert sys.platform not in ('win32', 'darwin'), \
            (language, error, languages())
        print("no %s dictionary (%s), test skipped" % (language, error))
    return d


def test_01():
    "the system's checker: check and suggest"
    d = system_dictionary('en-US')
    if d is None:
        return
    assert d.language
    assert d.check('house') and d.check('houses') and d.check('The')
    assert not d.check('hosue') and not d.check('xqzvbn')
    assert 'house' in d.suggest('hosue')
    assert all(isinstance(s, str) for s in d.suggest('xqzvbn'))


def test_02():
    "words beyond ASCII"
    d = system_dictionary('en-US')
    if d is None:
        return
    assert not d.check('hôuse') and 'house' in d.suggest('hôuse')
    d = dictionary('de')
    if d is not None:
        assert d.check('Straße') and d.check('Häuser')
        assert not d.check('Strasße')
        assert 'Häuser' in d.suggest('Häusre')

