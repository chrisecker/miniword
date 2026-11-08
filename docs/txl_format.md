
# TexelTree File Format Specification

## 1. File Structure

A file consists of sections in fixed order. All sections except `[document]` are optional.
Empty sections may be omitted. Comments start with `#`.

1. **`[basestyles]`** – Named basestyles.
2. **`[blobs]`** – Embedded binary data (images, etc.), base64-encoded.
3. **`[document]`** – Document properties (`PROPS`, optional) and content stream.

Strings are Python string literals in single or double quotes: `T('it\'s')`,
`T("say \"hi\"")`, `T('a\\b')`. Element names (`T`, `NL`, `FN`, …) and container
types (`"table"`, `"code"`) are case-sensitive. Rule of thumb: keywords of the syntax
are upper case, all names and values in quotes are lower case.

---

## 2. Document Properties (`PROPS`)

Document properties are written as the first element of `[document]`; only
values that differ from the default are written:

```
[document]
PROPS({author="Ada", paper="Letter"})
T("Hello")
ENDMARK
```

| Field                           | Type   | Default | Description                          |
| ------------------------------- | ------ | ------- | ------------------------------------ |
| `title` / `author`              | String | `""`    | Document info                        |
| `paper`                         | String | `"A4"`  | `"A4"`, `"Letter"`, `"custom"`       |
| `margin_top/bottom/left/right`  | Number | `70.87` | Page margins in pt (2.5 cm)          |
| `paper_width` / `paper_height`  | Number | *(A4)*  | Only when `paper="custom"`           |
| `header_left/center/right`      | Tuple  | `("none", "")` | Header field `(kind, text)`   |
| `footer_left/center/right`      | Tuple  | `("none", "")` | Footer field; `footer_center` defaults to `("page", "")` |
| `hyphenation`                   | Bool   | `False` | Automatic hyphenation                |
| `language`                      | String | `"en-us"` | Hyphenation patterns: `"en-us"`, `"de-1996"` |
| `header_footer_first_page`      | Bool   | `True`  | Header and footer also on page 1     |
| `header_footer_mirror`          | Bool   | `False` | Swap left and right on even pages    |

Header/footer kinds: `none`, `page`, `page_pages` ("3 / 10"), `title`,
`author`, `date`, `chapter` (running head: role h1), `section` (role h2),
`text` (the text as written).

---

## 3. Blobs (`[blobs]`)

The data of the images is embedded in the file, base64-encoded. Each entry maps a key to
the data; `IMG` elements refer to it by the key.

```
[blobs]
"3f9a1c0d2b7e4a56.png" = "base64encodeddata..."
"a07c55e19d0b3f28.jpg" = "base64encodeddata..."
```

MiniWord writes as key the first 16 hex digits of the SHA-256 of the data plus the
extension: equal images are stored once, and there are no unused entries. When a file
is written by other programs, any unique string works as key. The section is only a
storage form of the file – in the document, each image holds its data itself. It keeps
the long base64 data out of the content stream, so `[document]` stays readable.

---

## 4. Style System

### Properties

Properties control text rendering and structure. There are four categories:

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
| `widow_orphan_control` | `True` | No single line alone at a page break |
| `keep_with_next`    | `False`  | On the same page as the next paragraph |
| `hyphenate`         | `True`   | Hyphenate (if switched on for the document) |
| `right_indent`      | `0`      | Distance from the right text edge in pt  |

**Block Properties** – carried by `NL` elements:

Consecutive paragraphs with equal block properties and equal indents form a
block, decorated with one background and one border. The text stays at its
indents; background and border grow outward by `block_offset` (sideways
into the page margin). Above and below the block, `block_offset` +
`block_border_width` is reserved.

| Name                 | Default   | Description                         |
| -------------------- | --------- | ----------------------------------- |
| `block_color`        | `None`    | Background color (`None` = none)    |
| `block_offset`       | `0`       | Text to background/border in pt     |
| `block_border_width` | `0`       | Border line width in pt (`0` = none)|
| `block_border_color` | `"black"` | Border line color                   |
| `block_border_sides` | `"tblr"`  | Sides with a line: `t`, `b`, `l`, `r` |

Older files may contain `block_padding`; it is read as `block_offset`.

**List Properties** – carried by `NL` and `TAB` elements:

Several list properties hold a list of 10 values, one per indent level (levels 0–9).
The `indent` attribute of `NL` selects which value applies to a given paragraph.

