"""PDF 표준 보안 핸들러 복호화 테스트.

두 층위로 검증한다:
1. 암호 프리미티브(RC4/AES) — RFC 6229 / NIST SP 800-38A 공인 시험 벡터
2. 엔드투엔드 — pikepdf(=qpdf, 참조 인코더)로 만든 최소 암호화 PDF 를
   base64 로 임베드해 dochan 이 평문("Secret Text")을 복원하는지 확인
"""
import base64
import binascii

from dochan.pdf.crypto import rc4
from dochan.pdf.reader import PDFReader
from dochan.utils.aes import aes_cbc_decrypt_no_pad, aes_cbc_encrypt_no_pad


# ── 프리미티브: RC4 (RFC 6229 test vectors, key "Key"/"Wiki") ──

def test_rc4_known_answer():
    # 위키/RFC 예시: Key="Key", Plaintext="Plaintext" → BBF316E8D940AF0AD3
    assert binascii.hexlify(rc4(b"Key", b"Plaintext")).upper() == b"BBF316E8D940AF0AD3"
    # 대칭성 — 두 번 적용하면 원문
    assert rc4(b"Key", rc4(b"Key", b"round trip")) == b"round trip"


# ── 프리미티브: AES-256-CBC (NIST SP 800-38A F.2.5/F.2.6) ──

def test_aes256_cbc_nist_vector():
    key = binascii.unhexlify(
        "603deb1015ca71be2b73aef0857d7781"
        "1f352c073b6108d72d9810a30914dff4"
    )
    iv = binascii.unhexlify("000102030405060708090a0b0c0d0e0f")
    plain = binascii.unhexlify("6bc1bee22e409f96e93d7e117393172a")
    cipher = binascii.unhexlify("f58c4c04d6e5f1ba779eabfb5f7bfbd6")

    assert aes_cbc_encrypt_no_pad(key, iv, plain) == cipher
    assert aes_cbc_decrypt_no_pad(key, iv, cipher) == plain


def test_aes128_cbc_nist_vector():
    key = binascii.unhexlify("2b7e151628aed2a6abf7158809cf4f3c")
    iv = binascii.unhexlify("000102030405060708090a0b0c0d0e0f")
    plain = binascii.unhexlify("6bc1bee22e409f96e93d7e117393172a")
    cipher = binascii.unhexlify("7649abac8119b246cee98e9b12e9197d")

    assert aes_cbc_encrypt_no_pad(key, iv, plain) == cipher
    assert aes_cbc_decrypt_no_pad(key, iv, cipher) == plain


# ── 엔드투엔드: 참조 인코더가 만든 최소 암호화 PDF (빈 사용자 암호) ──
# pikepdf(qpdf) 로 생성한 1페이지 "Secret Text" 문서. 각 암호 방식별 1개.

RC4_R3 = 'JVBERi0xLjQKJb/3ov4KMSAwIG9iago8PCAvUGFnZXMgMiAwIFIgL1R5cGUgL0NhdGFsb2cgPj4KZW5kb2JqCjIgMCBvYmoKPDwgL0NvdW50IDEgL0tpZHMgWyAzIDAgUiBdIC9UeXBlIC9QYWdlcyA+PgplbmRvYmoKMyAwIG9iago8PCAvQ29udGVudHMgNCAwIFIgL01lZGlhQm94IFsgMCAwIDIwMCAyMDAgXSAvUGFyZW50IDIgMCBSIC9SZXNvdXJjZXMgPDwgL0ZvbnQgPDwgL0YxIDw8IC9CYXNlRm9udCAvSGVsdmV0aWNhIC9TdWJ0eXBlIC9UeXBlMSAvVHlwZSAvRm9udCA+PiA+PiA+PiAvVHlwZSAvUGFnZSA+PgplbmRvYmoKNCAwIG9iago8PCAvTGVuZ3RoIDUwIC9GaWx0ZXIgL0ZsYXRlRGVjb2RlID4+CnN0cmVhbQryYPxedZ3EWSCzgCGsfgCqyJ4vztmZsN6NUeno7rZQ9cAfRd4xGwdiqUcFyH1hKFo3yAplbmRzdHJlYW0KZW5kb2JqCjUgMCBvYmoKPDwgL0ZpbHRlciAvU3RhbmRhcmQgL0xlbmd0aCAxMjggL08gPDc3YjhmYjA5ODAyMmQzYWIzNDIzN2VhNTY0M2MwODcxMGVhNTEyM2ZjNWY4OGJmOTkzYTY4Y2NhNWYxMmI0MGY+IC9QIC0xMDI4IC9SIDMgL1UgPDMxMDc3M2Q5MzZjNDIwODEzZWRlNWY1ZjJiZDQ5NjJmMDEyMjQ1NmE5MWJhZTUxMzQyNzNhNmRiMTM0Yzg3YzQ+IC9WIDIgPj4KZW5kb2JqCnhyZWYKMCA2CjAwMDAwMDAwMDAgNjU1MzUgZiAKMDAwMDAwMDAxNSAwMDAwMCBuIAowMDAwMDAwMDY0IDAwMDAwIG4gCjAwMDAwMDAxMjMgMDAwMDAgbiAKMDAwMDAwMDMwMCAwMDAwMCBuIAowMDAwMDAwNDIxIDAwMDAwIG4gCnRyYWlsZXIgPDwgL1Jvb3QgMSAwIFIgL1NpemUgNiAvSUQgWzxkMjI5NTI4MTcxYzU4OTYxMmE1MTAwYjFlMDc0MjQxNT48ZDIyOTUyODE3MWM1ODk2MTJhNTEwMGIxZTA3NDI0MTU+XSAvRW5jcnlwdCA1IDAgUiA+PgpzdGFydHhyZWYKNjMxCiUlRU9GCg=='

