pt = 1
inch = 72 * pt
cm = 1 / 2.54 * inch
mm = 0.1 * cm

UNITS = {'': pt, 'pt': pt, 'mm': mm, 'cm': cm, 'in': inch}


def parse_length(text):
    """A length like '2cm', '20 mm', '1in' or '12' (pt) in pt; raises
    ValueError."""
    import re
    m = re.fullmatch(r'\s*(\d+(?:\.\d*)?)\s*([a-z]*)\s*', text.lower())
    if not m or m.group(2) not in UNITS:
        raise ValueError("not a length: %r" % text)
    return float(m.group(1)) * UNITS[m.group(2)]


def test_00():
    assert parse_length('12') == 12
    assert abs(parse_length('2.54 cm') - 72) < 1e-9
    assert parse_length('1In') == 72
    for text in ('', 'cm', '2 km', '-1mm'):
        try:
            parse_length(text)
        except ValueError:
            continue
        raise AssertionError(text)
