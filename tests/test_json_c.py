"""Native JSON differential and direct-model regression coverage."""
import io
import json
import os

import pytest

from dochan.conversion import Provenance
from dochan.model.document import Document, Paragraph, Section, TextRun
from dochan.model.table import Cell, Table
from dochan.output import json_indent, json_out


def test_json_backend_is_explicit():
    assert json_indent.JSON_BACKEND in {"c", "python"}
    if os.environ.get("DOCHAN_DISABLE_ACCEL") == "1":
        assert json_indent.JSON_BACKEND == "python"


def _document():
    provenance = Provenance(source_format="xlsx", sheet="시트", cell="A1", hidden=False)
    return Document(sections=[Section(elements=[Table(rows=[[
        Cell(paragraphs=[Paragraph(runs=[TextRun(text="한글\n\ud800", bold=True,
                                               provenance=provenance)], provenance=provenance)],
             row=0, col=0, provenance=provenance)
    ]])])])


@pytest.mark.parametrize("indent", [None, 0, 2, "\t", "", -1, True])
def test_model_native_path_avoids_intermediate_dicts(monkeypatch, indent):
    doc = _document()
    expected = json.dumps(json_out.to_dict(doc), ensure_ascii=False, indent=indent)
    if json_indent.JSON_BACKEND != "c":
        pytest.skip("optional C accelerator unavailable")

    def forbidden(*args, **kwargs):
        raise AssertionError("temporary model dict constructed")

    for name in ("_document_to_dict", "_cell_to_dict", "_paragraph_to_dict", "_run_to_dict",
                 "_provenance_to_dict"):
        monkeypatch.setattr(json_out, name, forbidden)
    assert json_out.to_json(doc, indent) == expected
    target = io.StringIO()
    json_out.write_json(doc, target, indent)
    assert target.getvalue() == expected


class _String(str):
    pass


class _List(list):
    pass


class _Int(int):
    def __repr__(self):
        return "wrong"


def _outcome(call):
    try:
        return "ok", call()
    except Exception as exc:
        return type(exc), str(exc)


@pytest.mark.parametrize("indent", [None, 2, 0, "x\ud800", 1.5, _Int(2), _String("\t")])
@pytest.mark.parametrize("value", [
    {"a": [_String("\udfff"), _Int(9)]},
    {"normal": [{1.5: "nonstring key", None: "null"}]},
    {"bad": {1}}, {"bad": object()}, {("bad",): 0},
    {"control": "".join(chr(i) for i in range(256))},
    {"surrogates": "\ud800\udc00😀𐀀\uffff\udfff"},
    _List([{"tuple": (1, 2)}, True]),
    {"x" * 70000: "value"},
])
def test_generic_values_and_exception_messages_match(value, indent):
    assert _outcome(lambda: json_indent.dumps(value, indent)) == _outcome(
        lambda: json.dumps(value, ensure_ascii=False, indent=indent))


def test_subclass_cycles_in_file_output_raise_value_error():
    loop = _List()
    loop.append(loop)
    expected = _outcome(lambda: json.dumps(loop, ensure_ascii=False, indent=2))
    assert _outcome(lambda: json_indent.dump(loop, io.StringIO())) == expected


@pytest.mark.parametrize("indent", [2, None, "\t"])
def test_stream_late_bailout_never_replays_written_output(indent):
    large = {"text": "한글" * 40000}
    tail = {1: [_String("subclass"), (True, None)]}
    produced = []

    def items():
        for value in (large, tail):
            produced.append(value)
            yield value

    class Sink:
        def __init__(self):
            self.chunks = []

        def write(self, text):
            self.chunks.append(text)

    sink = Sink()
    json_indent.dump(json_indent.Stream(items(), 2), sink, indent)
    assert produced == [large, tail]
    assert len(sink.chunks) >= 2
    assert "".join(sink.chunks) == json.dumps([large, tail], ensure_ascii=False, indent=indent)


