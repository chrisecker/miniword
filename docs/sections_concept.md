# Konzept: Abschnittswechsel (Section Breaks)

## Ziel

Abschnittswechsel ermöglichen es, Teile eines Dokuments mit unterschiedlichen
Seiteneigenschaften und Seitennummerierungen zu versehen – analog zu Word oder
Apple Pages.

## Abgrenzung zu Apple Pages / Word

- **Apple Pages**: Abschnitte sind *top-level Container*; das Dokument ist eine
  Liste von Abschnitten, jeder mit eigenem Seitenlayout, Kopf-/Fußzeile und
  Nummerierung. Kein Inline-Marker im Text.

- **Word**: Abschnittswechsel sind *Inline-Marker* im Textstrom (wie
  Absatzzeichen). Typen: „Nächste Seite", „Fortlaufend", „Gerade/Ungerade
  Seite". Anzeige als gestrichelte Doppellinie wenn Formatierungszeichen
  sichtbar sind.

- **miniword**: Wie Word – Inline-Marker im Textstrom, immer mit
  Seitenumbruch (kein „Fortlaufend"). Anzeige als sichtbares Symbol im
  Screen-Modus.


## Neuer Texel: `Section`

`Section` ist eine Unterklasse von `NL` (NewLine). Er beendet den aktuellen
Absatz und markiert gleichzeitig den Beginn eines neuen Abschnitts.

```python
class Section(NL):
    # Seitennummerierung
    page_number_start = None   # None = fortführen; int = neu starten
    page_number_style = None   # None = erben; 'arabic'|'roman'|'ROMAN'|
                               #               'letter'|'LETTER'
    # Seitengeometrie (None = aus Dokumenteinstellungen erben)
    paper        = None        # z.B. 'A4', 'A5', 'Letter'
    paper_width  = None        # für paper='custom'
    paper_height = None
    margin_top   = None
    margin_right = None
    margin_bottom = None
    margin_left  = None
```

`Section` erbt das gesamte Edit-Verhalten von `NL` (Single, Länge 1, hat
`.style`, `.parstyle`, `.indent`). Es sind keine Änderungen am Textmodell
nötig.

### TXL-Syntax

```
SECTION()
SECTION({page_number_start=1})
SECTION({page_number_start=1, page_number_style='roman'})
SECTION({paper='A5', margin_top=15mm, margin_bottom=15mm})
```

`SECTION()` ohne Argumente erzeugt einen reinen Seitenumbruch ohne
Eigenschaftsänderung.


## RestartMemo-Erweiterung

`RestartMemo` bekommt zwei neue Felder:

```python
class RestartMemo:
    ...
    page_number_offset = 0         # Versatz: angezeigte Nr. = index + offset
    page_number_style  = 'arabic'  # aktueller Nummerierungsstil
```

`geometry` und `border` existieren bereits und tragen Seitengröße und Ränder.
Alle abschnittsbezogenen Eigenschaften sind damit im State enthalten.

### `copy()` und `can_finish`

`copy()` muss die neuen Felder mitkopieren (sie sind immutable, kein
deep-copy nötig).

`can_finish` in `builder.py` vergleicht bereits `restartmemo.counters`. Die
neuen Felder müssen explizit verglichen werden:

```python
if old_restartmemo.page_number_offset != state.page_number_offset:
    return False
if old_restartmemo.page_number_style != state.page_number_style:
    return False
```


## pagegen.py – Änderungen

### `generate_boxes`

`generate_boxes` liefert bereits den letzten Texel des Absatzes als `nl = l[-1]`.
Eine Section wird erkannt durch `isinstance(nl, Section)`.

`generate_boxes` selbst wird nicht geändert; der Aufrufer `generate_pages`
wertet den Texeltyp aus.

### `generate_pages` – Abschnittsbehandlung

Aktuell liest `generate_pages` Geometrie und Ränder einmalig am Anfang:

```python
margin       = state.border
page_width   = state.geometry[0]
page_left    = margin[3]
page_right   = page_width - margin[1]
...
```

Ergänzung: nach jedem Absatz prüfen ob `nl` eine `Section` ist; wenn ja:

1. Seitenumbruch erzwingen (wie `page_break_before`)
2. Geometrie und Ränder aus den Section-Eigenschaften aktualisieren (fehlende
   Werte aus den Dokumenteinstellungen erben)
3. `state.geometry` und `state.border` aktualisieren
4. `page_number_offset` und `page_number_style` im State setzen
5. Lokale Variablen `margin`, `page_width`, `page_left`, `page_right`,
   `container_left`, `container_right` neu berechnen

```python
if isinstance(nl, Section):
    draft = draft.create_newpage()   # Seitenumbruch erzwingen
    _apply_section(state, nl, document_settings)
    # lokale Geometrievariablen neu berechnen
    margin          = state.border
    page_width      = state.geometry[0]
    page_left       = margin[3]
    page_right      = page_width - margin[1]
    container_left  = page_left
    container_right = page_right
```

Hilfsfunktion:

```python
def _apply_section(state, section, base_settings):
    """Aktualisiert state anhand der Section-Eigenschaften."""
    props = updated(settings_default, base_settings)
    # Geometrie
    paper = section.paper or props['paper']
    if paper in PAPER_SIZES:
        w, h = PAPER_SIZES[paper]
    else:
        w = section.paper_width  or props['paper_width']
        h = section.paper_height or props['paper_height']
    state.geometry = (w, h)
    # Ränder
    state.border = (
        section.margin_top    or props['margin_top'],
        section.margin_right  or props['margin_right'],
        section.margin_bottom or props['margin_bottom'],
        section.margin_left   or props['margin_left'],
    )
    # Seitennummerierung
    if section.page_number_style is not None:
        state.page_number_style = section.page_number_style
    if section.page_number_start is not None:
        # offset so dass: (globaler_index + 1) + offset == page_number_start
        # wird beim ersten Aufruf von adjust_pages gesetzt
        state.page_number_pending_start = section.page_number_start
```

Der `page_number_offset` kann erst gesetzt werden wenn die erste Seite des
neuen Abschnitts bekannt ist (deren globaler Index). Daher wird
`page_number_pending_start` als temporäres Feld gesetzt und beim
Seitenabschluss aufgelöst.


## builder.py – `adjust_pages`

```python
def adjust_pages(self):
    for i, page in enumerate(self._layout.childs):
        memo = page.restartmemo
        style  = getattr(memo, 'page_number_style',  'arabic')
        offset = getattr(memo, 'page_number_offset', 0)
        page.adjust(i + 1 + offset, style)
```

`page.adjust` bekommt den formatierten Wert; `format_number` aus `pagegen.py`
kann für Stil-Konvertierung verwendet werden.


## Darstellung im Editor

`Section` wird von der Factory wie `NL` behandelt, bekommt aber am Zeilenende
ein sichtbares `§`-Symbol (nur Screen-Modus, nicht im PDF). Analog zur
Darstellung von Zeilenumbrüchen (`BR`).


## Erster Abschnitt – kein expliziter Section-Texel nötig

`restartmemo_from_settings(settings)` liefert den initialen State aus den
Dokumenteinstellungen. Der erste Abschnitt wird implizit durch die
Dokumenteinstellungen definiert. Es ist kein `SECTION`-Texel an Position 0
erforderlich.

Bestehende Dokumente ohne `SECTION`-Texel verhalten sich unverändert.


## Zusammenfassung der betroffenen Dateien

| Datei                | Änderung                                              |
|----------------------|-------------------------------------------------------|
| `texels.py`          | Neue Klasse `Section(NL)`                             |
| `texeltreeformat.py` | `SECTION(...)` parsen und serialisieren               |
| `pagegen.py`         | `RestartMemo` erweitern; `_apply_section` in `generate_pages` |
| `builder.py`         | `adjust_pages` mit Stil und Offset                    |
| `factory.py`         | `Section`-Handler für `§`-Symbol                     |
| `can_finish`         | Vergleich von `page_number_offset` und `page_number_style` |


## Offene Fragen

1. **Seitengeometrie-Wechsel innerhalb eines Dokuments**: Wenn ein Abschnitt
   eine andere Seitengröße hat, müssen die Rest-Seiten beim `can_finish`-Check
   korrekt verworfen werden. `geometry` und `border` werden bereits verglichen
   (über `restartmemo.geometry != old_restartmemo.geometry`)?
   → Prüfen ob `can_finish` diese Felder vergleicht.

2. **Kopf- und Fußzeilen pro Abschnitt**: Noch nicht adressiert; würde
   `header_ref`/`footer_ref` im State erfordern.

3. **Abschnitt-Inspector**: UI zum Bearbeiten der Section-Eigenschaften.
