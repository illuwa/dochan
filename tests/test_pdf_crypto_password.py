"""사용자 암호 PDF 합성 바이트와 알려진 키로 R2–R6를 검증한다.

아래 숫자/암호문은 개발 중 pypdf 참조 인코더로 만든 합성 입력에서 얻었다.
실행 시에는 코퍼스나 참조 인코더에 의존하지 않고 PDF 바이트를 조립한다.
"""
import pytest

from dochan.pdf.crypto import StandardSecurityHandler, UnsupportedEncryption
from dochan.pdf.reader import PDFReader

VECTORS = [{'cipher': '32a54525324c8cb407355339f68d6da95adc6f5f29dd0c1fb0b2abce40b9ed5b0987b8d7312f5aa71f96198cc7',
  'encrypt': {'Filter': 'Standard',
              'Length': 40,
              'O': {'hex': '94e8094419662a774442fb072e3d9f19e9d130ec09a4d0061e78fe920f7ab62f'},
              'P': 4294967292,
              'R': 2,
              'U': {'hex': 'f3b60cbfd677a3f42fd8aa8b7d9c4891d76f2fd7a7e9d75a8e7bc4515d68a382'},
              'V': 1},
  'id': '6637313137306437313434353762633866336463373339643066616435663935',
  'derived': 'fbc077bdda',
  'name': 'RC4-40',
  'password': 'user'},
 {'cipher': '356edc00a8ef8f7f0f581c17b5d696bf364059c54d83f132fe96b493ae9e9106a43f49714b534944956532ee7b',
  'encrypt': {'Filter': 'Standard',
              'Length': 128,
              'O': {'hex': '0ba3835f88f90388e74e54584125ce142be0de24c6b0d37746e075b891756671'},
              'P': 4294967292,
              'R': 3,
              'U': {'hex': '9f8710822c672315b7d5d3f601fbe12e28bf4e5e4e758a4164004e56fffa0108'},
              'V': 2},
  'id': '6637313137306437313434353762633866336463373339643066616435663935',
  'derived': 'bd1aa9590e1be9968d7185d305cefb7c',
  'name': 'RC4-128',
  'password': 'user'},
 {'cipher': '63a1830d26b63fd212679107a6a6c6c16f36b00d93319b7fe1a17eb93064ee9f88c258b51846ec984b72a507f9ffc16cc4dd5d58eabb18a26ab16f28dd1d3b14',
  'encrypt': {'CF': {'StdCF': {'AuthEvent': 'DocOpen', 'CFM': 'AESV2', 'Length': 16}},
              'Filter': 'Standard',
              'Length': 128,
              'O': {'hex': '0ba3835f88f90388e74e54584125ce142be0de24c6b0d37746e075b891756671'},
              'P': 4294967292,
              'R': 4,
              'StmF': 'StdCF',
              'StrF': 'StdCF',
              'U': {'hex': '9f8710822c672315b7d5d3f601fbe12e28bf4e5e4e758a4164004e56fffa0108'},
              'V': 4},
  'id': '6637313137306437313434353762633866336463373339643066616435663935',
  'derived': 'bd1aa9590e1be9968d7185d305cefb7c',
  'name': 'AES-128',
  'password': 'user'},
 {'cipher': '6a1bb43debae76a7fb0d3962385ec561194190004fb6ce7d5b39c8708bf90b65067bb2533e7e6043ca4e9e0398abf2cf5b835a144dadc5ed9e383c64d051ddd8',
  'encrypt': {'CF': {'StdCF': {'AuthEvent': 'DocOpen', 'CFM': 'AESV3', 'Length': 32}},
              'Filter': 'Standard',
              'Length': 256,
              'O': {'hex': 'c1a3736464e4859d0b8758fb7fdecdb1f901c2807f97391fbe205c7713d1ce10225d323531413c06c19b650727ae20fb'},
              'OE': {'hex': '5dc4a305f64bc897836827844de767a20f073c03eb6773bfd9e31a69ae389b44'},
              'P': 4294967292,
              'Perms': {'hex': 'a7087449b1463508c0360cf8d6df03f5'},
              'R': 5,
              'StmF': 'StdCF',
              'StrF': 'StdCF',
              'U': {'hex': 'ae39e8e573cd533db83328cb3018404ab1c92be9354092e702301f0dd1feb0e0e7db04cf99f7e7650803b20549775b89'},
              'UE': {'hex': '569bdf6f3edc59f9d04e3bbdbb144edf73943717dfcd250f3789f5853a618ae1'},
              'V': 5},
  'id': '6637313137306437313434353762633866336463373339643066616435663935',
  'derived': '7368acd562d4ab2c1dad32743b1be18d543c574dadb8dffc0e5b9c1c4db9f2cb',
  'name': 'AES-256-R5',
  'password': 'user'},
 {'cipher': '9d931c04c51bc31dd2adde8b1bfca9b1fcc7f4a00cc2e3f1f927b7b3c2ae8a903a7772824b9192f771b8e5c32d22978bc6a77b1802f4968d8a435c9e06ad3250',
  'encrypt': {'CF': {'StdCF': {'AuthEvent': 'DocOpen', 'CFM': 'AESV3', 'Length': 32}},
              'Filter': 'Standard',
              'Length': 256,
              'O': {'hex': '2812f3618a3555f865780397ea47be5bdddd098e1d64647021d925950077cabdd344c12de4602a8463ea7d1a3d40cd8c'},
              'OE': {'hex': '801bbe011a8238b3713742590e93af80ec53934a072cfea950c2ed13bdacae5a'},
              'P': 4294967292,
              'Perms': {'hex': '03d331595aaebbabdea0a7a9f8b459b4'},
              'R': 6,
              'StmF': 'StdCF',
              'StrF': 'StdCF',
              'U': {'hex': '8895022e72ae32dca39e2c1cb818d8a69315a0e520ab3bb59e7217b3437c1f8c35f082c3dc7d994a4c4f966495fe90ba'},
              'UE': {'hex': 'b90b1340e602c5e6b08de479816ea3f3f2774e09e7985c54eb420ed06d964f13'},
              'V': 5},
  'id': '6637313137306437313434353762633866336463373339643066616435663935',
  'derived': '2ad35154f2fc67f2589ce189caa85ded4749206d5cc4c45ccbeaf4005ba8208f',
  'name': 'AES-256',
  'password': 'user'},
 {'cipher': '2936271c56e84b806059b4ee8d13a7ffcd6123616dc21f7a3cdbebfb6eb635b1ae7583180b6cdc558cec69bba86d2ff49504e744bc3f6d769a98af52cfffc38f',
  'encrypt': {'CF': {'StdCF': {'AuthEvent': 'DocOpen', 'CFM': 'AESV3', 'Length': 32}},
              'Filter': 'Standard',
              'Length': 256,
              'O': {'hex': '11998fa3175a683a02fa01397e564e2cd62fc10da7fbc052eab1c57e49792d1950526b6e938ab2cfcc5f88deea6011e3'},
              'OE': {'hex': '61a90ed9f9c5dbc2781fe8f355b7a4ed50c83bc3dd1f92d87524a0bfbe9aa25e'},
              'P': 4294967292,
              'Perms': {'hex': '09b85a263e5a849d26c12d525cb917d6'},
              'R': 6,
              'StmF': 'StdCF',
              'StrF': 'StdCF',
              'U': {'hex': '52b9ed4bcc978603b9e9adb2a7a5f86bd9b12cb5ee271cff733d8dbad986999b59cd7c3a39ef613ee22063d6441be855'},
              'UE': {'hex': '24d134d3f1654cb85d06bc76a045b1317cc9683788ee57b604c77c50daab30e0'},
              'V': 5},
  'id': '6637313137306437313434353762633866336463373339643066616435663935',
  'derived': 'c4affe3cc7baf545fa6ea48f6318af20a037ebd29e5340577cbc26866f37e0c8',
  'name': 'AES-256-sasl',
  'password': 'SaSLprep'}]