def test_model_subclasses_missing_attributes_and_custom_provenance_fall_back():
    from dochan.conversion import Provenance

    class ParagraphSubclass(Paragraph):
        @property
        def text(self):
            return "override"

    doc = _document()
    elements = doc.sections[0].elements
    elements.extend([ParagraphSubclass(), Paragraph(provenance=Provenance(source_format=_String("")))])
    run = elements[0].rows[0][0].paragraphs[0].runs[0]
    del run.note_reference_type  # getattr default also exists on its dataclass class.
    run.provenance = type("CustomProvenance", (), {"page": 0, "hidden": False})()
    expected = json.dumps(json_out.to_dict(doc), ensure_ascii=False, indent=2)
    assert json_out.to_json(doc) == expected
    target = io.StringIO()
    json_out.write_json(doc, target)
    assert target.getvalue() == expected


def test_sink_exceptions_are_never_retried():
    class Sink:
        count = 0

        def write(self, text):
            self.count += 1
            raise OSError("sink failed")

    sink = Sink()
    with pytest.raises(OSError, match="sink failed"):
        json_out.write_json(_document(), sink)
    assert sink.count == 1


def test_randomized_differential():
    import random

    rng = random.Random(20261102)
    scalars = [None, True, False, -2**95, 2**101, 1e-300, float("nan"), float("inf"),
               -0.0, "", "한글", "\ud800", "\udfff", "\x00\n\"\\", _Int(7), _String("abc")]

    def tree(depth=0):
        if depth >= 5 or rng.random() < 0.4:
            return rng.choice(scalars)
        if rng.random() < 0.5:
            result = [tree(depth + 1) for _ in range(rng.randrange(6))]
            return tuple(result) if rng.random() < 0.2 else result
        return {rng.choice(["text", "runs", "한글", "\ud800", 2, None, 1.5]): tree(depth + 1)
                for _ in range(rng.randrange(6))}

    for index in range(int(os.environ.get("DOCHAN_JSON_FUZZ_CASES", "1500"))):
        payload = tree()
        indent = [2, 0, None, "\t", "", -2, True][index % 7]
        expected = json.dumps(payload, ensure_ascii=False, indent=indent)
        assert json_indent.dumps(payload, indent) == expected, index
        target = io.StringIO()
        json_indent.dump(payload, target, indent)
        assert target.getvalue() == expected, index


def test_large_model_subclass_bailout_preserves_row_streaming(monkeypatch):
    class TableSubclass(Table):
        pass

    doc = Document(sections=[Section(elements=[TableSubclass(rows=[
        [Cell(paragraphs=[Paragraph(runs=[TextRun(text="row")])])] for _ in range(1200)
    ])])])
    expected = json_out.to_json(doc)
    calls = []
    original = json_out._cell_to_dict

    def cell(value):
        calls.append(value)
        return original(value)

    monkeypatch.setattr(json_out, "_cell_to_dict", cell)

    class Sink:
        chunks = []

        def write(self, text):
            # Verify the output begins before all rows have been converted.
            if not self.chunks:
                assert 0 < len(calls) < 1200
            self.chunks.append(text)

    sink = Sink()
    json_out.write_json(doc, sink)
    assert "".join(sink.chunks) == expected
    assert len(calls) == 1200


def test_randomized_invalid_values_and_errors():
    import random

    rng = random.Random(7)
    leaves = [None, 1, "한글", "\ud800", float("nan"), object(), {1}, b"bad", 3j]

    def tree(depth=0):
        if depth > 4 or rng.random() < 0.4:
            return rng.choice(leaves)
        if rng.random() < 0.5:
            return [tree(depth + 1) for _ in range(rng.randrange(5))]
        return {rng.choice(["x", "y", (1, 2), None, 7]): tree(depth + 1)
                for _ in range(rng.randrange(5))}

    for index in range(int(os.environ.get("DOCHAN_JSON_FUZZ_CASES", "1500"))):
        value = tree()
        indent = [2, None, 0, "\t"][index % 4]
        expected = _outcome(lambda: json.dumps(value, ensure_ascii=False, indent=indent))
        assert _outcome(lambda: json_indent.dumps(value, indent)) == expected, index

        def write():
            target = io.StringIO()
            json_indent.dump(value, target, indent)
            return target.getvalue()

        assert _outcome(write) == expected, index