| Name                | Default                                                    | Description                                    |
| ------------------- | ---------------------------------------------------------- | ---------------------------------------------- |
| `paragraph_type`    | `"normal"`                                                 | `normal` / `list` / `numbered`                 |
| `level_policy`      | `"free"`                                                   | `free` / `fixed`                               |
| `indent_levels`     | (0cm, 1cm, 2cm, 3cm, 4cm, 5cm, 6cm, 7cm, 8cm, 9cm)        | Left indent per level                          |
| `first_line_indent` | `0`                                                        | First-line indent in pt (negative = hanging)   |
| `list_indent`       | `1cm`                                                      | Extra indent added to list/numbered paragraphs (on top of `indent_levels[indent]`) |
| `marker`            | ("•","◦","-","-","-","-","-","-","-","-")                  | Bullet symbol per level                        |
| `marker_pos`        | (-0.5cm × 10)                                              | Marker position relative to text per level     |
| `marker_size`       | (1 × 10)                                                   | Marker size per level                          |
| `marker_color`      | ("black" × 10)                                             | Marker color per level                         |
| `numbering_style`   | ("1." × 10)                                                | Numbering format per level                     |
| `start_number`      | `None`                                                     | Start value for numbered lists (None or int)   |
| `counter`           | `"item"`                                                   | Counter to use: `item` / `section`             |

**Structural Parameters** – element-specific keys that appear in the property block
alongside style properties:

| Element   | Key      | Default | Description                              |
| --------- | -------- | ------- | ---------------------------------------- |
| `NL`      | `indent` | `0`     | Indent level 0–9, selects the active value from all level-indexed properties |
| `C("table",…)` | `ncols` | —  | Number of columns; number of rows is implicit from slot count |

### Level-indexed tuple properties

Properties like `indent_levels`, `marker`, `numbering_style` etc. are tuples with one
value per indent level (9 entries). When writing TXL files by hand or generating them
programmatically, a **shorter tuple** is allowed: the loader extends it to full length
by appending the remaining default values.

When saving, the writer trims trailing elements that match the built-in default, so only
the meaningful prefix is stored.

```
# Short form (3 entries) — levels 3–8 fall back to default:
indent_levels=(0, 0, 0)

# Equivalent full form after loading:
indent_levels=(0, 0, 0, 3cm, 4cm, 5cm, 6cm, 7cm, 8cm)
```

A tuple must have at least one element.

---

### Named Styles

The only named style type is the **basestyle**. It covers all three property categories
(Text, Structure, List). Referenced by `NL` and `TAB` via `base=`. A basestyle is always
complete: unspecified properties fall back to built-in defaults.

Each basestyle may have:
- `name` – display name in the UI (optional)
- `role` – semantic role for exporters, e.g. `"h1"`, `"bullet"`, `"code"` (optional)

**The normal style** is the first basestyle with `role="normal"`. It applies to
paragraphs without `base` (and to a `base` that names no basestyle). Without one,
such paragraphs have only the built-in defaults. A file without a normal style and
without a basestyle `"normal"` (files before 2026-11) gets the built-in one:
`"normal" = {name="Normal", role="normal", line_spacing=1.15, space_after=7}`.

A `role` belongs to the basestyle: a `role` in a paragraph's properties is ignored.

**IDs are stable.** When editing a document, always reuse existing IDs. The `role` can be
changed without touching the content stream.

### Counters

When `paragraph_type="numbered"`, the paragraph increments a counter and renders its
current value as a marker. The `counter` property selects which counter to use:

- `"item"` – for numbered list items. Resets to 0 when a `"section"` counter increments.
- `"section"` – for headings/sections. Resetting `"item"` on increment.

Counter state is maintained by the pagebuilder and stored in `rebuild_info`. It is
not stored in the document itself.

### Overrides

Any element may specify properties directly alongside a named style reference. These
override the named style's values for that element only.

```
NL({base="normal", alignment="right"})   # structure override
T("text", {bgcolor="red"})               # text override
```

---

## 5. Content Stream

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

**`T("text")`** / **`T("text", {prop=val, ...})`**

Text content. Additional properties are direct overrides on the character.

---

**`NL`** / **`NL({prop=val, ...})`**

Paragraph end. Carries the properties of the preceding paragraph.

