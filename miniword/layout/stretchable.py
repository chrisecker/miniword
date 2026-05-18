from .boxes import Rect, Box, VBox, TextBox, find_text_pos
from .testdevice import TESTDEVICE


class StretchableText(Box):
    stretch = 0

    def __init__(self, strings, widths, height, depth, trailing_space,
                 style, device):
        self.device = device
        self.style = style
        self.items = tuple(zip(strings, widths))
        self.trailing_space = trailing_space  # width of trailing space character

        # Compute total dimensions
        self.widths = widths
        self.width  = sum(widths)
        self.height = height
        self.depth  = depth

    def __len__(self):
        return sum(len(item[0]) for item in self.items)

    def get_stretchability(self):
        n = len(self.items)
        if self.trailing_space > 0:
            return n - 1
        if not self.items[-1][0].endswith(' '):
            return n - 1
        return n

    def get_minwidth(self):
        # For debugging
        return sum(item[1] for item in self.items)

    def set_stretch(self, stretch):
        """Increases the total width by the given stretch value."""
        assert self.stretch == 0
        self.stretch = stretch
        self.width += stretch

    def stretch_to(self, newwidth):
        w = self.width - self.trailing_space
        assert w < newwidth
        self.set_stretch(newwidth - w)

    def draw(self, x, y, dc):
        self.device.set_style(self.style, dc)
        if self.stretch:
            unit_stretch = self.stretch / self.get_stretchability()
        else:
            unit_stretch = 0
        strings = [item[0] for item in self.items]
        self.device.draw_strings(strings, x, y, unit_stretch, dc)

    def find_x(self, i):
        # For testing
        measure = self.device.measure
        for j1, j2, x_, y_, text in self.iter_strings(0, 0):
            if j1 <= i <= j2:
                return x_ + measure(text[:i - j1], self.style)[0]

    def draw_selection(self, i1, i2, x, y, dc):
        measure = self.device.measure
        x1 = x
        x2 = x + self.width
        l = list(self.iter_strings(x, y))
        l.reverse()
        for j1, j2, x_, y_, text in l:
            if j1 <= i1 <= j2:
                x1 = x_ + measure(text[:i1 - j1], self.style)[0]
                break
        for j1, j2, x_, y_, text in l:
            if j1 <= i2 <= j2:
                x2 = x_ + measure(text[:i2 - j1], self.style)[0]
                break
        self.device.invert_rect(x1, y, x2 - x1, self.height + self.depth, dc)

    def get_rect(self, i, x0, y0):
        measure = self.device.measure
        i = max(0, i)
        i = min(len(self), i)
        for j1, j2, x_, y_, text in reversed(
                tuple(self.iter_strings(x0, y0))):
            if j1 <= i <= j2:
                x1 = x_ + measure(text[:i - j1], self.style)[0]
                x2 = x1 + measure('m', self.style)[0]
                return Rect(x1, y0, x2, y0 + self.height + self.depth)
        assert False

    def iter_strings(self, x, y):
        if self.stretch:
            s = self.get_stretchability()
            unit_stretch = self.stretch / s
        else:
            unit_stretch = 0

        i1 = 0
        for string, width in self.items:
            i2 = i1 + len(string)
            yield i1, i2, x, y, string
            x  += width + unit_stretch
            i1  = i2

    def set_marker(self, marker, offset):
        self.marker = marker
        self.offset = offset

    def dump(self):
        ax = 0
        for i1, i2, x, y, t in self.iter_strings(0, 0):
            print("[%i, %i]" % (i1, i2), x - ax, y, repr(t))
            ax = x

    def get_index(self, x, y):
        for i1, i2, x_, y_, string in reversed(
                tuple(self.iter_strings(0, 0))):
            if x >= x_:
                # x falls within this string segment
                return (
                    find_text_pos(x - x_, string, self.style, self.device)
                    + i1
                )
        return 0


def create_stretchtext(textbox, is_last=False):
    """
    Convert a TextBox into a StretchableText.

    Args:
        textbox: The original TextBox.
        is_last: If True, the trailing space is not stretchable.

    Returns:
        A new StretchableText instance.
    """
    text   = textbox.text
    device = textbox.device
    style  = textbox.style

    # Split text into fragments at spaces
    fragments = text.split(" ")

    if len(fragments) == 1:
        # No spaces found — no stretchability possible
        items  = [text]
        widths = [textbox.width]
    else:
        items  = []
        widths = []

        for i, fragment in enumerate(fragments):
            if i < len(fragments) - 1:
                fragment += " "
            elif not fragment:
                continue
            items.append(fragment)
            w, h, d = device.measure(fragment, style)
            widths.append(w)

    if is_last and items[-1].endswith(" "):
        trailing_space = device.measure(" ", style)[0]
    else:
        trailing_space = 0

    stretchbox = StretchableText(
        items, widths, textbox.height,
        textbox.depth, trailing_space, style, textbox.device,
    )
    assert "".join(items) == text
    return stretchbox


