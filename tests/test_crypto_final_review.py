"""Deterministic crypto budgets and public password/IRM diagnostics."""
import time

import pytest

from dochan import Dochan
from dochan.crypto import ooxml
from dochan.model.document import Document
from test_ooxml_crypt import _agile


def test_crypto_budget_does_not_depend_on_elapsed_wall_time(monkeypatch):
    streams, expected = _agile()
    ticks = iter(range(0, 10 ** 12, 100000))
    monkeypatch.setattr(time, 'monotonic', lambda: next(ticks))
    assert ooxml.decrypt_ooxml(streams, 'secret') == expected


def test_high_spin_missing_password_reports_password_requirement():
    streams, _ = _agile()
    streams.streams['EncryptionInfo'] = streams.streams['EncryptionInfo'].replace(
        b'spinCount="3"', b'spinCount="1000000"')
    with pytest.raises(ooxml.OOXMLCryptoError, match='암호가 필요'):
        ooxml.decrypt_ooxml(streams)


def test_hash_budget_still_rejects_before_hashing(monkeypatch):
    budget = ooxml._WorkBudget()
    budget.hashes = 2
    monkeypatch.setattr(ooxml, '_hash', lambda *_: pytest.fail('hash budget must be reserved first'))
    with pytest.raises(ooxml.OOXMLCryptoError, match='반복 작업량 상한'):
        ooxml._password_hash('secret', bytes(16), 'sha512', 3, budget)


def test_ooxml_plaintext_limit_remains_16_mib():
    import struct

    streams, _ = _agile()
    package = streams.streams['EncryptedPackage']
    streams.streams['EncryptedPackage'] = struct.pack('<Q', 16 * 1024 * 1024 + 1) + package[8:]
    with pytest.raises(ooxml.OOXMLCryptoError, match='복호화 크기 상한'):
        ooxml.decrypt_ooxml(streams, 'secret')


@pytest.mark.parametrize('extension', ['doc', 'xls', 'ppt', 'docx', 'xlsx', 'pptx', 'pdf', 'hwp'])
@pytest.mark.parametrize('password', [b'private-password', bytearray(b'private-password'), 123])
def test_public_password_requires_string_before_reading_file(tmp_path, extension, password):
    with pytest.raises(TypeError, match='password must be str or None') as error:
        Dochan(str(tmp_path / ('missing.' + extension)), password=password)
    assert 'private-password' not in str(error.value)


@pytest.mark.parametrize('stream,protected', [
    ('\tDRMContent', True),
    ('\x06DataSpaces/TransformInfo/\tDRMTransform/\x06Primary', True),
    ('\x06DataSpaces', False),
    ('WordDocument', False),
])
def test_doc_irm_warning_preserves_compatibility_document(monkeypatch, stream, protected):
    import dochan.reader as reader_module

    class Container:
        def __init__(self, path):
            pass

        def exists(self, name):
            return name == stream

        def close(self):
            pass

    expected = Document(source_format='doc')

    class DOCReader:
        def read(self, path):
            return expected

    monkeypatch.setattr(reader_module.olefile, 'OleFileIO', Container)
    monkeypatch.setattr(reader_module, 'DOCReader', DOCReader)
    reader = object.__new__(Dochan)
    reader.file_path = 'synthetic.doc'
    reader._password = None
    reader._parse_doc()
    assert reader.doc is expected
    assert bool(reader.errors) is protected
    if protected:
        assert len(reader.errors) == 1
        assert reader.errors[0].startswith('WARN:')
        assert 'DRM/IRM' in reader.errors[0]


def test_irm_detection_keeps_container_size_limit(monkeypatch):
    from dochan.crypto.legacy import warn_irm_protection
    from dochan.utils.bounded_io import MAX_OLE_DOCUMENT_SIZE

    monkeypatch.setattr('os.path.getsize', lambda _: MAX_OLE_DOCUMENT_SIZE + 1)
    monkeypatch.setattr('olefile.OleFileIO', lambda _: pytest.fail('oversized container opened'))
    errors = []
    warn_irm_protection('synthetic.doc', errors)
    assert errors == []
