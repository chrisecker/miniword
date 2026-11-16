---
title: "On the Typesetting of Small Documents"
author:
  - name: Ada Example
    affiliation: Example University
  - name: B. Sample
date: 2026-11-16
lang: en-US
abstract: |
  We study how small documents are typeset.
  The results are encouraging.
bibliography: references.bib
link-citations: true
---

# Introduction {#sec:intro}

Typesetting has a long history [@knuth1984, p. 12; @lamport1994]. As
@doe2020 shows, the problem is not solved [see -@doe2020, ch. 3].

The energy is $E = mc^2$ and water is H~2~O; the area grows with r^2^.

$$
\int_0^1 x^2 \, dx = \frac{1}{3}
$$ {#eq:integral}

See @eq:integral and [@fig:layout].

![A page layout.](figures/layout.png){#fig:layout width=60%}

::: {.note}
This is a note in a fenced div.
:::

Term
:   Definition of the term.

| Line one of a line block
| Line two, kept as it is

Here is an inline note.^[The note text.] And [small caps]{.smallcaps}.

```{=latex}
\newpage
```

  Size   Value
  ------ -------
  small  1
  large  100

Table: A simple table.

# References {-}

::: {#refs}
:::
