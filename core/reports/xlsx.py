"""A small Excel writer.

SmSt Africa does not carry a spreadsheet library, so the workbooks are written
by hand as Office Open XML. The result is a normal .xlsx file that Excel,
LibreOffice and Numbers all open. Each app passes its own accent colours, so
the stock book and the finance book keep their own look.
"""

from __future__ import annotations

import io
import zipfile
from datetime import date, datetime
from decimal import Decimal

# Excel's serial date starts on 30 December 1899.
_EXCEL_EPOCH = date(1899, 12, 30)

# Style indexes available in the stylesheet written below.
STYLE_DEFAULT = 0
STYLE_HEADER = 1
STYLE_BOLD = 2
STYLE_NUMBER = 3
STYLE_DATE = 4
STYLE_TOTAL = 5
STYLE_TOTAL_NUMBER = 6


def escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def column_name(index: int) -> str:
    """0 becomes A, 25 becomes Z, 26 becomes AA."""
    name = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def serial_date(value) -> float:
    if isinstance(value, datetime):
        delta = value.date() - _EXCEL_EPOCH
        seconds = value.hour * 3600 + value.minute * 60 + value.second
        return delta.days + seconds / 86400
    return (value - _EXCEL_EPOCH).days


class Sheet:
    def __init__(self, title: str):
        self.title = title
        self.rows: list[list[tuple]] = []
        self.widths: list[float] = []
        self.freeze_rows = 0

    def set_widths(self, widths):
        self.widths = list(widths)

    def append(self, values, style=STYLE_DEFAULT):
        """Add a row. Each value may carry its own style as a tuple."""
        row = []
        for value in values:
            if isinstance(value, tuple) and len(value) == 2:
                row.append((value[0], value[1]))
            else:
                row.append((value, style))
        self.rows.append(row)
        return self

    def header(self, values):
        return self.append(values, style=STYLE_HEADER)

    def _cell_xml(self, reference: str, value, style: int) -> str:
        if value is None or value == "":
            return f'<c r="{reference}" s="{style}"/>'

        if isinstance(value, bool):
            return (
                f'<c r="{reference}" s="{style}" t="inlineStr">'
                f"<is><t>{'Yes' if value else 'No'}</t></is></c>"
            )

        if isinstance(value, (datetime, date)):
            return (
                f'<c r="{reference}" s="{STYLE_DATE}"><v>{serial_date(value):.5f}</v></c>'
            )

        if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
            return f'<c r="{reference}" s="{style}"><v>{value}</v></c>'

        return (
            f'<c r="{reference}" s="{style}" t="inlineStr">'
            f"<is><t xml:space=\"preserve\">{escape(str(value))}</t></is></c>"
        )

    def to_xml(self) -> str:
        parts = [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
        ]

        if self.widths:
            parts.append("<cols>")
            for index, width in enumerate(self.widths, start=1):
                parts.append(
                    f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>'
                )
            parts.append("</cols>")

        parts.append("<sheetData>")
        for row_index, row in enumerate(self.rows, start=1):
            parts.append(f'<row r="{row_index}">')
            for cell_index, (value, style) in enumerate(row):
                reference = f"{column_name(cell_index)}{row_index}"
                parts.append(self._cell_xml(reference, value, style))
            parts.append("</row>")
        parts.append("</sheetData>")

        if self.freeze_rows:
            parts.append(
                '<sheetViews><sheetView workbookViewId="0">'
                f'<pane ySplit="{self.freeze_rows}" topLeftCell="A{self.freeze_rows + 1}" '
                'activePane="bottomLeft" state="frozen"/>'
                "</sheetView></sheetViews>"
            )

        parts.append("</worksheet>")
        return "".join(parts)


class Workbook:
    def __init__(self, accent: str = "FFA65A17", title_color: str = "FF7A4A16"):
        self.sheets: list[Sheet] = []
        self.accent = accent
        self.title_color = title_color

    def add_sheet(self, title: str) -> Sheet:
        sheet = Sheet(title[:31] or "Sheet")
        self.sheets.append(sheet)
        return sheet

    def to_bytes(self) -> bytes:
        buffer = io.BytesIO()

        content_types = [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
            '<Default Extension="xml" ContentType="application/xml"/>',
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>',
        ]
        for index in range(1, len(self.sheets) + 1):
            content_types.append(
                f'<Override PartName="/xl/worksheets/sheet{index}.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            )
        content_types.append("</Types>")

        root_rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/>'
            "</Relationships>"
        )

        sheet_entries = "".join(
            f'<sheet name="{escape(sheet.title)}" sheetId="{index}" r:id="rId{index}"/>'
            for index, sheet in enumerate(self.sheets, start=1)
        )
        workbook_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f"<sheets>{sheet_entries}</sheets>"
            "</workbook>"
        )

        workbook_rels = [
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">',
        ]
        for index in range(1, len(self.sheets) + 1):
            workbook_rels.append(
                f'<Relationship Id="rId{index}" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                f'Target="worksheets/sheet{index}.xml"/>'
            )
        workbook_rels.append(
            f'<Relationship Id="rId{len(self.sheets) + 1}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
            'Target="styles.xml"/>'
        )
        workbook_rels.append("</Relationships>")

        styles_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<numFmts count="1"><numFmt numFmtId="164" formatCode="#,##0.00"/></numFmts>'
            '<fonts count="4">'
            '<font><sz val="11"/><color theme="1"/><name val="Calibri"/></font>'
            '<font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>'
            '<font><b/><sz val="11"/><color theme="1"/><name val="Calibri"/></font>'
            f'<font><b/><sz val="12"/><color rgb="{self.title_color}"/><name val="Calibri"/></font>'
            "</fonts>"
            '<fills count="3">'
            '<fill><patternFill patternType="none"/></fill>'
            '<fill><patternFill patternType="gray125"/></fill>'
            f'<fill><patternFill patternType="solid"><fgColor rgb="{self.accent}"/>'
            '<bgColor indexed="64"/></patternFill></fill>'
            "</fills>"
            '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="7">'
            '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
            '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1">'
            '<alignment vertical="center"/></xf>'
            '<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
            '<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
            '<xf numFmtId="14" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
            '<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1">'
            f'<alignment vertical="top"><border><top style="thin"><color rgb="{self.accent}"/></top></border></alignment></xf>'
            '<xf numFmtId="164" fontId="2" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyFont="1">'
            f'<alignment vertical="top"><border><top style="thin"><color rgb="{self.accent}"/></top></border></alignment></xf>'
            "</cellXfs>"
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
            "</styleSheet>"
        )

        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("[Content_Types].xml", "".join(content_types))
            archive.writestr("_rels/.rels", root_rels)
            archive.writestr("xl/workbook.xml", workbook_xml)
            archive.writestr("xl/_rels/workbook.xml.rels", "".join(workbook_rels))
            archive.writestr("xl/styles.xml", styles_xml)
            for index, sheet in enumerate(self.sheets, start=1):
                archive.writestr(f"xl/worksheets/sheet{index}.xml", sheet.to_xml())

        return buffer.getvalue()
