# All Markdown constructs

Every construct Miniword supports, written as Miniword saves it: loading and saving this file gives the same text (test in plugins/mdfilter.py).

## Text

Plain text with **bold**, *italic*, ***bold italic***, ~~struck~~, `code`, ``a `tick` inside``, H~2~O and x^2^.

**Bold over `code` and text**, a [link](https://example.org) and a [link with **bold** part](https://example.org/b).

Escaped characters: \*not italic\*, \[no link\], snake_case and \_x\_ and a # hash.

Special characters: & © ®, and a hard line break here:\
the next line of the same paragraph.

A footnote reference[^1] and a second one[^2].

An image (linked file): ![a red square](red.png)

## Headings

### Level 3

#### Level 4

##### Level 5

###### Level 6

## Lists

- Bullet
- Bullet with **bold**
  - Nested bullet
    - Nested deeper
- Back on top

Numbered, also nested:

1. First
2. Second
   - Bullet under a number
3. Third

A list starting at three:

3. Starting at three
4. Four

A task list:

- [ ] Open task
- [x] Done task

## Quotes and alerts

> A quote.
>
> Its second paragraph.

> [!NOTE]
> A note.

> [!TIP]
> A tip.

> [!IMPORTANT]
> Important.

> [!WARNING]
> A warning.

> [!CAUTION]
> Caution.

## Code

```
def hello():
    print('Hello')
```

## Table

| Left  | Center | Right | Default |
| :---- | :----: | ----: | ------- |
| a     | b      | c     | d       |
| **1** | `2`    | 3     | 4       |

## Rule

---

The end.

[^1]: The first footnote.
[^2]: The second footnote.
