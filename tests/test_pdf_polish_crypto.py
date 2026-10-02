"""간접 암호 필터 사전도 직접 사전과 같은 평문을 복원해야 한다."""
import pytest

from dochan.pdf.reader import PDFReader
from dochan.pdf.structure import PDFFile
from test_pdf_crypto_password import VECTORS, _decode, _pdf_value
from test_pdf_structure import _build_pdf


def _indirect_pdf(length=True, broken=None):
    vector = VECTORS[2]
    encrypt = _decode(vector["encrypt"])
    encrypt.pop("CF")
    encrypt.pop("StmF")
    encrypt.pop("StrF")
    if not length:
        encrypt.pop("Length")
    cipher = bytes.fromhex(vector["cipher"])
    objects = {
        1: "<< /Type /Catalog /Pages 2 0 R >>",
        2: "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        3: "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] "
           "/Resources << /Font << /F1 5 0 R >> >> /Contents 6 0 R >>",
        4: _pdf_value(encrypt)[:-2] + b" /CF 7 0 R /StmF 10 0 R /StrF 10 0 R >>",
        5: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        6: b"<< /Length %d >>\nstream\n%s\nendstream" % (len(cipher), cipher),
        7: "8 0 R",
        8: "<< /StdCF 9 0 R >>",
        9: "<< /CFM 11 0 R /Length 12 0 R >>",
        10: "/StdCF",
        11: "/AESV2",
        12: "16",
    }
    if broken == "cycle":
        objects[9] = "<< /CFM /AESV2 /Length 16 /Cycle 8 0 R >>"
    elif broken == "missing":
        del objects[9]
    elif broken == "depth":
        objects[9] = "<< /CFM /AESV2 /Length 16 /Nested 13 0 R >>"
        for num in range(13, 55):
            objects[num] = "<< /Nested %d 0 R >>" % (num + 1)
        objects[55] = "<< >>"
    elif broken == "width":
        objects[9] = "<< /CFM /AESV2 /Length 16 /Large [%s] >>" % ("0 " * 5000)
    return _build_pdf(objects, "/Encrypt 4 0 R /ID [<%s><%s>]" %
                      (vector["id"], vector["id"]))


@pytest.mark.parametrize("length", [True, False])
def test_indirect_crypt_filters_and_selectors_extract_plaintext(tmp_path, length):
    path = tmp_path / "indirect.pdf"
    path.write_bytes(_indirect_pdf(length))
    doc = PDFReader(password="user").read(str(path))
    assert doc.errors == []
    assert [p.text for p in doc.find_all("paragraph")] == ["Protected text"]


@pytest.mark.parametrize("broken", ["cycle", "missing", "depth", "width"])
def test_invalid_crypt_filter_graph_is_bounded_and_warns(broken):
    pdf = PDFFile(_indirect_pdf(broken=broken), password="user")
    assert not pdf.decrypt_ok
    assert any("암호" in message for message in pdf.warnings)
