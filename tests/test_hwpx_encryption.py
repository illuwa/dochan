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


def _package(path, *, password='private-password', change=None, with_image=False):
    parts = {
        'Contents/header.xml': b'<head/>',
        'Contents/section0.xml': SECTION,
        'Preview/PrvText.txt': b'Encrypted body',
    }
    if with_image:
        parts['Contents/section0.xml'] = SECTION.replace(
            b'</hp:run>', b'<hp:pic><hp:img binaryItemIDRef="image1"/>'
            b'</hp:pic></hp:run>')
        parts['BinData/image1.png'] = b'\x89PNG\r\n\x1a\nimage data'
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
            if change == 'checksum-image' and name.endswith('image1.png'):
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
    if damage == 'large-spin':
        assert any('암호 반복 작업량 상한 초과' in error for error in doc.errors)
    else:
        assert any(error.startswith('ERR: 지원하지 않는 HWPX 암호화') for error in doc.errors)
    assert all('파싱 실패' not in error for error in doc.errors)


def test_hwpx_open_password_rejects_checksum_mismatch(tmp_path):
    doc = Dochan(str(_package(tmp_path / 'encrypted.hwpx', change='checksum')),
                 password='private-password').doc
    assert any(error.startswith('ERR: 암호화된 HWPX 문서') for error in doc.errors)


def test_hwpx_open_password_skips_unreferenced_encrypted_parts(tmp_path):
    doc = Dochan(str(_package(tmp_path / 'encrypted.hwpx', change='checksum-preview')),
                 password='private-password').doc
    assert 'Encrypted body' in to_markdown(doc)
    assert not [error for error in doc.errors if error.startswith('ERR:')]


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


@pytest.mark.parametrize('damage', ['oversize', 'crc'])
def test_unencrypted_manifest_damage_preserves_body(tmp_path, damage):
    path = tmp_path / 'plain.hwpx'
    manifest = b'<manifest>' + b'x' * (1024 * 1024 if damage == 'oversize' else 0) + b'</manifest>'
    with zipfile.ZipFile(path, 'w') as zf:
        zf.writestr('mimetype', 'application/hwp+zip')
        zf.writestr('Contents/header.xml', b'<head/>')
        zf.writestr('Contents/section0.xml', SECTION)
        zf.writestr('META-INF/manifest.xml', manifest)
    if damage == 'crc':
        raw = bytearray(path.read_bytes())
        offset = raw.index(b'<manifest>')
        raw[offset + 1] ^= 1
        path.write_bytes(raw)
    doc = Dochan(str(path)).doc
    assert 'Encrypted body' in to_markdown(doc)
    assert not [error for error in doc.errors if error.startswith('ERR:')]


def test_wrong_password_stops_before_large_ciphertext(tmp_path, monkeypatch):
    path = _package(tmp_path / 'large.hwpx')
    with zipfile.ZipFile(path) as zf:
        items = {name: zf.read(name) for name in zf.namelist()}
    items['Contents/header.xml'] = bytes(2 * 1024 * 1024)
    with zipfile.ZipFile(path, 'w') as zf:
        for name, data in items.items():
            zf.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
    import dochan.hwpx.crypto as crypto
    original = crypto._aes
    decrypted = [0]

    def counted(key, data, iv=None, **kwargs):
        decrypted[0] += len(data)
        return original(key, data, iv, **kwargs)

    monkeypatch.setattr(crypto, '_aes', counted)
    doc = Dochan(str(path), password='wrong').doc
    assert any('암호가 틀리거나' in error for error in doc.errors)
    assert decrypted[0] <= 65536


def test_prefixed_manifest_attributes_and_forbidden_paths(tmp_path):
    path = _package(tmp_path / 'prefixed.hwpx')
    with zipfile.ZipFile(path) as zf:
        items = {name: zf.read(name) for name in zf.namelist()}
    manifest = items['META-INF/manifest.xml'].decode()
    for attr in ('full-path', 'size', 'checksum-type', 'checksum',
                 'algorithm-name', 'initialisation-vector', 'key-derivation-name',
                 'key-size', 'iteration-count', 'salt', 'start-key-generation-name'):
        manifest = manifest.replace(' ' + attr + '=', ' odf:' + attr + '=')
    items['META-INF/manifest.xml'] = manifest.encode()
    with zipfile.ZipFile(path, 'w') as zf:
        for name, data in items.items():
            zf.writestr(name, data)
    assert 'Encrypted body' in to_markdown(Dochan(str(path), password='private-password').doc)
    for forbidden in ('mimetype', 'META-INF/manifest.xml'):
        with zipfile.ZipFile(path) as zf:
            data = zf.read('META-INF/manifest.xml')
            names = set(zf.namelist())
        with pytest.raises(ValueError, match='지원하지 않는 HWPX 암호화'):
            read_encryption_manifest(data.replace(b'Contents/header.xml', forbidden.encode(), 1),
                                     names, HWPXParser._encrypted_limit)


