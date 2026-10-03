"""HWPX opening-password regression tests with in-memory encrypted parts."""
import base64
import hashlib
import io
import os
import zipfile
import zlib
from pathlib import Path

import pytest

from dochan import Dochan
from dochan.cli import main
from dochan.hwpx.crypto import decrypt_part, read_encryption_manifest
from dochan.hwpx.parser import HWPXParser
from dochan.output.markdown import to_markdown
from dochan.utils.aes import _encrypt_block, _key_expansion


NS = 'urn:oasis:names:tc:opendocument:xmlns:manifest:1.0'
SECTION = (b'<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
           b'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
           b'<hp:p><hp:run><hp:t>Encrypted body</hp:t></hp:run></hp:p></hs:sec>')


def _b64(data):
    return base64.b64encode(data).decode('ascii')


def _encrypt(key, iv, data):
    schedule = _key_expansion(key)
    result = bytearray()
    for offset in range(0, len(data), 16):
        block = bytes(a ^ b for a, b in zip(data[offset:offset + 16], iv))
        iv = _encrypt_block(block, schedule, 14)
        result.extend(iv)
    return bytes(result)


def _package(path, *, password='private-password', change=None):
    parts = {
        'Contents/header.xml': b'<head/>',
        'Contents/section0.xml': SECTION,
        'Preview/PrvText.txt': b'Encrypted body',
    }
    entries = []
    salt = bytes(range(16))
    iv = bytes(range(16, 32))
    start = hashlib.sha256(password.encode('utf-8')).digest()
    key = hashlib.pbkdf2_hmac('sha1', start, salt, 1024, 32)
    with zipfile.ZipFile(path, 'w') as zf:
        zf.writestr('mimetype', 'application/hwp+zip')
        for name, plain in parts.items():
            compressor = zlib.compressobj(wbits=-15)
            compressed = compressor.compress(plain) + compressor.flush()
            compressed += b'\0' * (-len(compressed) % 16)
            encrypted = _encrypt(key, iv, compressed)
            if change == 'truncated' and name.endswith('section0.xml'):
                encrypted = encrypted[:-1]
            zf.writestr(name, encrypted)
            attrs = {
                'algorithm-name': 'http://www.w3.org/2001/04/xmlenc#aes256-cbc',
                'key-derivation-name': NS + '#pbkdf2',
                'checksum-type': NS + '#sha256-1k',
                'start-key-generation-name': 'http://www.w3.org/2000/09/xmldsig#sha256',
                'initialisation-vector': _b64(iv), 'salt': _b64(salt),
                'checksum': _b64(hashlib.sha256(plain[:1024]).digest()),
                'iteration-count': '1024', 'key-size': '32', 'size': str(len(plain)),
            }
            if change == 'bad-base64' and name.endswith('header.xml'):
                attrs['salt'] = '!!!'
            if change == 'short-iv' and name.endswith('header.xml'):
                attrs['initialisation-vector'] = _b64(iv[:8])
            if change == 'large-spin' and name.endswith('header.xml'):
                attrs['iteration-count'] = '1000001'
            if change == 'cipher' and name.endswith('header.xml'):
                attrs['algorithm-name'] = 'other-cipher'
            if change == 'checksum' and name.endswith('header.xml'):
                attrs['checksum'] = _b64(bytes(32))
            if change == 'checksum-preview' and name.endswith('PrvText.txt'):
                attrs['checksum'] = _b64(bytes(32))
            entries.append(
                '<odf:file-entry full-path="%s" size="%s"><odf:encryption-data '
                'checksum-type="%s" checksum="%s"><odf:algorithm algorithm-name="%s" '
                'initialisation-vector="%s"/><odf:key-derivation key-derivation-name="%s" '
                'key-size="%s" iteration-count="%s" salt="%s"/>'
                '<odf:start-key-generation start-key-generation-name="%s" key-size="32"/>'
                '</odf:encryption-data></odf:file-entry>' % (
                    name, attrs['size'], attrs['checksum-type'], attrs['checksum'],
                    attrs['algorithm-name'], attrs['initialisation-vector'],
                    attrs['key-derivation-name'], attrs['key-size'],
                    attrs['iteration-count'], attrs['salt'], attrs['start-key-generation-name'])
            )
        zf.writestr('META-INF/manifest.xml',
                    ('<odf:manifest xmlns:odf="%s">%s</odf:manifest>'
                     % (NS, ''.join(entries))).encode())
    return path


def test_hwpx_open_password_reads_encrypted_body(tmp_path):
    doc = Dochan(str(_package(tmp_path / 'encrypted.hwpx')), password='private-password').doc
    assert not doc.errors
    assert 'Encrypted body' in to_markdown(doc)


@pytest.mark.parametrize('password', [None, 'incorrect-private-password'])
def test_hwpx_open_password_rejects_missing_or_wrong(tmp_path, password):
    doc = Dochan(str(_package(tmp_path / 'encrypted.hwpx')), password=password).doc
    assert any(error.startswith('ERR: 암호화된 HWPX 문서') for error in doc.errors)
    assert all('파싱 실패' not in error for error in doc.errors)
    assert 'incorrect-private-password' not in repr(doc.errors)