def _decode(value):
    if isinstance(value, dict):
        if set(value) == {"hex"}:
            return bytes.fromhex(value["hex"])
        return {key: _decode(item) for key, item in value.items()}
    return value


def _pdf_value(value):
    if isinstance(value, bytes):
        return b"<" + value.hex().encode("ascii") + b">"
    if isinstance(value, str):
        return b"/" + value.encode("ascii")
    if isinstance(value, dict):
        return b"<< " + b" ".join(b"/" + k.encode("ascii") + b" " + _pdf_value(v)
                                    for k, v in value.items()) + b" >>"
    return str(value).encode("ascii")


def _build_pdf(vector):
    cipher = bytes.fromhex(vector["cipher"])
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] "
            b"/Resources << /Font << /F1 5 0 R >> >> /Contents 6 0 R >>",
            _pdf_value(_decode(vector["encrypt"])),
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
            b"<< /Length " + str(len(cipher)).encode("ascii") + b" >>\nstream\n" +
            cipher + b"\nendstream"]
    data = bytearray(b"%PDF-1.7\n")
    offsets = [0]
    for number, obj in enumerate(objs, 1):
        offsets.append(len(data))
        data.extend(str(number).encode("ascii") + b" 0 obj\n" + obj + b"\nendobj\n")
    xref = len(data)
    data.extend(b"xref\n0 7\n0000000000 65535 f \n")
    for offset in offsets[1:]:
        data.extend(("%010d 00000 n \n" % offset).encode("ascii"))
    doc_id = vector["id"].encode("ascii")
    data.extend(b"trailer\n<< /Size 7 /Root 1 0 R /Encrypt 4 0 R /ID [<" + doc_id +
                b"><" + doc_id + b">] >>\nstartxref\n" + str(xref).encode("ascii") + b"\n%%EOF")
    return bytes(data)


