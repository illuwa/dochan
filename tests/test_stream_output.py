"""File output preserves text and publishes only completed conversions."""
import io
import json

import pytest

from dochan.model.document import Document, Section, Paragraph, TextRun
from dochan.output import json_indent, json_out, markdown
from dochan.batch import _atomic_write_text


@pytest.mark.parametrize('indent', [None, 0, 2, '\t'])
def test_json_writer(indent):
    doc = Document(sections=[Section(elements=[Paragraph(runs=[TextRun('한글')])])])
    fp = io.StringIO()
    json_out.write_json(doc, fp, indent)
    assert fp.getvalue() == json_out.to_json(doc, indent)


def test_lazy_dump_writes_before_consuming_all_items():
    fp = io.StringIO()

    def items():
        for i in range(10000):
            if i == 9000:
                assert fp.tell() > 0
            yield {'value': i}

    json_indent.dump(json_indent.Stream(items(), 10000), fp, 2)
    assert json.loads(fp.getvalue()) == [{'value': i} for i in range(10000)]


def test_markdown_writer():
    doc = Document(sections=[Section(elements=[Paragraph(runs=[TextRun(s)])])
                             for s in ['처음', '', '끝']])
    fp = io.StringIO()
    markdown.write_markdown(doc, fp)
    assert fp.getvalue() == markdown.to_markdown(doc)


def test_atomic_writer_failure_preserves_target(tmp_path):
    target = tmp_path / 'out.json'
    target.write_text('old')

    def fail(fp):
        fp.write('partial')
        raise OSError('disk failure')

    with pytest.raises(OSError, match='disk failure'):
        _atomic_write_text(str(target), fail)
    assert target.read_text() == 'old'
    assert list(tmp_path.iterdir()) == [target]


@pytest.mark.parametrize('native', [False, True])
@pytest.mark.parametrize('indent', [None, 2])
def test_native_flag_does_not_materialize_rows(monkeypatch, native, indent):
    monkeypatch.setattr(json_indent, 'STDLIB_INDENT_IS_NATIVE', native)
    doc = Document(sections=[Section(elements=[Paragraph(runs=[TextRun('값')])])])
    expected = json_out.to_json(doc, indent)

    def forbidden(*args):
        raise AssertionError('materialized dict')

    monkeypatch.setattr(json_out, 'to_dict', forbidden)
    fp = io.StringIO()
    json_out.write_json(doc, fp, indent)
    assert fp.getvalue() == expected


@pytest.mark.parametrize('value', [object(), {'bad': object()}, {('key',): 1}])
def test_dump_invalid_values_raise_type_error(value):
    with pytest.raises(TypeError):
        json_indent.dump(value, io.StringIO())


def test_dump_circular_reference():
    value = []
    value.append(value)
    with pytest.raises(ValueError, match='Circular reference detected'):
        json_indent.dump(value, io.StringIO())


@pytest.mark.parametrize('indent', [None, 0, 2, '\t'])
def test_writers_cover_tables_assets_and_notes(indent):
    from test_json_indent_encoder import _many_shapes_document
    doc = _many_shapes_document()
    fp = io.StringIO()
    json_out.write_json(doc, fp, indent)
    assert fp.getvalue() == json_out.to_json(doc, indent)
    fp = io.StringIO()
    markdown.write_markdown(doc, fp)
    assert fp.getvalue() == markdown.to_markdown(doc)


@pytest.mark.parametrize('fmt', ['json', 'markdown'])
def test_cli_and_batch_use_writer_without_string_api(tmp_path, monkeypatch, fmt):
    from dochan.reader import Dochan
    from dochan.cli import main
    from dochan.batch import batch_convert
    from scripts.probe_stream_output import synthetic_xlsx
    inputs = tmp_path / 'inputs'
    inputs.mkdir()
    source = inputs / 'small.xlsx'
    synthetic_xlsx(source, 3)
    reader = Dochan(str(source))
    expected = getattr(reader, 'to_' + fmt)()

    def forbidden(*args, **kwargs):
        raise AssertionError('string API used')

    monkeypatch.setattr(Dochan, 'to_' + fmt, forbidden)
    target = tmp_path / 'converted'
    assert main(['convert', str(source), '--format', fmt, '-o', str(target)]) == 0
    assert target.read_text() == expected
    result = batch_convert(str(inputs), str(tmp_path / 'batch'),
                           output_format=fmt, max_workers=1)
    assert result.success == 1
    from pathlib import Path
    assert Path(result.results[0].output_path).read_text() == expected


@pytest.mark.parametrize('indent', [None, 0, 2, '\t', -1])
def test_dump_scalar_and_nested_type_parity(indent):
    from test_json_indent_encoder import HANDCRAFTED
    for value in HANDCRAFTED:
        fp = io.StringIO()
        json_indent.dump(value, fp, indent)
        assert fp.getvalue() == json.dumps(value, ensure_ascii=False, indent=indent)


def test_markdown_emits_completed_section_before_next_section():
    fp = io.StringIO()

    class Sections:
        def __iter__(self):
            yield Section(elements=[Paragraph(runs=[TextRun('first')])])
            assert fp.getvalue() == 'first'
            yield Section(elements=[Paragraph(runs=[TextRun('second')])])

    doc = Document(sections=Sections())
    markdown.write_markdown(doc, fp)
    assert fp.getvalue() == 'first\n\nsecond'


def test_compact_dump_supports_lazy_rows():
    fp = io.StringIO()
    json_indent.dump({'rows': json_indent.Stream(iter([{'value': 1}, {'value': 2}]), 2)},
                     fp, indent=None)
    assert fp.getvalue() == '{"rows": [{"value": 1}, {"value": 2}]}'
