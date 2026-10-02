"""Synthetic regression cases for independent crypto review findings."""
import argparse
import io
import struct
import time
import zipfile

import pytest

from dochan.cli import main, _password_options
from dochan.crypto import ooxml
from dochan.reader import Dochan
from dochan.model.document import Document
from test_ooxml_crypt import _standard, _agile


@pytest.mark.parametrize('flag', ['--password', '-p', '--pass', '--password=PRIVATE_SENTINEL', '-pPRIVATE_SENTINEL'])
@pytest.mark.parametrize('position', ['before', 'after'])
def test_cli_review_masks_password_in_all_positions(flag, position, capsys):
    option = [flag] if '=' in flag or flag == '-pPRIVATE_SENTINEL' else [flag, 'PRIVATE_SENTINEL']
    argv = option + ['info', 'f.pdf'] if position == 'before' else ['info', 'f.pdf'] + option
    with pytest.raises(SystemExit):
        main(argv)
    captured = capsys.readouterr()
    assert 'PRIVATE_SENTINEL' not in captured.err + captured.out


def test_cli_typo_retains_option_diagnostic(capsys):
    with pytest.raises(SystemExit):
        main(['convert', 'f.pdf', '--formt', 'json'])
    error = capsys.readouterr().err
    assert '--formt' in error
    assert '암호는' not in error


def test_cli_empty_environment_is_unset(monkeypatch):
    monkeypatch.setenv('DOCHAN_PASSWORD', '')
    assert _password_options(argparse.Namespace(password_stdin=False)) == {}


def test_cli_password_tty_uses_hidden_input(monkeypatch):
    class Terminal(io.StringIO):
        def isatty(self):
            return True
        def readline(self, *args):
            pytest.fail('TTY must not echo password through readline')
    monkeypatch.setattr('sys.stdin', Terminal())
    monkeypatch.setattr('getpass.getpass', lambda prompt: '  hidden  ')
    assert _password_options(argparse.Namespace(password_stdin=True)) == {'password': '  hidden  '}


def test_standard_version_2_2():
    streams, expected = _standard()
    info = streams.streams['EncryptionInfo']
    streams.streams['EncryptionInfo'] = struct.pack('<HH', 2, 2) + info[4:]
    assert ooxml.decrypt_ooxml(streams, 'secret') == expected


def test_ooxml_budget_rejects_large_stream_before_read():
    streams, _ = _agile()
    original = streams.get_size
    streams.get_size = lambda name: 33 * 1024 * 1024 if name == 'EncryptedPackage' else original(name)
    original_open = streams.openstream
    def openstream(name):
        if name == 'EncryptedPackage':
            pytest.fail('oversized package must be rejected before allocation/decryption')
        return original_open(name)
    streams.openstream = openstream
    with pytest.raises(ValueError, match='상한'):
        ooxml.decrypt_ooxml(streams, 'secret')


def test_ooxml_candidate_budget(monkeypatch):
    streams, _ = _standard()
    calls = []
    def mismatch(*args):
        calls.append(args[-1])
        raise ooxml._PasswordMismatch()
    monkeypatch.setattr(ooxml, '_standard', mismatch)
    monkeypatch.setattr(ooxml, 'MAX_PASSWORD_CANDIDATES', 1, raising=False)
    with pytest.raises(ValueError, match='후보.*상한'):
        ooxml.decrypt_ooxml(streams)
    assert len(calls) <= 1


def _read_encrypted(monkeypatch, streams, password='secret'):
    class Container:
        def __init__(self, path):
            pass
        def __enter__(self):
            return streams
        def __exit__(self, *args):
            pass
    monkeypatch.setattr('dochan.reader.cfb.OleFileIO', Container)
    reader = object.__new__(Dochan)
    reader.file_path = 'synthetic.docx'
    reader._password = password
    reader.doc = Document()
    reader._parse_encrypted_ooxml()
    return reader


def test_api_preserves_safe_crypto_integrity_diagnostic(monkeypatch):
    streams, _ = _agile()
    package = bytearray(streams.streams['EncryptedPackage'])
    package[-17] ^= 1
    streams.streams['EncryptedPackage'] = bytes(package)
    reader = _read_encrypted(monkeypatch, streams)
    assert any('HMAC' in error for error in reader.errors)
    assert 'secret' not in repr(reader.errors)


def test_api_reports_unsupported_xlsb(monkeypatch):
    import test_ooxml_crypt as fixtures
    target = io.BytesIO()
    with zipfile.ZipFile(target, 'w') as archive:
        archive.writestr('xl/workbook.bin', b'synthetic')
    monkeypatch.setattr(fixtures, '_zip', target.getvalue)
    streams, _ = fixtures._standard()
    reader = _read_encrypted(monkeypatch, streams)
    assert any('XLSB' in error and '미지원' in error for error in reader.errors)


def test_ooxml_kdf_is_independent_of_wall_clock(monkeypatch):
    streams, expected = _agile()
    monkeypatch.setattr(time, 'monotonic', lambda: pytest.fail('crypto must use deterministic budgets'))
    assert ooxml.decrypt_ooxml(streams, 'secret') == expected


def test_ooxml_hash_budget_covers_both_candidates(monkeypatch):
    streams, _ = _standard()
    monkeypatch.setattr(ooxml, 'MAX_SPIN_COUNT', 75000)
    with pytest.raises(ValueError, match='암호가 필요'):
        ooxml.decrypt_ooxml(streams)


def test_ooxml_aes_is_independent_of_wall_clock(monkeypatch):
    expected = ooxml._aes(bytes(16), bytes(8192))
    monkeypatch.setattr(time, 'monotonic', lambda: pytest.fail('crypto must use deterministic budgets'))
    budget = ooxml._WorkBudget()
    assert ooxml._aes(bytes(16), bytes(8192), budget=budget) == expected


def test_ooxml_aes_work_budget_is_checked_before_blocks():
    budget = ooxml._WorkBudget()
    budget.bytes = 16
    with pytest.raises(ValueError, match='AES 작업량 상한'):
        ooxml._aes(bytes(16), bytes(32), budget=budget)


@pytest.mark.parametrize('factory', [_standard, _agile])
def test_ooxml_package_decryption_keeps_source_views(monkeypatch, factory):
    streams, expected = factory()
    original = ooxml._aes
    observed = []
    def aes(key, data, iv=None, **kwargs):
        if kwargs.get('output') is not None:
            observed.append(isinstance(data, memoryview))
        return original(key, data, iv, **kwargs)
    monkeypatch.setattr(ooxml, '_aes', aes)
    assert ooxml.decrypt_ooxml(streams, 'secret') == expected
    assert observed and all(observed)


def test_cli_attached_short_password_never_echoes(capsys):
    with pytest.raises(SystemExit):
        main(['info', 'f.pdf', '-pALPHASECRET'])
    captured = capsys.readouterr()
    assert 'ALPHASECRET' not in captured.err + captured.out
