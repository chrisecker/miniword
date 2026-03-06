
# Spezifikation: TexelTree File Format

## 1. Dokumentenstruktur & Sektionen

Das Format ist ein minimalistischer Stream. Alle Sektionen außer `[document]` sind optional.

1. **`[metadata]`**: Globale Einstellungen (Papierformat, Autor, Ränder).
2. **`[basestyles]`**: Absatz-Vorlagen (Paragraph Styles).
3. **`[charstyles]`**: Zeichen-Vorlagen (Character Styles).
4. **`[liststyles]`**: Listen-Definitionen (Bullet/Ordered).
5. **`[resources]`**: Binär-Referenzen (Bilder/Blobs).
6. **`[document]`**: Der Inhalts-Stream.

---

## 2. Metadaten-Konkretisierung (`[metadata]`)


| Feld                          | Typ     | Default  | Beschreibung                    |
| ------------------------------| ------- | -------- | ------------------------------- |
| `title` / `author`            | String  | `""`     | Dokumentinfos                   |
| `paper`                       | String  | `"A4"`   | `"A4"`, `"Letter"`, `"custom"`  |
| `margin_top/bottom/left/right`| Zahl    | `70.08`  | Seitenränder in pt              |
| `paper_width/height`          | Zahl    | *(A4)*   | Nur bei `paper="custom"`        |

---

## 3. Style-System: IDs und Rollen

Styles enthalten Parameter (properties) mit denen der Text gesetzt wird. Es werden die folgenden Kategorien benutzt:

Text-Properties:

| Name          | Default   | Comment                                     |
| ---           | ---       | ---                                         |
| `font_family` | `"Arial"` | Festlegung der Schriftart                   |
| `font_size`   | `12`      | Schriftgröße (Standardwert)                 |
| `bold`        | `False`   | Deaktiviert Fettkapselung                   |
| `italic`      | `False`   | Deaktiviert Kursivschrift                   |
| `underline`   | `False`   | Deaktiviert Unterstreichung                 |
| `strike`      | `False`   | Deaktiviert Durchstreichung                 |
| `color`       | `"black"` | Textfarbe (Vordergrund)                     |
| `bgcolor`     | `"white"` | Hintergrundfarbe                            |
| `text`        | `"none"`  | Id eines benannten Text-Style als Grundlage |


List-Properties:

| Name                | Default                                                                          | Comment                                                |
| ------------------- | -------------------------------------------------------------------------------- | ------------------------------------------------------ |
| `paragraph_type`    | `"normal"`                                                                       | normal / list / numbered                               |
| `level_policy`      | `"free"`                                                                         | free / fixed                                           |
| `indent_levels`     | (0cm, 1cm, 2cm, 3cm, 4cm, 5cm, 6cm, 7cm, 8cm, 9cm)                               | Einzugsstufen basierend auf cm und Level-Anzahl        |
| `first_line_indent` | `0`                                                                              | Einzug der ersten Zeile (negativ für hängenden Einzug) |
| `marker`            | ("•","◦","-","-","-","-","-","-","-","-")                                        | Symbole für Aufzählungszeichen                         |
| `marker_pos`        | (-0.5cm, -0.5cm, -0.5cm, -0.5cm, -0.5cm, -0.5cm, -0.5cm, -0.5cm, -0.5cm, -0.5cm) | Position der Marker relativ zum Text                   |
| `marker_size`       | (1, 1, 1, 1, 1, 1, 1, 1, 1)                                                      | Größe der Aufzählungszeichen pro Ebene                 |
| `marker_color`      | ("black", "black", "black", "black", "black", "black", "black", "black", "black")| Farbe der Aufzählungszeichen pro Ebene                 |
| `numbering_style`   | ("1.0", "1.0", "1.0", "1.0", "1.0", "1.0", "1.0", "1.0", "1.0")                  | Formatierung der Nummerierung (z.B. "1.", "1.1", "a.") |
| `start_number`      | `None`                                                                           | Startwert für nummerierte Listen (None oder Integer)   |
| `list`              | `none`                                                                           | Id eines Liststyle als Grundlage                       |


Structure-Properties:


| Name                | Default  | Comment                                      |
| ---                 | ---      | ---                                          |
| `alignment`         | `"left"` | Ausrichtung: left / center / right / justify |
| `space_before`      | `0`      | Abstand vor dem Absatz in pt                 |
| `space_after`       | `0`      | Abstand nach dem Absatz in pt                |
| `line_spacing`      | `1.0`    | Zeilenabstand (1 = einzeilig)                |
| `page_break_before` | `False`  | Erzwingt einen Seitenumbruch vor dem Absatz  |