AES128_R4 = 'JVBERi0xLjYKJb/3ov4KMSAwIG9iago8PCAvUGFnZXMgMiAwIFIgL1R5cGUgL0NhdGFsb2cgPj4KZW5kb2JqCjIgMCBvYmoKPDwgL0NvdW50IDEgL0tpZHMgWyAzIDAgUiBdIC9UeXBlIC9QYWdlcyA+PgplbmRvYmoKMyAwIG9iago8PCAvQ29udGVudHMgNCAwIFIgL01lZGlhQm94IFsgMCAwIDIwMCAyMDAgXSAvUGFyZW50IDIgMCBSIC9SZXNvdXJjZXMgPDwgL0ZvbnQgPDwgL0YxIDw8IC9CYXNlRm9udCAvSGVsdmV0aWNhIC9TdWJ0eXBlIC9UeXBlMSAvVHlwZSAvRm9udCA+PiA+PiA+PiAvVHlwZSAvUGFnZSA+PgplbmRvYmoKNCAwIG9iago8PCAvTGVuZ3RoIDgwIC9GaWx0ZXIgL0ZsYXRlRGVjb2RlID4+CnN0cmVhbQpQbgfoNad+UZkq4vWapbKWtCqEwysKlTCDyOI7AalFp8pu4bceUu7E6V2DEqYD279X2NIdso/8B81irUBwIdYuO2+NKrcYpXqsf+3VXGKmfAplbmRzdHJlYW0KZW5kb2JqCjUgMCBvYmoKPDwgL0NGIDw8IC9TdGRDRiA8PCAvQXV0aEV2ZW50IC9Eb2NPcGVuIC9DRk0gL0FFU1YyIC9MZW5ndGggMTYgPj4gPj4gL0ZpbHRlciAvU3RhbmRhcmQgL0xlbmd0aCAxMjggL08gPDc3YjhmYjA5ODAyMmQzYWIzNDIzN2VhNTY0M2MwODcxMGVhNTEyM2ZjNWY4OGJmOTkzYTY4Y2NhNWYxMmI0MGY+IC9QIC0xMDI4IC9SIDQgL1N0bUYgL1N0ZENGIC9TdHJGIC9TdGRDRiAvVSA8MzEwNzczZDkzNmM0MjA4MTNlZGU1ZjVmMmJkNDk2MmYwMTIyNDU2YTkxYmFlNTEzNDI3M2E2ZGIxMzRjODdjND4gL1YgNCA+PgplbmRvYmoKeHJlZgowIDYKMDAwMDAwMDAwMCA2NTUzNSBmIAowMDAwMDAwMDE1IDAwMDAwIG4gCjAwMDAwMDAwNjQgMDAwMDAgbiAKMDAwMDAwMDEyMyAwMDAwMCBuIAowMDAwMDAwMzAwIDAwMDAwIG4gCjAwMDAwMDA0NTEgMDAwMDAgbiAKdHJhaWxlciA8PCAvUm9vdCAxIDAgUiAvU2l6ZSA2IC9JRCBbPGQyMjk1MjgxNzFjNTg5NjEyYTUxMDBiMWUwNzQyNDE1PjxkMjI5NTI4MTcxYzU4OTYxMmE1MTAwYjFlMDc0MjQxNT5dIC9FbmNyeXB0IDUgMCBSID4+CnN0YXJ0eHJlZgo3NTMKJSVFT0YK'

