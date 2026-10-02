"""공개 HWPX 코퍼스의 기능별 독립 기대값과 파서 출력을 비교한다.

실행: /usr/bin/python3 -m scripts.probe_hwpx_features <공개 hwpx 폴더>
표본은 읽기만 하며, 기대값은 공개 XML 관찰값 또는 기존 고정 gold다.
"""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

from lxml import etree

from dochan.hwpx.parser import HWPXParser
from dochan.hwpx.charts import parse_chart_xml
from dochan.model.document import Paragraph
from dochan.model.table import Table


C = "{http://schemas.openxmlformats.org/drawingml/2006/chart}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def record(path, feature, expected, actual, errors=0):
    return dict(feature=feature, sample=path.name,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                expected=expected, actual=actual, errors=errors,
                passed=expected == actual and errors == 0)


def validate(base):
    results = []
    revision = base / "hwpxlib-ChangeTrack.hwpx"
    if revision.is_file():
        for mode, expected in [("preserve", "변경 추적 \t인간은"),
                               ("final", "변경 \t인간은"),
                               ("original", "변경 추적 \t")]:
            doc = HWPXParser().parse(revision, revision_mode=mode, include_assets=False)
            actual = doc.find_all("paragraph")[0].text
            results.append(record(revision, "revision:" + mode, expected, actual, len(doc.errors)))
    forms = {
        "form-01.hwpx": ["명령 단추", "[x]선택 상자", "[ ]라디오 단추", "여기에 입력"],
        "form-02.hwpx": ["명령 단추", "[x]선택 상자", "[ ]라디오 단추", "여기에 입력"],
        "SimpleEdit.hwpx": [],
        "hwp2hwpx-from_12.hwpx": ["테스트"],
    }
    for name, expected in forms.items():
        path = base / name
        if not path.is_file():
            continue
        doc = HWPXParser().parse(path, include_assets=False)
        actual = [p.text for p in doc.sections[0].elements if isinstance(p, Paragraph)]
        results.append(record(path, "controls", expected, actual, len(doc.errors)))
    # 26 public checkbox values are compared in document order against raw XML.
    path = base / "rhwp-36341511_masked.hwpx"
    if path.is_file():
        expected = []
        with zipfile.ZipFile(path) as archive:
            for name in sorted(archive.namelist()):
                if not name.startswith("Contents/section") or not name.endswith(".xml"):
                    continue
                root = etree.fromstring(archive.read(name), etree.XMLParser(resolve_entities=False, no_network=True))
                for node in root.iter("{http://www.hancom.co.kr/hwpml/2011/paragraph}checkBtn"):
                    expected.append(("[x]" if node.get("value") == "CHECKED" else "[ ]") + node.get("caption", ""))
        doc = HWPXParser().parse(path, include_assets=False)
        actual = [run.text for para in doc.find_all("paragraph") for run in para.runs
                  if run.text in {"[x]선택 상자", "[ ]선택 상자"}]
        results.append(record(path, "controls:checkbox-state", expected, actual, len(doc.errors)))
    for name, prefix in [("sample-outline-list.hwpx", 0),
                         ("sample-mixed-lists-with-outline.hwpx", 11)]:
        path = base / name
        if not path.is_file():
            continue
        doc = HWPXParser().parse(path, include_assets=False)
        actual = [p.heading_level for p in doc.sections[0].elements if isinstance(p, Paragraph)]
        expected = [0] * prefix + [1, 2, 3, 2, 1]
        results.append(record(path, "styles:headings", expected, actual, len(doc.errors)))
    for name, kind, label in [("2차원원형.hwpx", "pieChart", "pie"),
                              ("꺽은선형.hwpx", "lineChart", "line")]:
        path = base / name
        if not path.is_file():
            continue
        with zipfile.ZipFile(path) as archive:
            raw = archive.read("Chart/chart1.xml")
        root = etree.fromstring(raw, etree.XMLParser(resolve_entities=False, no_network=True))
        group = root.find(C + "chart/" + C + "plotArea/" + C + kind)
        expected = []
        for series in sorted(group.findall(C + "ser"),
                             key=lambda s: int(s.find(C + "order").get("val"))):
            series_name = series.findtext(C + "tx/" + C + "strRef/" + C + "strCache/" + C + "pt/" + C + "v")
            columns = []
            for cache_path in [C + "cat/" + C + "strRef/" + C + "strCache",
                               C + "val/" + C + "numRef/" + C + "numCache"]:
                cache = series.find(cache_path)
                points = {int(point.get("idx")): point.findtext(C + "v")
                          for point in cache.findall(C + "pt")}
                count = int(cache.find(C + "ptCount").get("val"))
                columns.append([points[index] for index in range(count)])
            expected.append(["Chart type: " + label if not expected else "",
                             [["범주", series_name]] + list(map(list, zip(*columns)))])
        elements, warnings = parse_chart_xml(raw)
        actual = [[table.caption_text, [[cell.text for cell in row] for row in table.rows]]
                  for table in elements if isinstance(table, Table)]
        results.append(record(path, "charts:cached-data", expected, actual, len(warnings)))
    # This public chart has a real explicit title and stored caches. The title
    # is independently transcribed from its c:title/c:tx/a:rich text nodes.
    path = base / "14_chart.hwpx"
    if path.is_file():
        with zipfile.ZipFile(path) as archive:
            raw = archive.read("Chart/chart1.xml")
        elements, warnings = parse_chart_xml(raw)
        actual = [elements[0].text, elements[0].heading_level,
                  [item.caption_side for item in elements if isinstance(item, Table)],
                  [item.caption_text for item in elements if isinstance(item, Table)]]
        # The actual c:catAx/c:valAx have no c:title. Category labels and the
        # units in the chart title must not be invented as axis titles.
        expected = ["분기별 매출/비용/이익 (억원)", 3, ["TOP"] * 3,
                    ["Chart type: column", "", ""]]
        results.append(record(path, "charts:title", expected, actual, len(warnings)))
    path = base / "charts.hwpx"
    if path.is_file():
        with zipfile.ZipFile(path) as archive:
            raw = archive.read("Chart/chart1.xml")
        elements, warnings = parse_chart_xml(raw)
        actual = [table.caption_text for table in elements if isinstance(table, Table)]
        # chart1.xml has barDir=bar and three cached series; its annotation is
        # chart-level metadata and must occur once, on the first series table.
        expected = ["Chart type: bar", "", ""]
        results.append(record(path, "charts:caption-once", expected, actual, len(warnings)))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    args = parser.parse_args()
    results = validate(args.corpus)
    print(json.dumps(dict(cases=results, total=len(results),
                          passed=sum(case["passed"] for case in results)),
                     ensure_ascii=False, indent=2))
    return 0 if results and all(case["passed"] for case in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
