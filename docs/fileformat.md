
# TexelTree File Format Specification

## 1. File Structure

A file consists of sections in fixed order. All sections except `[document]` are optional.
Empty sections may be omitted. Comments start with `#`.

1. **`[metadata]`** – Document properties (paper size, margins, author).
2. **`[basestyles]`** – Named basestyles.
3. **`[charstyles]`** – Named charstyles.
4. **`[liststyles]`** – Named liststyles.
5. **`[document]`** – Content stream.

---

## 2. Metadata (`[metadata]`)

| Field                           | Type   | Default | Description                          |
| ------------------------------- | ------ | ------- | ------------------------------------ |
| `title` / `author`              | String | `""`    | Document info                        |
| `paper`                         | String | `"A4"`  | `"A4"`, `"Letter"`, `"custom"`       |
| `margin_top/bottom/left/right`  | Number | `70.08` | Page margins in pt                   |
| `paper_width` / `paper_height`  | Number | *(A4)*  | Only when `paper="custom"`           |

---

## 3. Style System

### Properties

Properties control text rendering and structure. There are three categories:

**Text Properties** – carried by `T` elements:

| Name          | Default   | Description        |
| ------------- | --------- | ------------------ |
| `font_family` | `"Arial"` | Font face          |
| `font_size`   | `12`      | Font size in pt    |
| `bold`        | `False`   | Bold               |
| `italic`      | `False`   | Italic             |
| `underline`   | `False`   | Underline          |
| `strike`      | `False`   | Strikethrough      |
| `color`       | `"black"` | Foreground color   |
| `bgcolor`     | `"white"` | Background color   |

**Structure Properties** – carried by `NL` and `TAB` elements:

| Name                | Default  | Description                              |
| ------------------- | -------- | ---------------------------------------- |
| `alignment`         | `"left"` | `left` / `center` / `right` / `justify` |
| `space_before`      | `0`      | Space before paragraph in pt             |
| `space_after`       | `0`      | Space after paragraph in pt              |
| `line_spacing`      | `1.0`    | Line spacing factor                      |
| `page_break_before` | `False`  | Force page break before paragraph        |

**List Properties** – carried by `NL` and `TAB` elements:

Several list properties hold a list of 10 values, one per indent level (levels 0–9).
The `indent` attribute of `NL` selects which value applies to a given paragraph.

| Name              | Default                                                    | Description                                    |
| ----------------- | ---------------------------------------------------------- | ---------------------------------------------- |
| `paragraph_type`  | `"normal"`                                                 | `normal` / `list` / `numbered`                 |
| `level_policy`    | `"free"`                                                   | `free` / `fixed`                               |
| `indent_levels`   | (0cm, 1cm, 2cm, 3cm, 4cm, 5cm, 6cm, 7cm, 8cm, 9cm)        | Left indent per level                          |
| `first_line_indent` | `0`                                                      | First-line indent in pt (negative = hanging)   |
| `marker`          | ("•","◦","-","-","-","-","-","-","-","-")                  | Bullet symbol per level                        |
| `marker_pos`      | (-0.5cm × 10)                                              | Marker position relative to text per level     |
| `marker_size`     | (1 × 10)                                                   | Marker size per level                          |
| `marker_color`    | ("black" × 10)                                             | Marker color per level                         |
| `numbering_style` | ("1.0" × 10)                                               | Numbering format per level                     |
| `start_number`    | `None`                                                     | Start value for numbered lists (None or int)   |

**Structural Parameters** – element-specific keys that appear in the property block
alongside style properties:

| Element   | Key      | Default | Description                              |
| --------- | -------- | ------- | ---------------------------------------- |
| `NL`      | `indent` | `0`     | Indent level 0–9, selects the active value from all level-indexed properties |
| `C("table",…)` | `ncols` | —  | Number of columns; number of rows is implicit from slot count |

### Named Styles

Properties can be grouped and assigned a stable ID to form a named style. There are three kinds:

- **Basestyle** – covers all three property categories (Text, Structure, List). Referenced by `NL` and `TAB` via `base=`. A basestyle is always complete: unspecified properties fall back to built-in defaults.
- **Charstyle** – covers Text Properties only. Referenced by `T` via `char=`.
- **Liststyle** – covers List Properties only. Referenced by `NL` and `TAB` via `list=`.

Each named style may have:
- `name` – display name in the UI (optional)

Basestyles additionally support:
- `role` – semantic role for exporters, e.g. `"h1"`, `"bullet"`, `"code"` (optional)