@pytest.mark.parametrize('damage', ['bad-base64', 'short-iv', 'truncated', 'large-spin', 'cipher'])
def test_hwpx_open_password_rejects_invalid_encryption(tmp_path, damage):
    doc = Dochan(str(_package(tmp_path / 'encrypted.hwpx', change=damage)),
                 password='private-password').doc
    assert any(error.startswith('ERR: 지원하지 않는 HWPX 암호화') for error in doc.errors)
    assert all('파싱 실패' not in error for error in doc.errors)


def test_hwpx_open_password_rejects_checksum_mismatch(tmp_path):
    doc = Dochan(str(_package(tmp_path / 'encrypted.hwpx', change='checksum')),
                 password='private-password').doc
    assert any(error.startswith('ERR: 암호화된 HWPX 문서') for error in doc.errors)


def test_hwpx_open_password_checks_unreferenced_encrypted_parts(tmp_path):
    doc = Dochan(str(_package(tmp_path / 'encrypted.hwpx', change='checksum-preview')),
                 password='private-password').doc
    assert any(error.startswith('ERR: 암호화된 HWPX 문서') for error in doc.errors)


def test_hwpx_encrypted_part_respects_decompression_limit(tmp_path):
    path = _package(tmp_path / 'encrypted.hwpx')
    with zipfile.ZipFile(path) as zf:
        metadata = read_encryption_manifest(zf.read('META-INF/manifest.xml'),
                                            set(zf.namelist()), HWPXParser._encrypted_limit)
        ciphertext = zf.read('Contents/section0.xml')
    with pytest.raises(ValueError, match='지원하지 않는 HWPX 암호화'):
        decrypt_part(ciphertext, metadata['Contents/section0.xml'],
                     'private-password', 16, [1000000])


@pytest.mark.parametrize('source', ['environment', 'stdin'])
def test_hwpx_cli_password_sources(tmp_path, monkeypatch, capsys, source):
    path = _package(tmp_path / 'encrypted.hwpx')
    args = ['convert', str(path), '--format', 'text']
    if source == 'environment':
        monkeypatch.setenv('DOCHAN_PASSWORD', 'private-password')
    else:
        monkeypatch.setenv('DOCHAN_PASSWORD', 'incorrect-private-password')
        monkeypatch.setattr('sys.stdin', io.StringIO('private-password\n'))
        args.append('--password-stdin')
    assert main(args) == 0
    captured = capsys.readouterr()
    assert 'Encrypted body' in captured.out
    assert 'private-password' not in captured.err


def test_hwpx_cli_wrong_password_has_no_content_or_password(tmp_path, monkeypatch, capsys):
    path = _package(tmp_path / 'encrypted.hwpx')
    monkeypatch.setenv('DOCHAN_PASSWORD', 'incorrect-private-password')
    assert main(['convert', str(path), '--format', 'text']) == 1
    captured = capsys.readouterr()
    assert 'Encrypted body' not in captured.out + captured.err
    assert 'incorrect-private-password' not in captured.out + captured.err
    assert '암호화된 HWPX 문서' in captured.err


def test_public_encrypted_hwpx(tmp_path):
    corpus_root = os.environ.get('DOCHAN_CORPUS')
    if not corpus_root:
        pytest.skip('DOCHAN_CORPUS is unset')
    corpus = Path(corpus_root) / 'hwp-public/hwpx/encrypt.hwpx'
    if not corpus.exists():
        pytest.skip('public HWPX corpus is unavailable')
    doc = Dochan(str(corpus), password='abcde').doc
    assert not [error for error in doc.errors if error.startswith('ERR:')]
    assert len(doc.sections) == 1
    assert len(doc.find_all('image')) == 2
    assert [len(image.image_data) for image in doc.find_all('image')] == [13504, 4923]
    with zipfile.ZipFile(corpus) as zf:
        metadata = read_encryption_manifest(zf.read('META-INF/manifest.xml'),
                                            set(zf.namelist()), HWPXParser._encrypted_limit)
        preview = decrypt_part(zf.read('Preview/PrvText.txt'),
                               metadata['Preview/PrvText.txt'], 'abcde',
                               32 * 1024 * 1024, [1000000]).decode('utf-8')
    # PrvText encloses the second line in display brackets; the body XML
    # stores the same words without them.
    assert preview.replace('\r\n', '\n').strip().replace('<', '').replace('>', '') == '\n\n'.join(
        paragraph.text for paragraph in doc.find_all('paragraph'))


@pytest.mark.parametrize('name', ['156783589', '156784075'])
def test_public_distribution_hwpx_requires_password(name):
    corpus_root = os.environ.get('DOCHAN_CORPUS')
    if not corpus_root:
        pytest.skip('DOCHAN_CORPUS is unset')
    path = Path(corpus_root) / 'press-pairs' / (name + '.hwpx')
    if not path.exists():
        pytest.skip('public press corpus is unavailable')
    doc = Dochan(str(path)).doc
    assert doc.errors == ['ERR: 암호화된 HWPX 문서 — 암호가 필요함']