@pytest.mark.parametrize("vector", VECTORS, ids=lambda v: v["name"])
def test_user_password_known_key_and_plaintext(vector):
    handler = StandardSecurityHandler(_decode(vector["encrypt"]),
                                      bytes.fromhex(vector["id"]), vector["password"])
    assert handler.key == bytes.fromhex(vector["derived"])
    assert handler.decrypt(6, 0, bytes.fromhex(vector["cipher"])) == (
        b"BT /F1 12 Tf 10 100 Td (Protected text) Tj ET")


@pytest.mark.parametrize("vector", VECTORS[:5], ids=lambda v: v["name"])
def test_pdfreader_user_password_extracts_text(tmp_path, vector):
    path = tmp_path / "protected.pdf"
    path.write_bytes(_build_pdf(vector))
    doc = PDFReader(password=vector["password"]).read(str(path))
    assert doc.errors == []
    assert "Protected text" in "\n".join(p.text for s in doc.sections for p in s.elements
                                           if hasattr(p, "text"))


@pytest.mark.parametrize("vector", VECTORS[:3], ids=lambda v: v["name"])
def test_wrong_password_stops_owner_retry(vector, monkeypatch):
    original = StandardSecurityHandler._owner_user_password
    calls = []
    def owner(self, password):
        calls.append(password)
        assert len(calls) <= 1, "소유자 암호 재시도는 한 번이어야 한다"
        return original(self, password)
    monkeypatch.setattr(StandardSecurityHandler, "_owner_user_password", owner)
    with pytest.raises(UnsupportedEncryption):
        StandardSecurityHandler(_decode(vector["encrypt"]),
                                bytes.fromhex(vector["id"]), b"wrong")
    assert len(calls) == 1