@pytest.mark.parametrize("failure", ["ImportError", "RuntimeError"])
def test_native_loader_only_hides_import_error(failure):
    import subprocess
    import sys

    code = '''
import importlib.abc, sys
class BlockNative(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'dochan.output._cjson':
            raise FAILURE('injected loader failure')
sys.meta_path.insert(0, BlockNative())
try:
    from dochan.output import json_indent
except RuntimeError as exc:
    assert 'injected loader failure' in str(exc)
    assert FAILURE is RuntimeError
else:
    assert FAILURE is ImportError
    assert json_indent.JSON_BACKEND == 'python'
    assert json_indent.dumps({'x': [1]}, 2) == '{\\n  "x": [\\n    1\\n  ]\\n}'
'''.replace("FAILURE", failure)
    environment = os.environ.copy()
    environment.pop("DOCHAN_DISABLE_ACCEL", None)
    subprocess.run([sys.executable, "-c", code], env=environment, check=True,  # nosemgrep: dangerous-subprocess-use-audit
                   capture_output=True)


def _all_optional_fields_document():
    """Every conditional JSON key switched on, so a field added only to the Python path shows up."""
    from dochan.model.document import Equation
    from dochan.model.header_footer import Comment, Footnote, HeaderFooter
    from dochan.model.image import Image

    def prov(tag):
        return Provenance(source_format="hwpx", page=3, slide=2, sheet=tag, cell="B2", section=1,
                          paragraph=4, path="a/b", visibility=1, hidden=True)

    def para(text):
        return Paragraph(runs=[
            TextRun(text=text, bold=True, italic=True, underline=True, strikeout=True,
                    superscript=True, subscript=True, font_size_pt=7.5, link="https://x",
                    note_ref=2, provenance=prov("r"), note_reference_type="footnote",
                    note_reference_number=5),
            TextRun(text="식", equation=Equation(script="a over b", script_format="hwp")),
            TextRun(text="주", note_reference_type="comment", note_reference_number=1),
        ], style_id=4, heading_level=2, provenance=prov("p"))

    cell = Cell(paragraphs=[para("셀")], row=1, col=2, row_span=2, col_span=3, provenance=prov("c"))
    merged = Cell(paragraphs=[], row=1, col=3, row_span=0, col_span=0, provenance=prov("m"))
    caption = [para("표 캡션")]
    table = Table(rows=[[cell, merged]], caption=caption, caption_side="TOP")
    image = Image(bin_id=3, filename="a.png", width=5, height=6, ocr_text="ocr", alt_text="alt",
                  caption=[para("그림 캡션")], caption_side="LEFT", provenance=prov("i"))
    elements = [para("본문"), table, image, Equation(script="x", latex_override="\\x"),
                HeaderFooter(type="footer", paragraphs=[para("꼬리")]),
                Footnote(type="endnote", paragraphs=[para("미주")], number=3),
                Comment(paragraphs=[para("주석")], number=1, author="저자")]
    return Document(sections=[Section(elements=elements, provenance=prov("s"))],
                    provenance=prov("d"), source_format="hwpx")


@pytest.mark.parametrize("indent", [None, 2])
def test_every_optional_model_field_matches_python_dicts(monkeypatch, indent):
    """Reference is the pure-Python dict builders; the C writer must not drop or reorder a key."""
    doc = _all_optional_fields_document()
    expected = json.dumps(json_out.to_dict(doc), ensure_ascii=False, indent=indent)
    if json_indent.JSON_BACKEND != "c":
        pytest.skip("optional C accelerator unavailable")

    def forbidden(*args, **kwargs):
        raise AssertionError("fell back to the Python dict path")

    for name in ("_document_to_dict", "_section_to_dict", "_cell_to_dict", "_paragraph_to_dict",
                 "_run_to_dict", "_provenance_to_dict"):
        monkeypatch.setattr(json_out, name, forbidden)
    assert json_out.to_json(doc, indent) == expected


