"""들여쓰기 JSON 직렬화 — 표준 라이브러리 출력과 바이트 단위로 같아야 한다.

`to_json()` 은 모든 형식이 함께 쓰는 출력 경로다. CPython 3.12 이하에서는
`json.dumps(indent=...)` 가 순수 Python 재귀 제너레이터로 떨어져 파싱보다
오래 걸리므로 자체 직렬화기를 쓴다. 계약은 하나다: 어떤 입력에서도
`json.dumps(obj, ensure_ascii=False, indent=indent)` 와 결과(문자열 또는 예외)가 같다.
"""
import collections
import enum
import json
import random

import pytest

from dochan.conversion import AssetRef, Provenance
from dochan.model.document import Document, Paragraph, Section, TextRun
from dochan.model.header_footer import Footnote
from dochan.model.image import Image
from dochan.model.table import Cell, Table
from dochan.output import json_indent
from dochan.output.json_out import to_dict, to_json

INDENTS = (2, 0, 1, 4, "\t", "", -1, True)


def _reference(obj, indent):
    return json.dumps(obj, ensure_ascii=False, indent=indent)


class _Name(str):
    """PDFName 처럼 str 을 상속한 값."""


class _Level(enum.IntEnum):
    LOW = 1
    HIGH = 7


class _Ratio(float):
    pass


HANDCRAFTED = [
    {},
    [],
    (),
    "문자열",
    "",
    0,
    -17,
    2 ** 80,
    1.5,
    -0.0,
    1e300,
    1e-7,
    True,
    False,
    None,
    {"a": {}, "b": [], "c": (), "d": [[]], "e": [{}], "f": {"g": {"h": []}}},
    {"한글": "값", "quote": 'a"b', "back": "a\\b", "ctl": "\x00\x01\t\n\r\x1f", "del": "\x7f",
     "bmp": "  ", "astral": "\U0001f600", "lone": "\ud800"},
    [1, 2.5, True, False, None, "s", [1, [2, [3, [4]]]], {"k": [1, {"k2": (1, 2)}]}],
    {"nan": float("nan"), "inf": float("inf"), "ninf": float("-inf")},
    {1: "int", 2.5: "float", None: "none", False: "false"},
    {True: "bool key", "t": 1, 7: [True]},
    {"name": _Name("Helv"), "level": _Level.HIGH, "ratio": _Ratio(0.25), "pair": (_Name("a"), 3)},
    collections.OrderedDict([("z", 1), ("a", [collections.OrderedDict(b=2)])]),
    {"deep": [[[[[[[[[[[[[[[[[[[[{"x": [1]}]]]]]]]]]]]]]]]]]]]]},
]


@pytest.mark.parametrize("indent", INDENTS)
@pytest.mark.parametrize("value", HANDCRAFTED, ids=range(len(HANDCRAFTED)))
def test_indented_walker_matches_stdlib_bytes(value, indent):
    # 3.13+ 에서 to_json 이 표준 라이브러리로 위임하더라도 자체 직렬화기는 계속 검증한다.
    assert json_indent.dumps_indented(value, indent) == _reference(value, indent)
    assert json_indent.dumps(value, indent) == _reference(value, indent)


def _random_tree(rng, depth=0):
    roll = rng.random()
    if depth >= 6 or roll < 0.35:
        return rng.choice([
            None, True, False, 0, 1, -1, rng.randint(-10 ** 12, 10 ** 12), rng.random() * 1e6,
            rng.uniform(-1, 1), 10.0, "", "text", "줄\n바꿈", 'q"\\', "\x05", "\ud83d",
            _Name("N"), _Level.LOW, _Ratio(1.25),
        ])
    if roll < 0.65:
        items = [_random_tree(rng, depth + 1) for _ in range(rng.randint(0, 5))]
        return tuple(items) if rng.random() < 0.2 else items
    keys = ["text", "bold", "runs", "provenance", "한글 키", "", "k\n", 3, 4.5, None, True]
    return {rng.choice(keys): _random_tree(rng, depth + 1) for _ in range(rng.randint(0, 6))}


def test_indented_walker_matches_stdlib_on_random_trees():
    rng = random.Random(20261006)
    for index in range(1500):
        tree = _random_tree(rng)
        indent = INDENTS[index % len(INDENTS)]
        assert json_indent.dumps_indented(tree, indent) == _reference(tree, indent), (index, indent)


