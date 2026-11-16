# tinytool

[![Build](https://img.shields.io/badge/build-passing-green.svg)](https://example.org/ci)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A small command line tool for converting things. See the [docs][docs] or
visit www.example.org for details.

> [!NOTE]
> Requires Python 3.10 or newer.

## Installation

```bash
pip install tinytool
```

## Usage

1. Install the package.
2. Run `tinytool --help`:
   ```
   tinytool [options] FILE
   ```
3. Read the output.

- Supported formats:
  - Markdown
  - HTML
- Press <kbd>Ctrl</kbd>+<kbd>C</kbd> to stop.

| Option | Default | Description |
|:-------|:-------:|------------:|
| `-v`   | off     | verbose     |
| `-o`   | stdout  | output file |

## Roadmap

- [x] Basic conversion
- [ ] Plugins :tada:
- [ ] ~~Windows 7 support~~

<details>
<summary>Changelog</summary>

- 0.2: faster
- 0.1: first release

</details>

<!-- TODO: add screenshots -->

Contributions are welcome, see <https://example.org/contributing>.[^1]

[^1]: Please open an issue first.

[docs]: https://example.org/docs "Documentation"