Key parameters:
- `indent` – indent level 0–9 (default `0`). Selects the active value from all
  level-indexed properties (e.g. `marker[indent]`, `indent_levels[indent]`).
- `base` – references a basestyle (default: the normal style, see Named Styles).

```
NL                              # indent=0, the normal style
NL({base="h1"})                 # indent=0, base="h1"
NL({indent=2, base="bullet"})   # indent=2: uses marker[2], indent_levels[2], etc.
NL({indent=1, color="red"})     # indent=1, with text color override
```

---

**`TAB({prop=val, ...})`**

Tab character, used as horizontal separator within containers. Carries the same
properties as `NL`.

**`BR`** / **`BR({prop=val, ...})`**

Forced line break (Shift+Enter): ends the line, not the paragraph.

**`CB`** / **`CB({checked=True, ...})`**

Checkbox, e.g. at the start of a task list item (Markdown `- [ ]`,
`- [x]`); `checked` is left out when false.

**`RAW("source")`** / **`RAW("source", {prop=val, ...})`**

Raw HTML from Markdown, kept as its source: shown, never rendered,
written back unchanged.

**`HR`** / **`HR({prop=val, ...})`**

Horizontal rule, alone in its paragraph (Markdown `---`). The paragraph's
style (role `rule`) gives the space above and below.

---

**`IMG("key")`** / **`IMG("key", {prop=val, ...})`**

Inline image. `key` references an entry in the `[blobs]` section (`""`: an image
without data, e.g. a linked file that was not found). The image occupies one character position in the paragraph (it is a
Single, not a Container).

| Parameter | Default | Description |
| --------- | ------- | ----------- |
| `scale_x`, `scale_y` | `1.0` | Scale factors applied to the source pixel dimensions (old files: `scale` for both) |
| `proportional` | `True` | Keep the aspect ratio when resizing in the editor |
| `crop_x`, `crop_y` | `0` | Crop origin in source pixels (reserved, not yet rendered) |
| `crop_w`, `crop_h` | — | Display size in pt when cropping; also serves as explicit size override |
| `alt` | `""` | Alternative text |
| `path` | — | File the image came from, relative to the document |

```
IMG("photo.jpg")                                    # natural size
IMG("photo.jpg", {scale_x=0.5, scale_y=0.5})        # half size
IMG("photo.jpg", {crop_x=0, crop_y=0, crop_w=150, crop_h=200})  # 150×200 pt
```

---

**`FN(…)`** / **`FN({prop=val, ...}, …)`**

Footnote, at the position of its anchor in the text. Its content is written like a
document and ends with `ENDMARK`.

| Parameter   | Default     | Description |
| ----------- | ----------- | ----------- |
| `numbering` | `"numbers"` | `"numbers"`, `"letters"`, `"roman"` |
| `label`     | —           | Explicit label, overrides the automatic number |

```
T("Text")
FN(
  T("The note.")
  ENDMARK
)
FN({label="*"},
  T("Another note.")
  ENDMARK
)
NL({base="body"})
```

---

**`S("c")`** / **`S("c", {prop=val, ...})`**

A single character as an atomic element (a Single).

**`TAG("<kbd>")`**

Inline HTML tag from Markdown, kept as its source: shown, never rendered, written back
unchanged.

---

**`C("type", {prop=val, ...}, [slot], [slot], ...)`**

Container (e.g. table). The property block and slots are all optional.

- The type is lower case: `"table"`, `"code"`. Files written before 2026-11 use
  `"Table"` and `"Code"`; they are still read.
- The `{…}` block carries both style properties and structural parameters.
- Each slot is enclosed in `[…]` and contains a sequence of elements.
- The number of rows in a table is implicit from the slot count and `ncols`.

### `C("table", …)` — Table cells

The container `{…}` block carries the table-level parameters:

| Parameter    | Default | Description |
| ------------ | ------- | ----------- |
| `ncols`      | `1`     | Number of columns (required for a table) |
| `nheader`    | `0`     | Number of header rows |
| `breaklevel` | `1`     | Page break behaviour |
| `col_widths` | —       | Column widths as a tuple |

Old files use `header_rows` and `break_level`; they are still read.
Each slot corresponds to one cell; slots are ordered row by row.

Every slot may carry an optional `{…}` block with **cell-style attributes**.
This dict is the trailing separator of that cell — analogous to how `NL`
carries the paragraph style of the text before it. The dict is omitted when
all cell attributes are at their defaults.

