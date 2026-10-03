"""Excel TEXT() 공개 캐시 입력을 합성 XLSX에 넣어 실제 리더 출력을 대조한다."""
import argparse
from collections import Counter
import hashlib
from html import escape
import json
from pathlib import Path
import sys
import zipfile


NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _write_workbook(path, rows, date_1904):
    formats = []
    xfs = ['<xf numFmtId="0"/>']
    sheet_rows = []
    for index, item in enumerate(rows, start=1):
        formats.append('<numFmt numFmtId="%d" formatCode="%s"/>' %
                       (163 + index, escape(item["format"], quote=True)))
        xfs.append('<xf numFmtId="%d"/>' % (163 + index))
        kind = item["input_type"]
        value = escape(item["raw"] or "")
        if kind in ("n", ""):
            cell = '<c r="A%d" s="%d"><v>%s</v></c>' % (index, index, value)
        elif kind == "b":
            cell = '<c r="A%d" s="%d" t="b"><v>%s</v></c>' % (index, index, value)
        else:
            cell = '<c r="A%d" s="%d" t="inlineStr"><is><t>%s</t></is></c>' % (
                index, index, value)
        sheet_rows.append('<row r="%d">%s</row>' % (index, cell))
    workbook = (f'<workbook xmlns="{NS}" xmlns:r="{REL}">'
                + ('<workbookPr date1904="1"/>' if date_1904 else '') + '<sheets>'
                '<sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>')
    styles = (f'<styleSheet xmlns="{NS}"><numFmts count="{len(formats)}">'
              + "".join(formats) + '</numFmts><cellXfs count="%d">' % len(xfs)
              + "".join(xfs) + '</cellXfs></styleSheet>')
    sheet = f'<worksheet xmlns="{NS}"><sheetData>' + "".join(sheet_rows) + '</sheetData></worksheet>'
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as target:
        target.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/'
                        'package/2006/content-types"><Default Extension="rels" '
                        'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                        '<Default Extension="xml" ContentType="application/xml"/></Types>')
        target.writestr("_rels/.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/'
                        'package/2006/relationships"><Relationship Id="rId1" '
                        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
                        'officeDocument" Target="xl/workbook.xml"/></Relationships>')
        target.writestr("xl/workbook.xml", workbook)
        target.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.'
                        'openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" '
                        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
                        'worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        target.writestr("xl/styles.xml", styles)
        target.writestr("xl/worksheets/sheet1.xml", sheet)


def snapshot(code_root, source, output, temporary):
    rows = json.loads(source.read_text())
    try:
        sys.path.insert(0, str(code_root.resolve()))
        from dochan.ooxml.xlsx import XLSXReader
        groups = {}
        for index, item in enumerate(rows):
            groups.setdefault((item["file"], item["date1904"]), []).append((index, item))
        results = [None] * len(rows)
        errors = []
        for (_, date_1904), indexed in groups.items():
            _write_workbook(temporary, [item for _, item in indexed], date_1904)
            doc = XLSXReader().read(str(temporary))
            errors.extend(doc.errors)
            cells = {cell.provenance.cell: cell.text for table in doc.find_all("table")
                     for row in table.rows for cell in row if cell.provenance}
            for local_index, (index, item) in enumerate(indexed, start=1):
                actual = cells.get("A%d" % local_index, "")
                results[index] = {"file": item["file"], "cell": item["cell"],
                                  "input_type": item["input_type"],
                                  "exact": actual == item["excel"],
                                  "hash": hashlib.sha256(actual.encode("utf-8", "surrogatepass")).hexdigest()}
        output.write_text(json.dumps({"rows": results, "errors": errors}, ensure_ascii=False) + "\n")
        print("rows", len(results), "exact", sum(row["exact"] for row in results),
              "errors", len(errors))
    finally:
        temporary.unlink(missing_ok=True)


def compare(before, after):
    old = json.loads(before.read_text())["rows"]
    new = json.loads(after.read_text())["rows"]
    counts = Counter(total=len(old))
    for left, right in zip(old, new):
        if any(left[key] != right[key] for key in ("file", "cell", "input_type")):
            raise ValueError("input rows differ")
        counts["before_exact"] += left["exact"]
        counts["after_exact"] += right["exact"]
        counts["gained"] += not left["exact"] and right["exact"]
        counts["lost"] += left["exact"] and not right["exact"]
        counts["changed"] += left["hash"] != right["hash"]
        if left["input_type"] not in ("", "n"):
            counts["non_numeric"] += 1
    print(dict(counts))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("snapshot")
    for name in ("code_root", "source", "output", "temporary"):
        p.add_argument(name, type=Path)
    p = sub.add_parser("compare")
    p.add_argument("before", type=Path)
    p.add_argument("after", type=Path)
    args = parser.parse_args()
    if args.command == "snapshot":
        snapshot(args.code_root, args.source, args.output, args.temporary)
    else:
        compare(args.before, args.after)


if __name__ == "__main__":
    main()