### Speicherort der Styleinformationen
Die Text-Properties liegen in den Texeln. Zu jeder Indexposition gibt es einen Satz von Text-Properties. Beispielsweise 
T("ein Text", {color="red", bold})

Structure- und List-Properties liegen in NL und TAB. NL und TAB haben damit alle drei Arten von Properties. 


### Benannte Styles und Overrides
Gruppen von Properties können mit einer Id versehen werden und als benannter Style referenziert werden. Identifier (IDs) wie `"normal"` oder `"a3f9"` sind **stabil**. Es gibt 3 Arten von benannte Styles: 
- Basestyles
- Text-Styles 
- List-Styles


Ein Basestyle umfasst Properties aus allen drei Property-Kategorien: Text-Properties, Structure-Properties und List-Properties. Basestyles sind immer vollständig, sind nicht alle Werte angegeben, dann wird der entsprechende Defaultwert verwendet. 

Basestyles werden in den NL und TAB-Texeln durch die Angabe "base" gewählt. Ist "base" nicht angegeben, dann gilt "normal":

NL()
NL({base="normal"}) # äquivalent

Properties können auch direkt angegeben werden und überschreiben dann den entsprechenden Wert des Basestyle (Override):
NL({base="normal", align="right"}) # überschreiben einer Structure-Property
NL({base="normal", color="red"}) # Überschreiben einer Text-Property

Basestyles kann eine **Rolle** (`role`) zugewiesen werden. Sie definiert die semantische Bedeutung (z.B. `"h1"`, `"bold"`, `"code"`) und kann geändert werden, ohne den Text zu modifiziere.

Text-Styles und List-Styles sind spezialisierter. Text-Styles enthalten lediglich Text-Properties und List-Styles lediglich List-Properties. 

Text-Styles werden für alle Indexpositionen definiert: 
T("Ein Text", {text="highlight"})

Auch hier werden Properties des benannten Styles durch Overrides überschrieben: 
T("Ein Text", {text="highlight"m bgcolor="red"})

Identifier (IDs) wie `"normal"` oder `"a3f9"` sind **stabil** und werden im Stream referenziert. Die **Rolle** (`role`) definiert die semantische Bedeutung (z.B. `"h1"`, `"bold"`, `"code"`) und kann geändert werden, ohne den Text zu modifizieren.


## 4. Content-Stream & Syntax

### Style-Notation

* `{bold}`: Boolesches Flag (True).
* `{font="Arial", size=12}`: String- und numerische Werte.

### Elemente

* **T("text", {base="char_id", ...})**: Textinhalt. Referenziert nun optional `charstyles`.
* **NL({base="base_id", ...})**: Absatz-Ende. Referenziert `basestyles`. Es kann ein Wert für ident angegeben werden (eine Zahl zwischen 0 und 9), Default ist der Wert 0:
  - NL(2, base="normal")
* **TAB({base="base_id", ...})**: Tabulator-Zeichen, dient als horizontaler Trenner (innerhalb von Containern).
* **C("typ", params, {D0}, [Slots])**: Container (Tabelle, Bild, etc.).

---

## 5. Vollständiges Referenz-Beispiel

```rust
[metadata]
title = "Technische Spezifikation"
author = "C. Ecker"
paper = "A4"
margin_left = 50.0

[basestyles]
"h1" = {name="Header 1", role="h1", bold, size=18}
"body" = {name="Standard", alignment="justify", line_spacing=1.2}

[charstyles]
"key" = {name="Keyword", bold, color="blue"}

[document]
T("Einführung")
NL({base="h1"})

T("Dies ist ein ")
T("wichtiger", {char="key"})
T(" Begriff im Dokument.")
NL({base="body"})

C("table", 2, 1, {size=10}, 
  [T("ID"), {bold}], 
  [T("Wert")]
)
NL({base="body"})

ENDMARK

```

---

## 6. Wichtige Regeln für KI & Parser

1. **Stabilität:** Verwende beim Bearbeiten bestehende IDs weiter, auch wenn du die Attribute innerhalb der Sektionen änderst.
2. **Minimalismus:** Nicht definierte Attribute fallen auf die System-Defaults zurück.
3. **Rollen:** Die `role` in `[basestyles]` dient der semantischen Einordnung für Konverter (z.B. nach Markdown oder HTML).