def test_none_indent_keeps_compact_stdlib_form():
    value = {"a": [1, {"b": None}], "c": "값"}
    assert json_indent.dumps(value, None) == json.dumps(value, ensure_ascii=False)


@pytest.mark.parametrize("value", [
    {"bad": {1, 2}},
    [b"bytes"],
    {"obj": object()},
    {(1, 2): "tuple key"},
    [{"nested": [{("k",): 1}]}],
])
def test_unsupported_values_raise_the_same_error_as_stdlib(value):
    with pytest.raises(TypeError) as expected:
        _reference(value, 2)
    with pytest.raises(TypeError) as actual:
        json_indent.dumps(value, 2)
    assert str(actual.value) == str(expected.value)


def test_circular_reference_raises_the_same_error_as_stdlib():
    loop = {"items": []}
    loop["items"].append(loop)
    with pytest.raises(ValueError) as expected:
        _reference(loop, 2)
    with pytest.raises(ValueError) as actual:
        json_indent.dumps(loop, 2)
    assert str(actual.value) == str(expected.value)


def test_invalid_indent_type_behaves_like_stdlib():
    with pytest.raises(TypeError):
        _reference({"a": [1]}, 1.5)
    with pytest.raises(TypeError):
        json_indent.dumps({"a": [1]}, 1.5)


def _sample_document():
    note = Footnote(paragraphs=[Paragraph(runs=[TextRun(text="각주 본문")])])
    note.number = 1
    cell = Cell(
        paragraphs=[
            Paragraph(runs=[TextRun(text="셀 | 값\n둘째 줄", bold=True, link="https://example.com/a b")],
                      provenance=Provenance(source_format="xlsx", sheet="시트1", cell="B2")),
            Table(rows=[[Cell(paragraphs=[Paragraph(runs=[TextRun(text="중첩")])])]]),
        ],
        row=1, col=1, row_span=2, col_span=1,
        provenance=Provenance(source_format="xlsx", sheet="시트1", cell="B2", hidden=True),
    )
    table = Table(rows=[[cell, Cell(row_span=0, col_span=0)]],
                  caption=[Paragraph(runs=[TextRun(text="표 1")])], caption_side="TOP")
    image = Image(filename="그림 (1).png", alt_text="대체", ocr_text="OCR")
    section = Section(
        elements=[
            Paragraph(runs=[TextRun(text="제목", font_size_pt=16.5), TextRun(text="", note_ref=1)],
                      heading_level=1, provenance=Provenance(source_format="pdf", page=0)),
            table, image, note,
        ],
        provenance=Provenance(source_format="xlsx", sheet="시트1", visibility=1),
    )
    doc = Document(sections=[section, Section()], source_format="xlsx")
    doc.errors.append("WARN: 표본 경고")
    doc.assets.append(AssetRef(id="rId1", source_path="xl/media/image1.png", filename="image1.png",
                               content_type="image/png",
                               metadata={"kind": "image", "size": (3, 4), "tags": ["a", None]}))
    return doc


@pytest.mark.parametrize("indent", [2, 0, 4, "\t", None])
def test_to_json_matches_stdlib_dump_of_to_dict(indent):
    doc = _sample_document()
    assert to_json(doc, indent=indent) == _reference(to_dict(doc), indent)


def test_model_payload_never_falls_back_to_stdlib():
    doc = _sample_document()
    before = json_indent.stdlib_fallbacks()
    assert json_indent.dumps_indented(to_dict(doc), 2) == _reference(to_dict(doc), 2)
    json_indent.dumps(to_dict(doc), 2)
    assert json_indent.stdlib_fallbacks() == before


def test_fallback_counter_counts_unsupported_payloads():
    before = json_indent.stdlib_fallbacks()
    with pytest.raises(TypeError):
        json_indent.dumps({"bad": {1}}, 2)
    expected = before if json_indent.STDLIB_INDENT_IS_NATIVE else before + 1
    assert json_indent.stdlib_fallbacks() == expected


def test_native_indent_probe_agrees_with_interpreter_behaviour():
    # C 인코더가 들여쓰기를 직접 내는 인터프리터(3.13+)에서는 자체 직렬화기가 오히려 느리다.
    import sys

    assert isinstance(json_indent.STDLIB_INDENT_IS_NATIVE, bool)
    if sys.implementation.name == "cpython":
        assert json_indent.STDLIB_INDENT_IS_NATIVE == (sys.version_info >= (3, 13))