def test_run_missing_note_reference_attribute_matches_python_dicts():
    """A run object lacking one note attribute must not leave a pending C exception behind."""
    run = TextRun(text="a")
    del run.__dict__["note_reference_type"]
    TextRun.note_reference_type, saved = None, TextRun.__dict__.get("note_reference_type")
    try:
        del TextRun.note_reference_type
        doc = Document(sections=[Section(elements=[Paragraph(runs=[run])])])
        expected = json.dumps(json_out.to_dict(doc), ensure_ascii=False, indent=2)
        assert json_out.to_json(doc, 2) == expected
    finally:
        TextRun.note_reference_type = saved if saved is not None else ""


class _Hostile(str):
    """Every Python-level hook lies; only the stored characters count for JSON."""

    def __new__(cls, text, number=None):
        instance = super().__new__(cls, text)
        instance.number = number
        return instance

    def __str__(self):
        raise AssertionError("__str__ must not be consulted")

    def __repr__(self):
        raise AssertionError("__repr__ must not be consulted")

    def __len__(self):
        raise AssertionError("__len__ must not be consulted")

    def __iter__(self):
        raise AssertionError("__iter__ must not be consulted")

    def encode(self, *args, **kwargs):
        raise AssertionError("encode must not be consulted")

    def __getitem__(self, item):
        raise AssertionError("__getitem__ must not be consulted")


_TEXTS = ["", "plain", "한글", "q\"b\\n\n\t\x00\x1f\x7f", "\ud800", "\udfff", "😀𐀀￿ ",
          "x" * 70000]


def _no_fallback(*args):
    raise AssertionError("string subclass fell back to Python")


@pytest.mark.parametrize("indent", [None, 0, 2, "\t"])
@pytest.mark.parametrize("text", _TEXTS, ids=range(len(_TEXTS)))
def test_str_subclass_values_are_escaped_natively(text, indent):
    if json_indent.JSON_BACKEND != "c":
        pytest.skip("optional C accelerator unavailable")
    value = {"a": [_Hostile(text, 1.5), {"b": _Hostile(text)}], "c": _Hostile(text, "fmt")}
    expected = json.dumps({"a": [text, {"b": text}], "c": text}, ensure_ascii=False, indent=indent)
    assert json_indent._native_encode(value, indent, fallback=_no_fallback) == expected
    target = io.StringIO()
    json_indent._native_encode(value, indent, target, fallback=_no_fallback)
    assert target.getvalue() == expected
    # The root value itself, too.
    assert json_indent._native_encode(_Hostile(text), indent, fallback=_no_fallback) == \
        json.dumps(text, ensure_ascii=False)


def test_str_subclass_run_text_in_model_is_escaped_without_python_fallback(monkeypatch):
    if json_indent.JSON_BACKEND != "c":
        pytest.skip("optional C accelerator unavailable")
    provenance = Provenance(source_format="xls", sheet="s", cell="A1")
    run = TextRun(text=_Hostile("12.50 \ud800", 12.5), provenance=provenance)
    doc = Document(sections=[Section(elements=[Table(rows=[[Cell(
        paragraphs=[Paragraph(runs=[run], provenance=provenance)], row=0, col=0,
        provenance=provenance)]])])])
    plain = TextRun(text="12.50 \ud800", provenance=provenance)
    reference = Document(sections=[Section(elements=[Table(rows=[[Cell(
        paragraphs=[Paragraph(runs=[plain], provenance=provenance)], row=0, col=0,
        provenance=provenance)]])])])
    expected = json.dumps(json_out.to_dict(reference), ensure_ascii=False, indent=2)
    monkeypatch.setattr(json_out, "_model_fallback", _no_fallback)
    # Cell.text / Paragraph.text join run texts through Python, which the lying hooks must not break.
    assert json_out.to_json(doc, 2) == expected