| Cell attribute  | Default  | Description                                      |
| --------------- | -------- | ------------------------------------------------ |
| `border_left`   | `"thin"` | Left border                                      |
| `border_right`  | `"thin"` | Right border                                     |
| `border_top`    | `"thin"` | Top border                                       |
| `border_bottom` | `"thin"` | Bottom border                                    |
| `cell_halign`   | `None`   | Horizontal alignment (`left`/`center`/`right`/`justify`); `None` = from paragraph style |
| `cell_valign`   | `"top"`  | Vertical alignment (`top`/`middle`/`bottom`)     |
| `cell_bgcolor`  | `None`   | Background colour; `None` = transparent          |

Border values are strings: `"none"`, `"thin"`, `"thick"`, `"double"`.

Example — 2×1 table, first cell with a thick bottom border:

```
C("table",
  {ncols=1},
  [T("Hello"), {border_bottom="thick"}],
  [T("World")]
)
```

At shared cell edges both neighbours may define the same border. The
**right/bottom** cell takes precedence.

### `C("code", …)` — Code block

A code block (Markdown fenced code) or HTML block: one slot with the lines,
separated by `NL`.

| Parameter | Default  | Description |
| --------- | -------- | ----------- |
| `kind`    | `"code"` | `"code"` or `"html"` (HTML block) |
| `lang`    | `""`     | Language of the code, e.g. `"python"` |

```
C("code", {lang="python"},
  [T("x = 1")
   NL
   T("print(x)")]
)
```

---

**`ENDMARK`** / **`ENDMARK({prop=val, ...})`**

Closes the last paragraph. Same syntax as `NL`. Every document has exactly one `ENDMARK`,
at the end of `[document]`.

---

## 6. Full Reference Example

```
[basestyles]
"h1"     = {name="Header 1",  role="h1",     bold, font_size=18,
            paragraph_type="numbered", counter="section"}
"body"   = {name="Standard",  alignment="justify", line_spacing=1.2}
"bullet" = {name="Bullet",    role="bullet", paragraph_type="list"}
"enum"   = {name="Numbered",  role="enum",   paragraph_type="numbered"}

[blobs]
"photo.jpg" = "base64encodeddata..."

[document]
PROPS({title="Technical Specification", author="C. Ecker", margin_left=50.0})

T("Introduction")
NL({base="h1"})

IMG("photo.jpg", {scale=0.5})
NL({base="body"})

T("This is ")
T("important", {bold})
T(" text in the document.")
NL({base="body"})

T("First level item.")
NL({base="bullet"})
T("Second level item.")
NL({indent=0, base="bullet"})
T("Nested list item.")
NL({indent=1, base="bullet"})

T("First numbered item.")
NL({base="enum"})
T("Second numbered item.")
NL({base="enum"})

C("table", {ncols=2, nheader=1},
  [T("Name")],
  [T("Value")],
  [T("Alpha")],
  [T("1")]
)
NL({base="body"})

ENDMARK({base="body"})
```

---

## 7. Rules for AI & Parsers

1. **ID stability:** Always reuse existing style IDs. Never invent new IDs unless adding a new style.
2. **Minimal overrides:** Only specify properties that differ from the named style. Unspecified properties fall back to the named style, then to built-in defaults.
3. **Roles:** The `role` field enables semantic export (e.g. to Markdown or HTML). It may change without modifying the content stream.
4. **`indent`:** Sets the indent level (0–9), selecting the active value from `indent_levels` and all other level-indexed properties. It is an index, not a distance. `indent=0` corresponds to the normal text column (no extra indentation). List paragraphs get an additional `list_indent` offset on top of `indent_levels[indent]`, so `indent=0` is correct for a top-level list item.
5. **Markers:** A bullet or number is rendered on the first line of a paragraph when `paragraph_type="list"` or `"numbered"` is set. For numbered paragraphs, `counter="section"` uses the section counter (resets the item counter on increment); `counter="item"` (default) uses the item counter.
6. **Unified property block:** All element parameters — structural and stylistic — go in the `{…}` block. There are no positional arguments other than the element type string and slot contents.
7. **Case:** Element names are upper case (`T`, `NL`, `C`), container types lower case (`C("table", …)`); both are case-sensitive.
8. **Singles vs. Containers:** `IMG` and other keyword elements are Singles — they behave as atomic units in the edit model (length 1, no slots). Use `C("type", …)` only when slots are needed.