def test_unused_preview_checksum_is_warning_and_password_cleared(tmp_path):
    parser = HWPXParser()
    doc = parser.parse(str(_package(tmp_path / 'preview.hwpx', change='checksum-preview')),
                       password='private-password')
    assert 'Encrypted body' in to_markdown(doc)
    assert not [error for error in doc.errors if error.startswith('ERR:')]
    assert parser._password is None
    assert not hasattr(parser, '_encrypted_cache')


def test_optional_encrypted_image_failure_is_warning(tmp_path):
    path = _package(tmp_path / 'image.hwpx', change='checksum-image', with_image=True)
    doc = Dochan(str(path), password='private-password').doc
    assert 'Encrypted body' in to_markdown(doc)
    assert not [error for error in doc.errors if error.startswith('ERR:')]
    assert any('이미지' in error and '복호화 실패' in error for error in doc.errors)
    without_assets = Dochan(str(path), password='private-password', include_assets=False).doc
    assert 'Encrypted body' in to_markdown(without_assets)
    assert not any('복호화 실패' in error for error in without_assets.errors)


def test_repeated_part_respects_requested_limit(tmp_path):
    parser = HWPXParser()
    path = _package(tmp_path / 'cache.hwpx')
    with zipfile.ZipFile(path) as zf:
        parser._password = 'private-password'
        parser._encrypted_parts = read_encryption_manifest(
            zf.read('META-INF/manifest.xml'), set(zf.namelist()), parser._encrypted_limit)
        assert parser._read_zip_part(zf, 'Contents/header.xml', 1024)
        with pytest.raises(ValueError):
            parser._read_zip_part(zf, 'Contents/header.xml', 1)


def test_repeated_key_derivation_is_counted_once(tmp_path):
    path = _package(tmp_path / 'keys.hwpx')
    with zipfile.ZipFile(path) as zf:
        metadata = read_encryption_manifest(zf.read('META-INF/manifest.xml'),
                                            set(zf.namelist()), HWPXParser._encrypted_limit)
        ciphertext = zf.read('Contents/header.xml')
    budget = [1024]
    cache = {}
    for _ in range(4):
        assert decrypt_part(ciphertext, metadata['Contents/header.xml'],
                            'private-password', 1024, budget, cache) == b'<head/>'
    assert budget == [0]
    assert len(cache) == 1


def test_many_encrypted_parts_share_one_key_budget(tmp_path):
    path = _package(tmp_path / 'many.hwpx')
    with zipfile.ZipFile(path) as zf:
        items = {name: zf.read(name) for name in zf.namelist()}
    manifest = items['META-INF/manifest.xml']
    start = manifest.index(b'<odf:file-entry full-path="Preview/PrvText.txt"')
    end = manifest.index(b'</odf:file-entry>', start) + len(b'</odf:file-entry>')
    template = manifest[start:end]
    extra = {}
    entries = []
    for index in range(990):
        name = 'BinData/unused%04d.bin' % index
        extra[name] = items['Preview/PrvText.txt']
        entries.append(template.replace(b'Preview/PrvText.txt', name.encode()))
    items['META-INF/manifest.xml'] = manifest.replace(
        b'</odf:manifest>', b''.join(entries) + b'</odf:manifest>')
    with zipfile.ZipFile(path, 'w') as zf:
        for name, data in list(items.items()) + list(extra.items()):
            zf.writestr(name, data)
    doc = Dochan(str(path), password='private-password').doc
    assert 'Encrypted body' in to_markdown(doc)
    assert not [error for error in doc.errors if error.startswith('ERR:')]


def test_manifest_preflights_distinct_key_work(tmp_path):
    path = _package(tmp_path / 'work.hwpx')
    with zipfile.ZipFile(path) as zf:
        manifest = zf.read('META-INF/manifest.xml')
        names = set(zf.namelist())
    same = manifest.replace(b'iteration-count="1024"', b'iteration-count="1000000"')
    assert len(read_encryption_manifest(same, names, HWPXParser._encrypted_limit)) == 3
    distinct = same.replace(b'salt="AAECAwQFBgcICQoLDA0ODw=="',
                            b'salt="AQEBAQEBAQEBAQEBAQEBAQ=="', 1)
    with pytest.raises(ValueError, match='암호 반복 작업량 상한 초과'):
        read_encryption_manifest(distinct, names, HWPXParser._encrypted_limit)


def test_encrypted_aes_budget_is_bounded(tmp_path):
    path = _package(tmp_path / 'budget.hwpx')
    with zipfile.ZipFile(path) as zf:
        metadata = read_encryption_manifest(zf.read('META-INF/manifest.xml'),
                                            set(zf.namelist()), HWPXParser._encrypted_limit)
        ciphertext = zf.read('Contents/header.xml')
    from dochan.hwpx.crypto import AESBudget
    aes_budget = AESBudget()
    aes_budget.remaining = 0
    with pytest.raises(ValueError, match='AES 작업량 상한 초과'):
        decrypt_part(ciphertext, metadata['Contents/header.xml'], 'private-password',
                     1024, [1000000], aes_budget=aes_budget)