# ── 지연 목록(Stream): 문서 전체의 dict 트리를 만들지 않고 항목을 하나씩 쓰고 버린다 ──

def _stream(values):
    values = list(values)
    return json_indent.Stream(iter(values), len(values))


@pytest.mark.parametrize("indent", [2, 0, "\t"])
def test_stream_is_serialized_exactly_like_a_list(indent):
    rows = [[{"text": f"r{r}c{c}", "n": r * c, "ok": bool(c % 2)} for c in range(3)] for r in range(5)]
    lazy = {
        "empty": _stream([]),
        "scalars": _stream([1, "둘", None, 2.5, True]),
        "rows": _stream(_stream(row) for row in rows),
        "tail": {"after": [1]},
    }
    eager = {"empty": [], "scalars": [1, "둘", None, 2.5, True], "rows": rows, "tail": {"after": [1]}}
    assert json_indent.dumps_indented(lazy, indent) == _reference(eager, indent)
    assert json_indent.dumps_indented(_stream(rows), indent) == _reference(rows, indent)


def test_stream_items_are_produced_one_at_a_time():
    produced = []

    def rows():
        for index in range(4):
            produced.append(index)
            yield {"row": index}

    text = json_indent.dumps_indented({"rows": json_indent.Stream(rows(), 4)}, 2)
    assert produced == [0, 1, 2, 3]
    assert text == _reference({"rows": [{"row": index} for index in range(4)]}, 2)


def test_large_stream_output_survives_chunk_compaction():
    # 조각 수가 압축 임계를 여러 번 넘도록 충분히 큰 표를 흘려 보낸다.
    rows = [[{"text": f"값 {r}-{c}", "row": r, "col": c, "flags": [True, None]} for c in range(8)]
            for r in range(600)]
    lazy = {"sections": _stream([{"elements": _stream([{"rows": _stream(rows)}, {"type": "p"}])}])}
    eager = {"sections": [{"elements": [{"rows": rows}, {"type": "p"}]}]}
    assert json_indent.dumps_indented(lazy, 2) == _reference(eager, 2)


def _many_shapes_document():
    doc = _sample_document()
    big = Table(rows=[[Cell(paragraphs=[Paragraph(runs=[TextRun(text=f"{r}행 {c}열")])], row=r, col=c)
                       for c in range(6)] for r in range(400)])
    empty_table = Table(rows=[])
    blank_rows = Table(rows=[[], [Cell()]])
    header = __import__("dochan.model.header_footer", fromlist=["HeaderFooter"]).HeaderFooter(
        type="header", paragraphs=[Paragraph(runs=[TextRun(text="머리글")]), Table(rows=[[Cell()]])])
    doc.sections.append(Section(elements=[big, empty_table, blank_rows, header]))
    doc.sections.append(Section(elements=[]))
    return doc


@pytest.mark.parametrize("indent", [2, 0, 4, "\t", None])
def test_to_json_streaming_matches_stdlib_dump_of_to_dict_for_all_shapes(indent):
    doc = _many_shapes_document()
    assert to_json(doc, indent=indent) == _reference(to_dict(doc), indent)
    assert to_json(Document(), indent=indent) == _reference(to_dict(Document()), indent)


def test_to_json_does_not_fall_back_for_model_documents():
    before = json_indent.stdlib_fallbacks()
    to_json(_many_shapes_document())
    assert json_indent.stdlib_fallbacks() == before


def test_to_json_with_unserializable_asset_metadata_fails_like_stdlib():
    doc = _sample_document()
    doc.assets[0].metadata["bad"] = {1, 2}
    with pytest.raises(TypeError) as expected:
        _reference(to_dict(doc), 2)
    with pytest.raises(TypeError) as actual:
        to_json(doc)
    assert str(actual.value) == str(expected.value)


def test_to_dict_stays_fully_materialized():
    payload = to_dict(_many_shapes_document())
    assert type(payload["sections"]) is list
    assert type(payload["sections"][0]["elements"]) is list
    table = next(e for e in payload["sections"][2]["elements"] if e["type"] == "table")
    assert type(table["rows"]) is list and type(table["rows"][0]) is list
    assert json.loads(json.dumps(payload, ensure_ascii=False)) == json.loads(to_json(_many_shapes_document()))