AES256_R6 = 'JVBERi0xLjcKJb/3ov4KMSAwIG9iago8PCAvRXh0ZW5zaW9ucyA8PCAvQURCRSA8PCAvQmFzZVZlcnNpb24gLzEuNyAvRXh0ZW5zaW9uTGV2ZWwgOCA+PiA+PiAvUGFnZXMgMiAwIFIgL1R5cGUgL0NhdGFsb2cgPj4KZW5kb2JqCjIgMCBvYmoKPDwgL0NvdW50IDEgL0tpZHMgWyAzIDAgUiBdIC9UeXBlIC9QYWdlcyA+PgplbmRvYmoKMyAwIG9iago8PCAvQ29udGVudHMgNCAwIFIgL01lZGlhQm94IFsgMCAwIDIwMCAyMDAgXSAvUGFyZW50IDIgMCBSIC9SZXNvdXJjZXMgPDwgL0ZvbnQgPDwgL0YxIDw8IC9CYXNlRm9udCAvSGVsdmV0aWNhIC9TdWJ0eXBlIC9UeXBlMSAvVHlwZSAvRm9udCA+PiA+PiA+PiAvVHlwZSAvUGFnZSA+PgplbmRvYmoKNCAwIG9iago8PCAvTGVuZ3RoIDgwIC9GaWx0ZXIgL0ZsYXRlRGVjb2RlID4+CnN0cmVhbQpcKzvZJdnILx0eDPrHggcrTS1MwMVAO8aJU7UD49CfE0lb2sAHNZduy8Tf47WSUvatSh855x0vKRzMtDxFPStt178rDikXEmC6jhK1ySyHzwplbmRzdHJlYW0KZW5kb2JqCjUgMCBvYmoKPDwgL0NGIDw8IC9TdGRDRiA8PCAvQXV0aEV2ZW50IC9Eb2NPcGVuIC9DRk0gL0FFU1YzIC9MZW5ndGggMzIgPj4gPj4gL0ZpbHRlciAvU3RhbmRhcmQgL0xlbmd0aCAyNTYgL08gPDFlMjcwZWFhMzNlMDNhMjg0MDU1YzFjZGIyZWE3NWU1Y2VjZjM5NTUyMWUxMGRkOGU1NDg5OWEwZjhhNjQyMjRmMmIyMGQ0NTkyZGI3OTNlZDA4OWU3NmVhZjljNTg2Mz4gL09FIDxiZWE2MWM2NTRjZDBlYTg0YTk5MzBiOTQ5NTA2ZmY3MWRlYmQwNGJiNjE5NDVkZGE1MjZjYTg5YjFkNDUwNTRkPiAvUCAtMTAyOCAvUGVybXMgPDdiYmE1Mjg2NDMyYTVlZjNlOGY5ZWViZDJlNTE0MTIxPiAvUiA2IC9TdG1GIC9TdGRDRiAvU3RyRiAvU3RkQ0YgL1UgPGNkOWIxYzU1OThjOTUxOWQ5Yzc2YWU5ZGEyNzdjZDE2ZWE0ZDMyZWEzMmE4NDAxYjc2ZjhhMDI0YTM2YWVjMmRiNDQ3NDU5MDg3YWM3M2I0ZjAyZDUyZDdiNmFiMTc2Nj4gL1VFIDxiM2FmMGQyMjRjMWE3NTE4MDEzYzY2NzNiMDkwYmEzYzE5YzA3MzExODUyZGNlMmQxYjE5NmZjYjAxMzI2MzI4PiAvViA1ID4+CmVuZG9iagp4cmVmCjAgNgowMDAwMDAwMDAwIDY1NTM1IGYgCjAwMDAwMDAwMTUgMDAwMDAgbiAKMDAwMDAwMDEzMCAwMDAwMCBuIAowMDAwMDAwMTg5IDAwMDAwIG4gCjAwMDAwMDAzNjYgMDAwMDAgbiAKMDAwMDAwMDUxNyAwMDAwMCBuIAp0cmFpbGVyIDw8IC9Sb290IDEgMCBSIC9TaXplIDYgL0lEIFs8ZDIyOTUyODE3MWM1ODk2MTJhNTEwMGIxZTA3NDI0MTU+PGQyMjk1MjgxNzFjNTg5NjEyYTUxMDBiMWUwNzQyNDE1Pl0gL0VuY3J5cHQgNSAwIFIgPj4Kc3RhcnR4cmVmCjEwNjcKJSVFT0YK'


def _decrypt_and_read(b64: str):
    import os
    import tempfile

    data = base64.b64decode(b64)
    fd, path = tempfile.mkstemp(suffix=".pdf")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        doc = PDFReader().read(path)
        text = "\n".join(
            p.text for s in doc.sections for p in s.elements if hasattr(p, "text")
        )
        return text, doc.errors
    finally:
        os.unlink(path)


def test_rc4_r3_empty_password_decrypts():
    text, errors = _decrypt_and_read(RC4_R3)
    assert "Secret Text" in text
    assert errors == []


def test_aes128_r4_empty_password_decrypts():
    text, errors = _decrypt_and_read(AES128_R4)
    assert "Secret Text" in text
    assert errors == []


def test_aes256_r6_empty_password_decrypts():
    text, errors = _decrypt_and_read(AES256_R6)
    assert "Secret Text" in text
    assert errors == []
