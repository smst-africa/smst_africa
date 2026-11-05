"""A small PDF writer.

SmSt Africa does not carry a PDF library, so the reports are written by hand.
Only what the reports need is here: pages of text, rules, filled rectangles and
tables. The output opens in any reader.
"""

from __future__ import annotations

import zlib
from datetime import date, datetime
from decimal import Decimal

A4_WIDTH = 595
A4_HEIGHT = 842

# Widths of the Helvetica and Helvetica-Bold glyphs, in 1/1000 of the size.
# They let the writer align a column of figures to the right.
_REGULAR_WIDTHS = {
    " ": 278, "!": 278, '"': 355, "#": 556, "$": 556, "%": 889, "&": 667,
    "'": 191, "(": 333, ")": 333, "*": 389, "+": 584, ",": 278, "-": 333,
    ".": 278, "/": 278, ":": 278, ";": 278, "<": 584, "=": 584, ">": 584,
    "?": 556, "@": 1015, "[": 278, "\\": 278, "]": 278, "^": 469, "_": 556,
    "`": 333, "{": 334, "|": 260, "}": 334, "~": 584,
    "A": 667, "B": 667, "C": 722, "D": 722, "E": 667, "F": 611, "G": 778,
    "H": 722, "I": 278, "J": 500, "K": 667, "L": 556, "M": 833, "N": 722,
    "O": 778, "P": 667, "Q": 778, "R": 722, "S": 667, "T": 611, "U": 722,
    "V": 667, "W": 944, "X": 667, "Y": 667, "Z": 611,
    "a": 556, "b": 556, "c": 500, "d": 556, "e": 556, "f": 278, "g": 556,
    "h": 556, "i": 222, "j": 222, "k": 500, "l": 222, "m": 833, "n": 556,
    "o": 556, "p": 556, "q": 556, "r": 333, "s": 500, "t": 278, "u": 556,
    "v": 500, "w": 722, "x": 500, "y": 500, "z": 500,
}
for _digit in "0123456789":
    _REGULAR_WIDTHS[_digit] = 556

_BOLD_WIDTHS = {
    " ": 278, "!": 333, '"': 474, "#": 556, "$": 556, "%": 889, "&": 722,
    "'": 238, "(": 333, ")": 333, "*": 389, "+": 584, ",": 278, "-": 333,
    ".": 278, "/": 278, ":": 333, ";": 333, "<": 584, "=": 584, ">": 584,
    "?": 611, "@": 975, "[": 333, "\\": 278, "]": 333, "^": 584, "_": 556,
    "`": 333, "{": 389, "|": 280, "}": 389, "~": 584,
    "A": 722, "B": 722, "C": 722, "D": 722, "E": 667, "F": 611, "G": 778,
    "H": 722, "I": 278, "J": 556, "K": 722, "L": 611, "M": 833, "N": 722,
    "O": 778, "P": 667, "Q": 778, "R": 722, "S": 667, "T": 611, "U": 722,
    "V": 667, "W": 944, "X": 667, "Y": 667, "Z": 611,
    "a": 556, "b": 611, "c": 556, "d": 611, "e": 556, "f": 333, "g": 611,
    "h": 611, "i": 278, "j": 278, "k": 556, "l": 278, "m": 889, "n": 611,
    "o": 611, "p": 611, "q": 611, "r": 389, "s": 556, "t": 333, "u": 611,
    "v": 556, "w": 778, "x": 556, "y": 556, "z": 500,
}
for _digit in "0123456789":
    _BOLD_WIDTHS[_digit] = 556


def text_width(value: str, size: float, bold: bool = False) -> float:
    table = _BOLD_WIDTHS if bold else _REGULAR_WIDTHS
    total = 0
    for character in value:
        total += table.get(character, 556)
    return total * size / 1000.0


def fit_text(value: str, size: float, max_width: float, bold: bool = False) -> str:
    """Shorten a value so that it fits the space it was given."""
    if text_width(value, size, bold) <= max_width:
        return value
    trimmed = value
    while trimmed and text_width(trimmed + "...", size, bold) > max_width:
        trimmed = trimmed[:-1]
    return trimmed + "..."


def escape(value: str) -> str:
    value = sanitize(value)
    return (
        value.replace("\\", r"\\")
        .replace("(", r"\(")
        .replace(")", r"\)")
        .replace("\r", " ")
        .replace("\n", " ")
    )


