import re as _re
from ..core.styles import n_levels


def set_counter(indent, counter, value):
    counter[indent] = value
    for k in range(indent + 1, n_levels):
        counter[k] = 0

        
def inc_counter(indent, counter):
    value = counter[indent]+1
    return set_counter(indent, counter, value)
    
    
def _to_roman(n):
    """Convert positive integer to lowercase Roman numeral string."""
    val  = [1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1]
    syms = ['m', 'cm', 'd', 'cd', 'c', 'xc', 'l', 'xl', 'x', 'ix', 'v', 'iv', 'i']
    result = ''
    for v, s in zip(val, syms):
        while n >= v:
            result += s
            n -= v
    return result or 'i'


def format_number(arr, level, style):
    """Format a numbered-list marker from a counter array.

    Each occurrence of ``1``, ``a``, ``A``, ``i``, or ``I`` in *style* is
    replaced by the counter at the corresponding nesting depth (left to right,
    starting at depth 0).  Everything else is literal text.

    Examples::

        format_number([3, 0, ...], 0, "1.")   → "3."
        format_number([2, 4, ...], 1, "1.1.") → "2.4."
        format_number([5, 0, ...], 0, "a.")   → "e."
        format_number([3, 0, ...], 0, "i.")   → "iii."
    """
    parts    = _re.split(r'([1aAiI])', style)
    n_tokens = (len(parts) - 1) // 2
    result   = parts[0]
    # Single-token styles ("1.", "a.", …) display the counter at the
    # current indent level.  Composite styles ("1.1.") start at level 0
    # so the full hierarchy is shown.
    lev = level if n_tokens == 1 else 0
    for k in range(1, len(parts), 2):
        typ = parts[k]
        n   = arr[lev] if lev < len(arr) else 0
        lev += 1
        if typ == '1':
            result += str(n)
        elif typ == 'a':
            result += chr(ord('a') + (n - 1) % 26) if n > 0 else 'a'
        elif typ == 'A':
            result += chr(ord('A') + (n - 1) % 26) if n > 0 else 'A'
        elif typ == 'i':
            result += _to_roman(n) if n > 0 else 'i'
        else:  # 'I'
            result += _to_roman(n).upper() if n > 0 else 'I'
        if k + 1 < len(parts):
            result += parts[k + 1]
    return result
