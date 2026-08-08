import pytest

from dochan.pdf.objects import (
    PDFLexer,
    PDFName,
    PDFRef,
    PDFStream,
    PDFSyntaxError,
    parse_indirect_object,
)


def _parse(data: bytes):
    return PDFLexer(data).parse_object()


def test_parses_scalars():
    assert _parse(b"true") is True
    assert _parse(b"false") is False
    assert _parse(b"null") is None
    assert _parse(b"42") == 42
    assert _parse(b"-17") == -17
    assert _parse(b"3.14") == pytest.approx(3.14)


def test_parses_name_with_hash_escape():
    name = _parse(b"/A#20B")
    assert isinstance(name, PDFName)
    assert name == "A B"


def test_parses_literal_string_with_escapes_and_nesting():
    assert _parse(rb"(a\(b\)c)") == b"a(b)c"
    assert _parse(b"(nested (paren) ok)") == b"nested (paren) ok"
    assert _parse(rb"(tab\there)") == b"tab\there"
    assert _parse(rb"(\101\102)") == b"AB"


def test_parses_hex_string_with_odd_digits():
    assert _parse(b"<48454C4C4F>") == b"HELLO"
    assert _parse(b"<48 45 4C>") == b"HEL"
    assert _parse(b"<484>") == b"H@"


def test_parses_array_and_dict_with_refs():
    obj = _parse(b"<< /Kids [3 0 R 4 0 R] /Count 2 /Name /Pages >>")
    assert obj["Kids"] == [PDFRef(3, 0), PDFRef(4, 0)]
    assert obj["Count"] == 2
    assert obj["Name"] == "Pages"


def test_skips_comments_between_tokens():
    assert _parse(b"% comment\n7") == 7


def test_parse_indirect_object_plain():
    data = b"12 0 obj\n<< /Type /Catalog >>\nendobj\n"
    num, gen, obj = parse_indirect_object(data, 0)
    assert (num, gen) == (12, 0)
    assert obj["Type"] == "Catalog"


def test_parse_indirect_object_stream_with_length():
    body = b"BT (hi) Tj ET"
    data = b"5 0 obj\n<< /Length %d >>\nstream\n%s\nendstream\nendobj\n" % (len(body), body)
    num, gen, obj = parse_indirect_object(data, 0)
    assert isinstance(obj, PDFStream)
    assert obj.raw == body


def test_parse_indirect_object_stream_with_wrong_length_falls_back():
    body = b"0123456789"
    data = b"5 0 obj\n<< /Length 99999 >>\nstream\n%s\nendstream\nendobj\n" % body
    _, _, obj = parse_indirect_object(data, 0)
    assert isinstance(obj, PDFStream)
    assert obj.raw == body


def test_parse_indirect_object_stream_with_indirect_length():
    body = b"abcdef"
    data = b"5 0 obj\n<< /Length 6 0 R >>\nstream\n%s\nendstream\nendobj\n" % body
    _, _, obj = parse_indirect_object(data, 0, resolve=lambda ref: 6)
    assert obj.raw == body


def test_raises_on_broken_header():
    with pytest.raises(PDFSyntaxError):
        parse_indirect_object(b"nonsense here", 0)