def get_stretchability(box):
    if isinstance(box, StretchableText):
        return box.get_stretchability()
    return 0


def get_trailing_space(box):
    if isinstance(box, StretchableText):
        return box.trailing_space
    return 0


def justify_line(l, width):
    """
    Build a justified line from a list of boxes.

    Converts TextBoxes into StretchableTexts and applies stretch so
    that the core width (excluding trailing space) equals the given
    width.

    Args:
        l:     List of boxes.
        width: Desired line width (excluding trailing space).

    Returns:
        List of boxes with stretch applied.
    """
    if not l:
        return []

    # Convert TextBoxes to StretchableTexts
    boxes = []
    for i, box in enumerate(l):
        is_last = (i == len(l) - 1)
        if isinstance(box, TextBox):
            stretchbox = create_stretchtext(box, is_last=is_last)
            assert stretchbox.width == stretchbox.get_minwidth()
            boxes.append(stretchbox)
        else:
            boxes.append(box)

    trailing_space = get_trailing_space(boxes[-1])
    current_width  = sum(box.width for box in boxes) - trailing_space

    if current_width >= width:
        # No scaling needed or possible
        return boxes

    stretch        = width - current_width
    stretchability = sum(get_stretchability(box) for box in boxes)
    if stretchability == 0:
        return boxes  # single word wider than line: leave as-is
    unit_stretch   = stretch / stretchability

    for box in boxes:
        s = get_stretchability(box)
        if not s:
            continue
        box.set_stretch(s * unit_stretch)

    new_width = sum(box.width for box in boxes) - trailing_space

    try:
        assert abs(new_width - width) < 0.1
    except AssertionError:
        print("old:", current_width)
        print("new:", new_width)
        print("target:", width)
        raise

    return boxes



def test_00():
    # Create a standard TextBox
    textbox = TextBox("Hello world example")

    # Convert to StretchableText — all spaces stretchable
    stretchbox = create_stretchtext(textbox, is_last=False)

    # Convert to StretchableText — trailing space not stretchable
    stretchbox = create_stretchtext(textbox, is_last=True)

    # Apply stretch
    stretchbox.set_stretch(20)


def test_01():
    "find_x"
    textbox   = TextBox("Hello world example")
    stretchbox = create_stretchtext(textbox, is_last=False)
    for i in range(len(textbox.text)):
        x = stretchbox.find_x(i)
        assert x == i


def test_02():
    "set_stretch"
    textbox1   = TextBox("Hello ")
    textbox2   = TextBox("world ")
    stretchbox1 = create_stretchtext(textbox1, is_last=False)
    stretchbox2 = create_stretchtext(textbox2, is_last=True)
    assert stretchbox1.width         == 6
    assert stretchbox1.trailing_space == 0
    assert stretchbox2.width         == 6
    assert stretchbox2.trailing_space == 1

    w = (stretchbox1.width + stretchbox2.width
         - stretchbox2.trailing_space)
    assert w == 11

    assert stretchbox1.get_stretchability() == 1
    assert stretchbox2.get_stretchability() == 0

    stretchbox1.set_stretch(10)
    assert stretchbox1.width         == 16
    assert stretchbox1.trailing_space == 0

    textbox    = TextBox("Hello world")
    stretchbox = create_stretchtext(textbox, is_last=True)
    assert stretchbox.get_stretchability() == 1
    assert stretchbox.trailing_space       == 0
    assert list(stretchbox.iter_strings(0, 0)) == \
        [(0, 6, 0, 0, 'Hello '), (6, 11, 6, 0, 'world')]

    w0 = stretchbox.width
    stretchbox.set_stretch(20)
    assert stretchbox.width         == w0 + 20
    assert stretchbox.trailing_space == 0
    assert list(stretchbox.iter_strings(0, 0)) == \
        [(0, 6, 0, 0, 'Hello '), (6, 11, 26, 0, 'world')]


def test_03():
    "justify_line"
    textbox1 = TextBox("Hello ")
    textbox2 = TextBox("world ")
    boxes = justify_line([textbox1, textbox2], 16)
    assert sum(box.width for box in boxes) == 17
    assert sum(box.width - box.trailing_space for box in boxes) == 16

    textbox1 = TextBox("Hello")
    textbox2 = TextBox(" world ")
    boxes = justify_line([textbox1, textbox2], 16)
    assert sum(box.width for box in boxes) == 17
    assert sum(box.width - box.trailing_space for box in boxes) == 16

    textbox1 = TextBox("Hello")
    textbox2 = TextBox("world ")
    # no inter-word space: returned unchanged (graceful degradation)
    boxes = justify_line([textbox1, textbox2], 20)
    assert sum(box.width for box in boxes) == 11

    textbox1 = TextBox("Hello")
    textbox2 = TextBox("world ")
    textbox3 = TextBox("! ")
    boxes = justify_line([textbox1, textbox2, textbox3], 20)
    assert sum(box.width for box in boxes) == 21
    assert sum(box.width - box.trailing_space for box in boxes) == 20

