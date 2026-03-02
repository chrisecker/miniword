# TXL – Dateiformat-Dokumentation

*Version 0.1 – Arbeitsdokument*

---

## Überblick

Eine `.txl`-Datei speichert ein vollständiges MiniWord-Dokument. Sie besteht
aus vier Sektionen, die in fixer Reihenfolge aufeinander folgen. Das Format
ist textbasiert, menschenlesbar und Git-diffbar.

```
[charstyles]     optional – benannte Zeichenstile
[basestyles]     optional – benannte Absatzstile
[liststyles]     optional – benannte Listen/Aufzählungsstile
[document]       required – Inhalt als TexelTree (inkl. optionaler PROPS)
```

Leere Sektionen können weggelassen werden. Kommentare beginnen mit `#`.

---

## Sektionen

### [charstyles]

Benannte Zeichenstile. Jeder Eintrag hat eine ID, einen optionalen Namen,
eine optionale Rolle und Style-Attribute.

```
[charstyles]
"bold"  = {name="Fett", role="bold", bold}
"code"  = {name="Code", role="code", font="Courier New", size=10}
"red"   = {name="Rot",  color="red"}
```

Felder:
- `name` – angezeigter Name im UI (optional)
- `role` – semantische Rolle aus dem MD-Vokabular (optional): `bold`, `italic`, `code`, `strikethrough`, `link`
- alle weiteren Felder sind Style-Attribute

### [basestyles]

Benannte Absatzstile. Jeder Stil speichert nur **Abweichungen vom eingebauten
Default** – keine Vererbung zwischen Styles, keine Hierarchie.

```
[basestyles]
"normal" = {name="Normal"}
"h1"     = {name="Überschrift 1", role="h1",  size=18, bold,
            space_before=12, space_after=6}
"h2"     = {name="Überschrift 2", role="h2",  size=14, bold,
            space_before=8,  space_after=4}
"code"   = {name="Code",          role="codeblock", font="Courier New",
            size=10, lineheight=1.0}
```

`normal` ohne weitere Attribute bedeutet: vollständig vom eingebauten Default
übernommen. Felder die dem eingebauten Default entsprechen werden weggelassen.

Felder:
- `name` – angezeigter Name im UI (optional)
- `role` – semantische Rolle aus dem MD-Vokabular (optional): `h1`–`h6`, `body`, `blockquote`, `codeblock`, `bullet`, `ordered`
- `font`, `size`, `bold`, `italic` – Schriftattribute
- `lineheight` – Zeilenabstand als Faktor
- `space_before`, `space_after` – Abstand vor/nach Absatz in Punkten
- `indent` – Einzug in mm
- `align` – Ausrichtung: `left`, `right`, `center`, `block`

### [liststyles]

Benannte Listen- und Aufzählungsstile.

```
[liststyles]
"bullet"  = {name="Aufzählung", marker="•",  indent=6, hanging=3}
"ordered" = {name="Nummeriert", marker="1.", indent=6, hanging=3}
```

Felder:
- `name` – angezeigter Name im UI (optional)
- `marker` – Aufzählungszeichen oder Nummerierungsformat
- `indent` – Gesamteinzug in mm
- `hanging` – hängender Einzug in mm

### [document]

Der Dokumentinhalt als kanonischer TexelTree. Groups sind aufgelöst.
Container-Separatoren sind versteckt.

Die Sektion beginnt optional mit `PROPS`, gefolgt von den Texel-Elementen
und abgeschlossen durch `ENDMARK`.

```
[document]
PROPS({author="Ada Lovelace", paper="A4"})
T("Einleitung")
NL({base="h1"})
T("Dies ist ein normaler Absatz mit ")
T("fettem Text", {bold})
T(" darin.")
NL({base="normal"})
T("Zweiter Absatz, leicht eingerückt.")
NL({base="normal", indent=10})
ENDMARK({base="normal"})
```

---

## Element-Referenz

### T – Text

```
T("text")
T("text", {style-attribute, ...})
```

Trägt Textinhalt und optionale Zeichenstil-Overrides. Overrides werden auf
den Zeichenstil des umgebenden Absatzes addiert.

Beispiele:
```
T("normaler Text")
T("fett", {bold})
T("rot und kursiv", {color="red", italic})
T("referenzierter Stil", {charstyle="code"})
```

### NL – NewLine

```
NL
NL({base="style-id"})
NL({base="style-id", override-attribute, ...})
```

Absatzabschluss. Trägt den Absatzstil des vorangehenden Absatzes.
`base` verweist auf eine ID aus `[basestyles]`. Weitere Felder sind
lokale Overrides die auf den Basestyle addiert werden.

Beispiele:
```
NL
NL({base="normal"})
NL({base="normal", lineheight=1.5})
NL({base="normal", align="block", indent=10})
```

### PROPS

```
PROPS({key="value", key=number, ...})
```

Optionale Dokumenteigenschaften. Steht als erster Eintrag in der
`[document]`-Sektion, vor allen Texel-Elementen. Nur Werte, die vom
eingebauten Default abweichen, werden gespeichert.

Unterstützte Felder:

