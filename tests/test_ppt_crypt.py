"""Synthetic PPT CryptoAPI containers; no external corpus required."""
import hashlib
import struct

import pytest

from dochan.pdf.crypto import rc4


def record(kind, body, options=0):
    return struct.pack('<HHI', options, kind, len(body)) + body


def encrypted_presentation(password='open', key_bits=128):
    salt = bytes(range(16))
    digest = hashlib.sha1(salt + password.encode('utf-16-le')).digest()

    def crypt(data, pid):
        key = hashlib.sha1(digest + struct.pack('<I', pid)).digest()[:key_bits // 8]
        if key_bits == 40:
            key += b'\0' * 11
        return rc4(key, data)

    verifier = b'0123456789abcdef'
    hdr = struct.pack('<8I', 4, 0, 0x6801, 0x8004, key_bits, 1, 0, 0)
    encinfo = struct.pack('<HHII', 4, 2, 4, len(hdr)) + hdr
    encrypted = crypt(verifier + hashlib.sha1(verifier).digest(), 0)
    encinfo += struct.pack('<I', 16) + salt + encrypted[:16] + struct.pack('<I', 20) + encrypted[16:]
    outline = record(1011, struct.pack('<5I', 2, 0, 0, 256, 0)) + record(4008, b'Encrypted slide')
    document = record(1000, record(4080, outline, 15), 15)
    slide = record(1006, b'', 15)
    plain = document + slide
    stream = crypt(document, 1) + crypt(slide, 2)
    crypto_offset = len(stream)
    stream += record(12052, encinfo, 15)
    directory_offset = len(stream)
    stream += record(6002, struct.pack('<4I', (3 << 20) | 1, 0, len(document), crypto_offset))
    edit_offset = len(stream)
    stream += record(4085, struct.pack('<7I', 0, 0, 0, directory_offset, 1, 4, 0) + struct.pack('<I', 3))
    user = record(4086, struct.pack('<IIIHHBBH', 20, 0xF3D1C4DF, edit_offset, 0, 1012, 3, 0, 0))
    return stream, user, plain, crypt


@pytest.mark.parametrize('bits', [40, 56, 128])
def test_ppt_cryptoapi_decrypts_each_persistent_object(bits):
    from dochan.crypto.ppt import decrypt_presentation
    data, user, plain, _ = encrypted_presentation(key_bits=bits)
    decrypted, pictures = decrypt_presentation(data, user, b'', 'open')
    assert decrypted[:len(plain)] == plain
    assert pictures == b''
    assert decrypted[len(plain):] == data[len(plain):]


@pytest.mark.parametrize('password', [None, 'wrong'])
def test_ppt_cryptoapi_rejects_missing_or_wrong_password(password):
    from dochan.crypto.ppt import decrypt_presentation
    data, user, _, _ = encrypted_presentation()
    with pytest.raises(ValueError, match='암호화된 문서') as exc:
        decrypt_presentation(data, user, b'', password)
    assert 'wrong' not in str(exc.value)


@pytest.mark.parametrize('password', ['', '/01Hannes Ruescher/01'])
def test_ppt_cryptoapi_none_tries_empty_and_spec_default_password(password):
    from dochan.crypto.ppt import decrypt_presentation
    data, user, plain, _ = encrypted_presentation(password=password)
    decrypted, _ = decrypt_presentation(data, user, b'', None)
    assert decrypted[:len(plain)] == plain


@pytest.mark.parametrize('password', ['', 'wrong'])
def test_ppt_cryptoapi_explicit_password_does_not_fall_back_to_default(password):
    from dochan.crypto.ppt import decrypt_presentation
    data, user, _, _ = encrypted_presentation(password='/01Hannes Ruescher/01')
    with pytest.raises(ValueError, match='암호화된 문서'):
        decrypt_presentation(data, user, b'', password)


def test_ppt_cryptoapi_rejects_cyclic_edit_chain():
    from dochan.crypto.ppt import decrypt_presentation
    data, user, _, _ = encrypted_presentation()
    mutable = bytearray(data)
    edit = struct.unpack_from('<I', user, 16)[0]
    struct.pack_into('<I', mutable, edit + 16, edit)
    with pytest.raises(ValueError):
        decrypt_presentation(bytes(mutable), user, b'', 'open')


def test_ppt_cryptoapi_plain_stream_is_unchanged():
    from dochan.crypto.ppt import decrypt_presentation
    assert decrypt_presentation(b'plain', b'', b'images', None) == (b'plain', b'images')


def test_ppt_cryptoapi_picture_fields_reset_rc4():
    from dochan.crypto.ppt import decrypt_presentation
    data, user, _, crypt = encrypted_presentation()
    uid = b'abcdefghijklmnop'
    pixels = b'\x89PNG\r\n\x1a\nimage bytes'
    header = struct.pack('<HHI', 0x6E00, 0xF01E, 17 + len(pixels))
    fields = [header, uid, b'\xff', pixels]
    encrypted = b''.join(crypt(field, 0) for field in fields)
    _, pictures = decrypt_presentation(data, user, encrypted, 'open')
    assert pictures == b''.join(fields)


@pytest.mark.parametrize('instance,uid_count', [
    (0x46A, 1), (0x46B, 2), (0x6E2, 1), (0x6E3, 2),
])
def test_ppt_cryptoapi_jpeg_rgb_and_cmyk_uid_fields(instance, uid_count):
    from dochan.crypto.ppt import decrypt_presentation
    from dochan.office_binary.officeart import decode_blip, parse_records
    data, user, _, crypt = encrypted_presentation()
    pixels = b'\xff\xd8synthetic JPEG payload\xff\xd9'
    fields = [struct.pack('<HHI', instance << 4, 0xF01D,
                          uid_count * 16 + 1 + len(pixels))]
    fields.extend(bytes([index]) * 16 for index in range(uid_count))
    fields.extend([b'\xff', pixels])
    encrypted = b''.join(crypt(field, 0) for field in fields)
    _, pictures = decrypt_presentation(data, user, encrypted, 'open')
    assert pictures == b''.join(fields)
    assert decode_blip(parse_records(pictures)[0]) == ('jpg', pixels)


def test_ppt_cryptoapi_rejects_oversized_object():
    from dochan.crypto.ppt import decrypt_presentation
    data, user, _, crypt = encrypted_presentation()
    data = crypt(struct.pack('<HHI', 15, 1000, 0xFFFFFFFF), 1) + data[8:]
    with pytest.raises(ValueError, match='암호화된 문서'):
        decrypt_presentation(data, user, b'', 'open')


def test_ppt_reader_uses_password_and_keeps_it_out_of_errors(monkeypatch, tmp_path):
    import io
    from dochan.office_binary.ppt import PPTReader
    from dochan.output.markdown import to_markdown
    data, user, _, _ = encrypted_presentation()
    streams = {'PowerPoint Document': data, 'Current User': user}

    class FakeOle:
        def __init__(self, _):
            pass

        def exists(self, name):
            return name in streams

        def openstream(self, name):
            return io.BytesIO(streams[name])

        def get_size(self, name):
            return len(streams[name])

        def close(self):
            pass

    monkeypatch.setattr('dochan.office_binary.ppt.olefile.OleFileIO', FakeOle)
    path = tmp_path / 'encrypted.ppt'
    path.write_bytes(b'synthetic')
    assert 'Encrypted slide' in to_markdown(PPTReader(password='open').read(str(path)))
    for password in (None, 'private-wrong-value'):
        doc = PPTReader(password=password).read(str(path))
        assert not doc.sections
        assert doc.errors[0].startswith('ERR: 암호화된 문서')
        assert 'private-wrong-value' not in str(doc.errors)