def test_r6_password_uses_saslprep():
    vector = VECTORS[-1]
    handler = StandardSecurityHandler(_decode(vector["encrypt"]),
                                      bytes.fromhex(vector["id"]), "SªSL\u00adprep")
    assert handler.key == bytes.fromhex(vector["derived"])


def test_r6_password_rejects_prohibited_control():
    vector = VECTORS[-1]
    with pytest.raises(UnsupportedEncryption):
        StandardSecurityHandler(_decode(vector["encrypt"]),
                                bytes.fromhex(vector["id"]), "bad\x07password")


@pytest.mark.parametrize("vector", VECTORS[:5], ids=lambda v: v["name"])
def test_owner_password_opens_user_protected_document(vector):
    handler = StandardSecurityHandler(_decode(vector["encrypt"]),
                                      bytes.fromhex(vector["id"]), "owner")
    assert handler.key == bytes.fromhex(vector["derived"])


@pytest.mark.parametrize("vector", VECTORS[3:5], ids=lambda v: v["name"])
def test_aes256_wrong_password_is_rejected(vector):
    with pytest.raises(UnsupportedEncryption):
        StandardSecurityHandler(_decode(vector["encrypt"]),
                                bytes.fromhex(vector["id"]), b"wrong")


def test_identity_string_filter_preserves_unencrypted_strings():
    vector = VECTORS[2]
    encrypt = _decode(vector["encrypt"])
    encrypt["StrF"] = "Identity"
    handler = StandardSecurityHandler(encrypt, bytes.fromhex(vector["id"]), b"user")
    assert handler.decrypt(6, 0, b"plain annotation", is_stream=False) == b"plain annotation"
    assert handler.decrypt(6, 0, bytes.fromhex(vector["cipher"])).startswith(b"BT ")


@pytest.mark.parametrize("revision", [2, 3, 4, 5, 6])
def test_malformed_encryption_dictionary_is_rejected(revision):
    with pytest.raises(UnsupportedEncryption):
        StandardSecurityHandler({"V": 5 if revision >= 5 else 2,
                                 "R": revision, "Length": 0}, b"id", b"user")


@pytest.mark.parametrize("vector", VECTORS[:3], ids=lambda v: v["name"])
def test_legacy_password_string_uses_pdfdocencoding(vector):
    """PDFDocEncoding Euro=0xa0; O is fixed independently of this user check."""
    import hashlib
    import struct
    from dochan.pdf.crypto import _PAD, rc4
    encrypt = _decode(vector["encrypt"])
    doc_id = bytes.fromhex(vector["id"])
    n = encrypt["Length"] // 8
    digest = hashlib.md5((b"\xa0" + _PAD)[:32] + encrypt["O"] +
                         struct.pack("<I", encrypt["P"]) + doc_id).digest()
    if encrypt["R"] >= 3:
        for _ in range(50):
            digest = hashlib.md5(digest[:n]).digest()
    key = digest[:n]
    if encrypt["R"] == 2:
        encrypt["U"] = rc4(key, _PAD)
    else:
        user = rc4(key, hashlib.md5(_PAD + doc_id).digest())
        for i in range(1, 20):
            user = rc4(bytes(c ^ i for c in key), user)
        encrypt["U"] = user + b"\x00" * 16
    assert StandardSecurityHandler(encrypt, doc_id, b"\xa0").key == key
    assert StandardSecurityHandler(encrypt, doc_id, "€").key == key


@pytest.mark.parametrize("vector", VECTORS[3:5], ids=lambda v: v["name"])
def test_aes256_length_omission_is_valid(vector):
    encrypt = _decode(vector["encrypt"])
    del encrypt["Length"]
    handler = StandardSecurityHandler(encrypt, bytes.fromhex(vector["id"]), "user")
    assert handler.key == bytes.fromhex(vector["derived"])
    assert handler.decrypt(6, 0, bytes.fromhex(vector["cipher"])) == (
        b"BT /F1 12 Tf 10 100 Td (Protected text) Tj ET")