| Feld            | Typ    | Default  | Beschreibung                              |
|-----------------|--------|----------|-------------------------------------------|
| `title`         | String | `""`     | Dokumenttitel                             |
| `author`        | String | `""`     | Autor                                     |
| `paper`         | String | `"A4"`   | Papierformat: `"A4"`, `"Letter"`, `"custom"` |
| `paper_width`   | Zahl   | 595.28   | Breite in Punkten (nur bei `paper="custom"`) |
| `paper_height`  | Zahl   | 841.89   | Höhe in Punkten (nur bei `paper="custom"`) |
| `margin_top`    | Zahl   | 170.08   | Rand oben in Punkten                      |
| `margin_right`  | Zahl   | 170.08   | Rand rechts in Punkten                    |
| `margin_bottom` | Zahl   | 170.08   | Rand unten in Punkten                     |
| `margin_left`   | Zahl   | 170.08   | Rand links in Punkten                     |

Beispiele:
```
PROPS({author="Ada Lovelace", title="Mein Dokument"})
PROPS({paper="Letter", margin_left=56.69, margin_right=56.69})
PROPS({paper="custom", paper_width=419.53, paper_height=595.28})
```

### ENDMARK

```
ENDMARK
ENDMARK({base="style-id"})
ENDMARK({base="style-id", override-attribute, ...})
```

Abschluss des letzten Absatzes. Trägt denselben Inhalt wie NL, steht aber
außerhalb des TexelTree. Jedes Dokument hat genau eine ENDMARK, am Ende
der `[document]`-Sektion.

### S – Single

```
S("char")
S("char", {style-attribute, ...})
```

Atomares Einzelelement für Sonderzeichen, Bilder, und andere
nicht-text Inhalte. Länge ist immer 1.

### C – Container

```
C("type",
  slot1,
  slot2,
  ...
)
```

Strukturiertes Element das seinen Inhalt visuell umrahmt oder transformiert.
Slots können einen optionalen Style-Präfix tragen:

```
C("frac",
  T("Zähler"),
  T("Nenner")
)

C("table",
  {align="left"}:  T("Zelle 1"),
  {align="right"}: T("Zelle 2")
)
```

---

## Style-Syntax

Style-Blöcke verwenden die Notation `{key, key="value", key=number}`:

```
{bold}                          # boolesches Flag
{bold, italic}                  # mehrere Flags
{font="Arial"}                  # String-Wert
{size=12}                       # numerischer Wert
{bold, color="red", size=12}    # kombiniert
```

---

## IDs und Rollen

Style-IDs sind stabile Bezeichner die im TexelTree referenziert werden.
Sie ändern sich nicht. Während der Entwicklung können sprechende IDs
verwendet werden (`"normal"`, `"h1"`); im produktiven Einsatz werden
sie automatisch generiert (`"a3f9"`).

Die Rolle ist eine semantische Eigenschaft des Styles, nicht des Absatzes.
Sie kann sich ändern ohne dass der TexelTree angefasst werden muss.

```
# Vorher:
"a3f9" = {name="Meine Überschrift", role="h2", ...}

# Nachher (Rolle geändert, ID stabil):
"a3f9" = {name="Meine Überschrift", role="h1", ...}

# TexelTree unverändert:
NL({base="a3f9"})
```

---

## Vollständiges Beispiel

```
# Beispieldokument
# Erstellt mit MiniWord

[charstyles]
"em"   = {name="Hervorhebung", role="bold", bold}
"code" = {name="Code",         role="code", font="Courier New", size=10}

[basestyles]
"normal" = {name="Normal"}
"h1"     = {name="Überschrift 1", role="h1", size=18, bold,
            space_before=12, space_after=6}
"h2"     = {name="Überschrift 2", role="h2", size=14, bold,
            space_before=8,  space_after=4}

[liststyles]
"bullet" = {name="Aufzählung", marker="•", indent=6, hanging=3}

[document]
PROPS({author="Ada Lovelace", title="Einführung", paper="A4"})
T("Einführung")
NL({base="h1"})
T("Dies ist ein Absatz mit ")
T("hervorgehobenem Text", {charstyle="em"})
T(" und weiter.")
NL({base="normal"})
T("Zweiter Absatz.")
NL({base="normal", lineheight=1.5})
ENDMARK({base="normal"})
```

---

## Designentscheidungen

**Warum nicht Markdown?**
Markdown kann Absatzstile, Zeilenabstand, Einzüge und benannte Styles nicht
repräsentieren. Ein Roundtrip wäre verlustbehaftet.

**Warum keine Style-Hierarchie?**
Words Stil-Vererbung erzeugt in der Praxis unübersichtliche Abhängigkeiten.
TXL verwendet flache Basestyles mit lokalen Overrides – deterministisch
und ohne versteckte Abhängigkeiten.

**Warum Delta-Styles statt vollständiger Styles?**
Vollständige Styles wären redundant und schwer lesbar – die meisten Attribute
entsprechen dem Default. Delta-Styles sind kompakt und zeigen auf einen Blick,
was an einem Stil besonders ist.

**Eingebauter Default als fester Fallback**
Der eingebaute Default (hardcodiert in der Anwendung) ist unveränderlich und
dient als ultimativer Fallback – analog zu den Browser-Defaultstyles in CSS.
Er ist nicht im Dokument gespeichert. Referenziert ein Absatz einen
unbekannten oder gelöschten Stil, greift automatisch der eingebaute Default.
Dadurch ist das Format robust gegenüber fehlenden oder gelöschten Styles.

**Warum IDs statt Namen als Referenz?**
Der User kann einen Style umbenennen oder seine Rolle ändern ohne dass
der TexelTree angefasst werden muss. Die ID ist die stabile Schnittstelle.

**Warum Groups nicht im Format?**
Groups sind semantisch neutral – sie dienen nur der internen Balancierung.
Im Austauschformat sind sie bedeutungslos und werden weggelassen.

---

*Ende der Formatdokumentation v0.1*
