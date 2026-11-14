"""Document languages as BCP 47 codes: language, optionally with region
('de', 'de-DE', 'en-US')."""

import re

CODE = re.compile(r'([a-z]{2,3})(?:-([a-z]{2}|\d{3}))?')
OLD = {'de-1996': 'de-DE'}  # values of older files (hyphenation pattern names)


def normalize(text):
    """The code for text, read leniently: 'de_DE.UTF-8', 'de-de' ->
    'de-DE', 'DE' -> 'de'. ValueError if text is no code."""
    code = text.split('.')[0].replace('_', '-').lower()
    if code in OLD:
        return OLD[code]
    m = CODE.fullmatch(code)
    if m is None:
        raise ValueError("not a language code: %r" % text)
    language, region = m.groups()
    if region is None:
        return language
    return language + '-' + region.upper()


def lookup(language, available):
    """The first of language and its language alone ('de-AT', 'de') in
    available (RFC 4647 lookup), None if neither is; language in any
    form normalize reads, None if it is no code."""
    try:
        code = normalize(language)
    except ValueError:
        return None
    for candidate in (code, code.split('-')[0]):
        if candidate in available:
            return candidate
    return None


def test_00():
    "normalize: lenient input, one form; old values; no code"
    assert normalize('de') == normalize('DE') == 'de'
    assert normalize('de-DE') == normalize('de-de') == normalize('de_DE') \
        == normalize('de_DE.UTF-8') == 'de-DE'
    assert normalize('en-us') == 'en-US'
    assert normalize('de-1996') == 'de-DE'
    assert normalize('es-419') == 'es-419'
    for text in ('Deutsch', 'd', 'de-DEU', 'C', ''):
        try:
            normalize(text)
        except ValueError:
            continue
        assert False, text


def test_01():
    "lookup: the code, else its language alone"
    available = {'de', 'en-GB'}
    assert lookup('de-AT', available) == 'de'
    assert lookup('de_1996', available) == 'de'
    assert lookup('en-gb', available) == 'en-GB'
    assert lookup('en-US', available) is None
    assert lookup('Deutsch', available) is None
