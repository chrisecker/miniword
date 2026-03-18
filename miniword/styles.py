# -*- coding. utf-8 -*-

"""
Conceptual notes and open questions:

List values (i.e. indent_levels) are still conceptually problematic.

- Should they be treated as if there were 10 distinct values
  like indent_01, indent_02, ...?
- What constitutes an override — a single value or the entire list?

This issue arises for:
- offsets
- marker
- marker_pos
- marker_alignment
- numbering_style


This module consolidates style computation. The goal is to decouple
other modules from implementation details so the style model can be
changed easily.

A known issue with the current implementation is that text formatting
(styling) is not distinguished from paragraph layout parameters
(alignment, indent, ...). As a result, every box ends up with its own
dict containing many entries.

A cleaner approach might be to store only text formatting attributes
directly in ParStyle, and keep layout parameters in a separate
attribute.
"""

from collections import OrderedDict
from .units import pt, inch, cm, mm

n_levels = 9  # 0–8, displayed as 1–9
defaultbullets = ["•", "◦", "▪", "–"]


text_default = {
    "font_family":  "Arial",
    "font_size":    12,
    "bold":         False,
    "italic":       False,
    "underline":    False,
    "strike":       False,
    "color":        "black",
    "bgcolor":      "white",
    # "letter_spacing":    0,        # normal
    # "vertical_position": "normal"  # normal / superscript / subscript
}

structure_default = {                
    "paragraph_type":  "normal",     # normal / list / numbered
    "level_policy":    "free",       # free / fixed
    "indent_levels":   tuple(i * cm for i in range(n_levels)),
    "first_line_indent": 0,          # hanging indent: use negative values
    "marker":          ("•", "◦") + ("–",) * 8,
    "marker_pos":      (-0.5 * cm,) * n_levels,
    # "marker_alignment": ('right',) * n_levels,
    "marker_size":     (1,) * n_levels,
    "marker_color":    ("black",) * n_levels,
    "numbering_style": ("1.",) * n_levels,  # e.g. "1.", "1.1", "a."
    "start_number":    None,               # None or int (for numbered lists)
}

layout_default = {
    "alignment":         "left",    # left / center / right / justify
    "space_before":      0,         # in pt
    "space_after":       0,         # in pt
    "line_spacing":      1.0,       # 1 = single spacing
    # "min_line_height": None,
    # "keep_together":   False,
    # "tab_stops":       ...,       # TODO

    "page_break_before": False,     # start on a new page
    # "keep_with_next":       False, # keep together with next paragraph
    # "keep_lines_together":  False, # prevent paragraph from breaking across pages
    # "widow_control":        True,  # avoid widows
    # "orphan_control":       True,  # avoid orphans
    # "border_top":           None,  # top border
    # "border_bottom":        None,  # bottom border
    # "background_color":     None,  # background color
}

other_default = {
    "next_style": "standard",
}


# Keys that live exclusively on individual paragraphs and must never be
# promoted to base styles or treated as style overrides (no red triangle).
PARAGRAPH_ONLY_KEYS = frozenset({'start_number'})


style_default = {
    **text_default,
    **structure_default,
    **layout_default,
    **other_default,
}


def updated(default, *styles):
    """Merges dicts by updating from left to right."""
    r = default.copy()
    for s in styles:
        r.update(s)
    return r


# This stylesheet is intended for internal testing:
normal = updated(
    text_default,
    structure_default,
    layout_default,
    other_default,
    dict(name="Normal"),
)

h0 = updated(normal, dict(name="Heading 1", font_size=18, bold=True,
                          page_break_before=True))
h1 = updated(normal, dict(name="Heading 2", font_size=16, bold=True,
                          color="red"))
h2 = updated(normal, dict(name="Heading 3", font_size=14, bold=True))
h3 = updated(normal, dict(name="Heading 4", font_size=12, bold=True))

from .stylesheet import StyleSheet

testsheet = StyleSheet()
testsheet.set('normal', normal)
testsheet.set('h0', h0)
testsheet.set('h1', h1)
testsheet.set('h2', h2)
testsheet.set('h3', h3)


def mk_style(stylesheet, parstyle, style):
    basestyle = stylesheet[parstyle.get("base", "normal")]
    return updated(basestyle, parstyle, style)


def mk_parstyle(stylesheet, parstyle):
    basestyle = stylesheet[parstyle.get("base", "normal")]
    return updated(basestyle, parstyle)


def test_00():
    assert (21*cm - 595.27) < 0.1
    
def test_01():
    testsheet.get('normal')['font_size'] == 12