**IDs are stable.** When editing a document, always reuse existing IDs. The `role` can be changed without touching the content stream.

### Overrides

Any element may specify properties directly alongside a named style reference. These override the named style's values for that element only.

```
NL({base="normal", alignment="right"})       # structure override
T("text", {char="highlight", bgcolor="red"}) # text override
```

---

## 4. Content Stream

### Property Block Notation

All parameters of an element — whether style properties or structural parameters — are
written in a single `{…}` block. The distinction between "style" and "structure" is an
implementation detail; from the format's perspective they are simply named attributes.

```
{bold}                               # boolean flag (True)
{bold, italic}                       # multiple flags
{font_family="Arial"}                # string value
{font_size=12}                       # numeric value
{bold, color="red", font_size=12}    # combined
{indent=2, base="bullet"}            # structural + style
{ncols=3, alignment="center"}        # structural + style
```

### Elements

The general pattern for all elements is:

```
TYPE
TYPE({prop=val, ...})
TYPE({prop=val, ...}, [slot], [slot], ...)
```

---

**`T("text")`** / **`T("text", {char="id", prop=val, ...})`**

Text content. `char` references a charstyle (optional). Additional properties are overrides.

---

**`NL`** / **`NL({prop=val, ...})`**

Paragraph end. Carries the properties of the preceding paragraph.

Key parameters:
- `indent` – indent level 0–9 (default `0`). Selects the active value from all
  level-indexed properties (e.g. `marker[indent]`, `indent_levels[indent]`).
- `base` – references a basestyle (default `"normal"`).

```
NL                              # indent=0, base="normal"
NL({base="h1"})                 # indent=0, base="h1"
NL({indent=2, base="bullet"})   # indent=2: uses marker[2], indent_levels[2], etc.
NL({indent=1, color="red"})     # indent=1, with text color override
```

---

**`TAB({prop=val, ...})`**

Tab character, used as horizontal separator within containers. Carries the same
properties as `NL`.

---

**`C("type", {prop=val, ...}, [slot], [slot], ...)`**

Container (table, image, etc.). The property block and slots are all optional.

- The `{…}` block carries both style properties and structural parameters.
- Each slot is enclosed in `[…]` and contains a sequence of elements.
- The number of rows in a table is implicit from the slot count and `ncols`.

```
C("table", {ncols=2},
  [T("Cell 1.1")],
  [T("Cell 1.2")],
  [T("Cell 2.1")],
  [T("Cell 2.2")]
)

C("table", {ncols=3, border=1},
  [T("A")], [T("B")], [T("C")],
  [T("D")], [T("E")], [T("F")]
)

C("image", {src="photo.png", width=200}, [])
```

---

**`ENDMARK`** / **`ENDMARK({prop=val, ...})`**

Closes the last paragraph. Same syntax as `NL`. Every document has exactly one `ENDMARK`,
at the end of `[document]`.

---

## 5. Full Reference Example

```
[metadata]
title = "Technical Specification"
author = "C. Ecker"
paper = "A4"
margin_left = 50.0

[basestyles]
"h1"     = {name="Header 1",  role="h1", bold, font_size=18}
"body"   = {name="Standard",  alignment="justify", line_spacing=1.2}
"bullet" = {name="Bullet",    role="bullet", paragraph_type="list"}

[charstyles]
"key" = {name="Keyword", bold, color="blue"}

[document]
T("Introduction")
NL({base="h1"})

T("This is an ")
T("important", {char="key"})
T(" term in the document.")
NL({base="body"})

T("First level item.")
NL({base="bullet"})
T("Second level item.")
NL({indent=1, base="bullet"})

C("table", {ncols=2},
  [T("Name")],
  [T("Value")],
  [T("Alpha")],
  [T("1")]
)
NL({base="body"})

ENDMARK({base="body"})
```

---

## 6. Rules for AI & Parsers

1. **ID stability:** Always reuse existing style IDs. Never invent new IDs unless adding a new style.
2. **Minimal overrides:** Only specify properties that differ from the named style. Unspecified properties fall back to the named style, then to built-in defaults.
3. **Roles:** The `role` field enables semantic export (e.g. to Markdown or HTML). It may change without modifying the content stream.
4. **`indent`:** Sets the indent level (0–9), selecting the active value from `indent_levels` and all other level-indexed properties. For `paragraph_type="list"` or `"numbered"` it also activates the corresponding marker.
5. **Unified property block:** All element parameters — structural and stylistic — go in the `{…}` block. There are no positional arguments other than the element type string and slot contents.
