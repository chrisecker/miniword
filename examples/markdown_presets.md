# Introduction

This document is a playground for the predefined Markdown formats. Choose
an entry from *Markdown ▸ Predefined* and watch how headings, paragraphs,
code, quotes and lists change. Each action is a single undo step, so you
can switch back and forth with *Undo* and compare.

Long paragraphs show the effect of justification and hyphenation best.
Typographical considerations, internationalization requirements and
straightforward implementation strategies compete with each other when a
word processor has to decide where a line should be broken. Without
hyphenation, justified text often gets uncomfortably wide gaps between
words; with hyphenation, the right edge stays calm and the spacing even.

A second paragraph makes the difference between *space between
paragraphs* and *first-line indent* visible. Books usually indent the
first line and leave no gap, while reports and web pages prefer a gap
and no indent.

## Background

The formats differ in font, size, line spacing and a few features:

- **GitHub** – sans serif, 12 pt, quote with a bar on the left
- **GitHub Small** – the same at 10 pt
- **Report** – serif, justified and hyphenated, header with title and
  chapter
- **Compact** – small and dense, for long texts
- **Book** – serif, justified, every chapter on a new page
- **Technical** – numbered sections and framed code

> A quote shows the difference between a bar on the left and a grey
> background. The box should lie on the text edges, with the text
> inside.

### Details

Steps to try:

1. Open this file.
2. Choose *Markdown ▸ Predefined ▸ Technical*.
3. Look at the section numbers and the code frame below.
4. Remove the section numbers with *Markdown ▸ Section numbers ▸ Remove*.

# Code

Code is set in a monospace font and is never hyphenated or justified,
whatever the format says:

```
def fibonacci(n):
    """The first n Fibonacci numbers."""
    a, b = 0, 1
    result = []
    for _ in range(n):
        result.append(a)
        a, b = b, a + b
    return result
```

Inline code such as `fibonacci(10)` stays in the running text.

## A longer listing

```
class Stack:
    def __init__(self):
        self.items = []

    def push(self, item):
        self.items.append(item)

    def pop(self):
        return self.items.pop()

    def __len__(self):
        return len(self.items)
```

The frame around the listing comes from *Code frame*; the grey
background is always there.

## Headings at the end of a page

Headings keep with the next paragraph: a heading never stands alone at
the bottom of a page. Change the font size with *Markdown ▸ Size* to move
the page breaks and watch the headings.

# Conclusion

With *Chapters on new page* every top-level heading starts a new page, as
in a book. Page numbers appear in the footer; *Markdown ▸ Page numbers ▸
Remove* takes them away.

## Summary

| Format       | Font       | Size  | Justified |
|--------------|------------|-------|-----------|
| GitHub       | Sans serif | 12 pt | no        |
| Report       | Serif      | 12 pt | yes       |
| Compact      | Sans serif | 10 pt | no        |
| Book         | Serif      | 11 pt | yes       |
| Technical    | Sans serif | 11 pt | no        |

> The best format is the one that suits the reader.
