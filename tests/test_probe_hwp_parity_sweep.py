from pathlib import Path

from dochan.model.document import Document, Paragraph, Section, TextRun
from dochan.model.equation import Equation
from scripts.probe_hwp_parity_sweep import (_asset_neutral, discover_pairs,
                                            summarize_pair)


def test_discover_pairs_across_format_directories(tmp_path):
    (tmp_path / 'hwp').mkdir()
    (tmp_path / 'hwpx').mkdir()
    (tmp_path / 'hwp' / 'same.hwp').write_bytes(b'hwp')
    (tmp_path / 'hwpx' / 'same.hwpx').write_bytes(b'hwpx')
    (tmp_path / 'hwp' / 'other.hwp').write_bytes(b'hwp')
    assert [(name, Path(x).name, Path(h).name)
            for name, x, h in discover_pairs(tmp_path)] == [
        ('same', 'same.hwpx', 'same.hwp')]


def test_discover_pairs_accepts_uppercase_extensions(tmp_path):
    (tmp_path / 'case.HWPX').write_bytes(b'hwpx')
    (tmp_path / 'case.hwp').write_bytes(b'hwp')
    assert [(name, Path(x).name, Path(h).name)
            for name, x, h in discover_pairs(tmp_path)] == [
        ('case', 'case.HWPX', 'case.hwp')]


class _Reader:
    def __init__(self, text, paragraph, source_format, errors=()):
        self._text = text
        self.doc = Document(sections=[Section(elements=[paragraph, Equation(script='x')])],
                            source_format=source_format)
        self.errors = list(errors)

    def to_markdown(self):
        return self._text

    def to_plain_text(self):
        return self._text


def test_summarize_pair_records_hashes_and_counts_without_full_output():
    paragraph = Paragraph(runs=[TextRun(text='제목')], heading_level=2)
    row = summarize_pair(_Reader('## 제목\n', paragraph, 'hwpx'),
                         _Reader('## 제목\n', paragraph, 'hwp'))
    assert row['markdown_equal'] is True
    assert row['token_similarity'] == 1.0
    assert row['heading_levels_equal'] is True
    assert row['counts']['hwpx']['equation'] == 1
    assert row['same_document'] is True
    assert '## 제목' not in str(row)


def test_asset_neutral_preserves_image_description_and_order():
    hwpx = '![설명](BinData/image1.png)\n![둘](BinData/image2.jpg)'
    hwp = '![설명](BIN0001.png)\n![둘](BIN0002.jpg)'
    assert _asset_neutral(hwpx) == _asset_neutral(hwp)
    assert _asset_neutral('![다른 설명](BIN0001.png)') != _asset_neutral(
        '![설명](BinData/image1.png)')


def test_mislabeled_hwp_file_is_not_an_hwpx_oracle():
    paragraph = Paragraph(runs=[TextRun(text='제목')])
    row = summarize_pair(_Reader('제목', paragraph, 'hwp'),
                         _Reader('제목', paragraph, 'hwp'))
    assert row['same_document'] is False
    assert row['format_valid'] is False