def test_supplied_wrong_password_warning_does_not_claim_empty_password(tmp_path):
    path = tmp_path / "wrong-password.pdf"
    path.write_bytes(_build_pdf(VECTORS[0]))
    doc = PDFReader(password="wrong").read(str(path))
    assert doc.errors
    assert any("제공 암호" in warning for warning in doc.errors)
    assert all("빈 암호" not in warning for warning in doc.errors)


@pytest.mark.parametrize("identity_field", [None, "StmF", "StrF"])
@pytest.mark.parametrize("explicit_cf_length", [True, False])
def test_v4_aesv2_omitted_root_length_uses_active_cipher(identity_field, explicit_cf_length):
    vector = VECTORS[2]
    encrypt = _decode(vector["encrypt"])
    del encrypt["Length"]
    if not explicit_cf_length:
        del encrypt["CF"]["StdCF"]["Length"]
    if identity_field:
        encrypt[identity_field] = "Identity"
    handler = StandardSecurityHandler(encrypt, bytes.fromhex(vector["id"]), "user")
    assert handler.key == bytes.fromhex(vector["derived"])


@pytest.mark.parametrize("length", [5, 16])
def test_v4_rc4_omitted_root_length_uses_cf_bytes(length):
    import hashlib
    import struct
    from dochan.pdf.crypto import _PAD, rc4
    vector = VECTORS[1]
    encrypt = _decode(vector["encrypt"])
    del encrypt["Length"]
    encrypt.update(V=4, R=4, StmF="StdCF", StrF="StdCF",
                   CF={"StdCF": {"CFM": "V2", "Length": length}})
    doc_id = bytes.fromhex(vector["id"])
    digest = hashlib.md5((b"user" + _PAD)[:32] + encrypt["O"] +
                         struct.pack("<I", encrypt["P"]) + doc_id).digest()
    for _ in range(50):
        digest = hashlib.md5(digest[:length]).digest()
    key = digest[:length]
    user = rc4(key, hashlib.md5(_PAD + doc_id).digest())
    for i in range(1, 20):
        user = rc4(bytes(c ^ i for c in key), user)
    encrypt["U"] = user + b"\x00" * 16
    handler = StandardSecurityHandler(encrypt, doc_id, "user")
    assert handler.key == key
    assert handler.length_bits == length * 8


@pytest.mark.parametrize("length", [0, -1, 5, 17, 16.0, "16", True])
def test_v4_aesv2_invalid_cf_length_is_rejected(length):
    vector = VECTORS[2]
    encrypt = _decode(vector["encrypt"])
    del encrypt["Length"]
    encrypt["CF"]["StdCF"]["Length"] = length
    with pytest.raises(UnsupportedEncryption, match="암호 필터 키 길이"):
        StandardSecurityHandler(encrypt, bytes.fromhex(vector["id"]), "user")


def test_v4_conflicting_active_cf_lengths_are_rejected():
    vector = VECTORS[2]
    encrypt = _decode(vector["encrypt"])
    del encrypt["Length"]
    encrypt["StrF"] = "ShortCF"
    encrypt["CF"]["ShortCF"] = {"CFM": "V2", "Length": 5}
    with pytest.raises(UnsupportedEncryption, match="서로 다른 암호 필터 키 길이"):
        StandardSecurityHandler(encrypt, bytes.fromhex(vector["id"]), "user")


def test_v4_explicit_root_length_retains_precedence_over_cf_length():
    vector = VECTORS[2]
    encrypt = _decode(vector["encrypt"])
    encrypt["CF"]["StdCF"]["Length"] = 5
    handler = StandardSecurityHandler(encrypt, bytes.fromhex(vector["id"]), "user")
    assert handler.key == bytes.fromhex(vector["derived"])