def sanitize(value: str) -> str:
    """Keep the text inside the simple encoding the writer uses."""
    replacements = {
        "—": "-",
        "–": "-",
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        "•": "-",
        "·": "-",
        " ": " ",
        "…": "...",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    return value.encode("latin-1", "replace").decode("latin-1")


def as_count(value) -> str:
    """A quantity, without the decimals when it is a whole number."""
    if value is None or value == "":
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return as_text(value)
    if number == int(number):
        return f"{int(number):,}"
    return f"{number:,.2f}"


def as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (datetime, date)):
        if isinstance(value, datetime):
            return value.strftime("%d %b %Y, %H:%M")
        return value.strftime("%d %b %Y")
    if isinstance(value, Decimal):
        return f"{value:,.2f}"
    if isinstance(value, float):
        return f"{value:,.2f}"
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


class Page:
    """One page of a document. The origin sits at the top left."""

    def __init__(self, width: int = A4_WIDTH, height: int = A4_HEIGHT):
        self.width = width
        self.height = height
        self.operations: list[str] = []

    def text(
        self,
        x: float,
        y: float,
        value: str,
        size: float = 10,
        bold: bool = False,
        color=(0, 0, 0),
        align: str = "left",
    ):
        value = as_text(value)
        if not value:
            return
        if align == "right":
            x -= text_width(value, size, bold)
        elif align == "center":
            x -= text_width(value, size, bold) / 2

        red, green, blue = (component / 255 for component in color)
        font = "F2" if bold else "F1"
        baseline = self.height - y - size
        self.operations.append(
            f"BT {red:.3f} {green:.3f} {blue:.3f} rg "
            f"/{font} {size} Tf 1 0 0 1 {x:.2f} {baseline:.2f} Tm "
            f"({escape(value)}) Tj ET"
        )

    def rect(self, x: float, y: float, width: float, height: float, color=(255, 255, 255)):
        red, green, blue = (component / 255 for component in color)
        self.operations.append(
            f"{red:.3f} {green:.3f} {blue:.3f} rg "
            f"{x:.2f} {self.height - y - height:.2f} {width:.2f} {height:.2f} re f"
        )

    def line(self, x1: float, y1: float, x2: float, y2: float, color=(220, 220, 220), width: float = 0.6):
        red, green, blue = (component / 255 for component in color)
        self.operations.append(
            f"{red:.3f} {green:.3f} {blue:.3f} RG {width} w "
            f"{x1:.2f} {self.height - y1:.2f} m {x2:.2f} {self.height - y2:.2f} l S"
        )

    def stream(self) -> bytes:
        return "\n".join(self.operations).encode("latin-1", "replace")


class Document:
    """A PDF document made of pages."""

    def __init__(self, title: str = "SmSt Africa", margin: int = 42):
        self.title = title
        self.margin = margin
        self.pages: list[Page] = []

    @property
    def page(self) -> Page:
        if not self.pages:
            self.add_page()
        return self.pages[-1]

    def add_page(self) -> Page:
        page = Page()
        self.pages.append(page)
        return page

    def to_bytes(self) -> bytes:
        objects: list[bytes] = []

        def add(body: bytes) -> int:
            objects.append(body)
            return len(objects)

        # The content stream of every page, then the two fonts.
        content_ids = []
        for page in self.pages:
            stream = page.stream()
            content_ids.append(
                add(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
            )

        font_regular = add(
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
        )
        font_bold = add(
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"
        )

        # The page tree comes next, and each page object follows it.
        pages_id = len(objects) + 1
        page_ids = [pages_id + 1 + index for index in range(len(self.pages))]

        kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
        objects.append(
            f"<< /Type /Pages /Kids [ {kids} ] /Count {len(page_ids)} >>".encode(
                "latin-1"
            )
        )

        for index, page in enumerate(self.pages):
            objects.append(
                (
                    f"<< /Type /Page /Parent {pages_id} 0 R "
                    f"/MediaBox [0 0 {page.width} {page.height}] "
                    f"/Resources << /Font << /F1 {font_regular} 0 R /F2 {font_bold} 0 R >> >> "
                    f"/Contents {content_ids[index]} 0 R >>"
                ).encode("latin-1")
            )

        info_id = len(objects) + 1
        objects.append(
            f"<< /Title ({escape(self.title)}) /Producer (SmSt Africa) >>".encode(
                "latin-1", "replace"
            )
        )

        catalog_id = len(objects) + 1
        objects.append(f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode("latin-1"))

        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0]
        for index, body in enumerate(objects, start=1):
            offsets.append(len(out))
            out += f"{index} 0 obj\n".encode("latin-1") + body + b"\nendobj\n"

        xref_offset = len(out)
        out += f"xref\n0 {len(objects) + 1}\n".encode("latin-1")
        out += b"0000000000 65535 f \n"
        for offset in offsets[1:]:
            out += f"{offset:010d} 00000 n \n".encode("latin-1")
        out += (
            f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R "
            f"/Info {info_id} 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n"
        ).encode("latin-1")

        return bytes(out)
