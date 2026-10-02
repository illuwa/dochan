"""Password routing must preserve parser contracts and never disclose secrets."""
import inspect
import io

import pytest

from dochan import Dochan
from dochan.cli import main
from test_pdf_crypto_password import VECTORS, _build_pdf


def test_password_is_keyword_only():
    parameter = inspect.signature(Dochan).parameters['password']
    assert parameter.kind == inspect.Parameter.KEYWORD_ONLY
    assert parameter.default is None


@pytest.mark.parametrize('vector', VECTORS[:5], ids=lambda v: v['name'])
def test_public_api_pdf_password(tmp_path, vector):
    path = tmp_path / 'encrypted.pdf'
    path.write_bytes(_build_pdf(vector))
    reader = Dochan(str(path), password=vector['password'])
    assert 'Protected text' in reader.to_plain_text()
    assert not reader.errors


@pytest.mark.parametrize('password', [None, 'secret-wrong-password'])
def test_public_api_pdf_wrong_password_is_fatal(tmp_path, password):
    path = tmp_path / 'encrypted.pdf'
    path.write_bytes(_build_pdf(VECTORS[0]))
    reader = Dochan(str(path), password=password)
    assert any(e.startswith('ERR: 암호화된 문서') for e in reader.errors)
    assert not reader.to_plain_text()
    assert 'secret-wrong-password' not in repr(reader.errors)


@pytest.mark.parametrize('command', ['convert', 'info'])
@pytest.mark.parametrize('source', ['stdin', 'environment'])
def test_cli_password_sources(tmp_path, monkeypatch, capsys, command, source):
    path = tmp_path / 'encrypted.pdf'
    path.write_bytes(_build_pdf(VECTORS[0]))
    argv = [command, str(path)]
    if source == 'stdin':
        monkeypatch.setenv('DOCHAN_PASSWORD', 'incorrect-env')
        monkeypatch.setattr('sys.stdin', io.StringIO('user\r\nunused-second-line\n'))
        argv.append('--password-stdin')
    else:
        monkeypatch.setenv('DOCHAN_PASSWORD', 'user')
    assert main(argv) == 0
    out = capsys.readouterr()
    assert 'incorrect-env' not in out.out + out.err
    if command == 'convert':
        assert 'Protected text' in out.out


def test_cli_wrong_password_does_not_publish_output(tmp_path, monkeypatch, capsys):
    path = tmp_path / 'encrypted.pdf'
    output = tmp_path / 'result.md'
    path.write_bytes(_build_pdf(VECTORS[0]))
    monkeypatch.setenv('DOCHAN_PASSWORD', 'secret-wrong-password')
    assert main(['convert', str(path), '-o', str(output)]) == 1
    assert not output.exists()
    captured = capsys.readouterr()
    assert 'secret-wrong-password' not in captured.out + captured.err
    assert '암호화된 문서' in captured.err


def test_cli_batch_help_explains_password_limitation(capsys):
    with pytest.raises(SystemExit) as exc:
        main(['batch', '--help'])
    assert exc.value.code == 0
    assert '암호' in capsys.readouterr().out


def test_cli_password_line_keeps_spaces(tmp_path, monkeypatch, capsys):
    path = tmp_path / 'unused.pdf'
    path.write_bytes(b'')
    received = []
    class Reader:
        def __init__(self, file_path, **kwargs):
            received.append(kwargs['password'])
            self.errors = []
            self.metadata = {}
    monkeypatch.setattr('dochan.reader.Dochan', Reader)
    monkeypatch.setattr('sys.stdin', io.StringIO('  spaced password  \nignored\n'))
    assert main(['info', str(path), '--password-stdin']) == 0
    assert received == ['  spaced password  ']


@pytest.mark.parametrize('option', ['--password', '--pass', '--password-stdin'])
def test_cli_rejects_inline_password_without_echo(tmp_path, capsys, option):
    with pytest.raises(SystemExit) as exc:
        main(['info', str(tmp_path / 'file.pdf'), option, 'do-not-echo-this'])
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert 'do-not-echo-this' not in captured.out + captured.err


@pytest.mark.parametrize('line', ['', 'x' * 4097 + '\n'])
def test_cli_password_input_failure_is_bounded(tmp_path, monkeypatch, capsys, line):
    path = tmp_path / 'encrypted.pdf'
    path.write_bytes(_build_pdf(VECTORS[0]))
    monkeypatch.setattr('sys.stdin', io.StringIO(line))
    assert main(['info', str(path), '--password-stdin']) == 1
    assert '암호' in capsys.readouterr().err


@pytest.mark.parametrize('password', [None, 'known-password'])
def test_hwp_password_is_explicitly_unsupported(tmp_path, monkeypatch, password):
    import struct
    from test_reader_magic_byte_fallback import FakeHwpOle, _file_header_bytes

    class EncryptedHwp(FakeHwpOle):
        def openstream(self, name):
            if name == 'FileHeader':
                header = bytearray(_file_header_bytes())
                struct.pack_into('<I', header, 36, 2)
                return io.BytesIO(header)
            raise AssertionError('Encrypted body must not be parsed')

    path = tmp_path / 'protected.hwp'
    path.write_bytes(b'\xd0\xcf\x11\xe0synthetic')
    monkeypatch.setattr('dochan.reader.olefile.OleFileIO', EncryptedHwp)
    reader = Dochan(str(path), password=password)
    assert any(e.startswith('ERR: 암호화/DRM') for e in reader.errors)
    assert reader.to_plain_text() == ''
    assert 'known-password' not in repr(reader.errors)


def _plain_office_package(kind):
    import zipfile
    ns = 'http://schemas.openxmlformats.org/'
    rel = ns + 'officeDocument/2006/relationships'
    parts = {}
    if kind == 'docx':
        parts['word/document.xml'] = ('<w:document xmlns:w="' + ns +
            'wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Protected Office text'
            '</w:t></w:r></w:p></w:body></w:document>')
    elif kind == 'pptx':
        parts['ppt/presentation.xml'] = ('<p:presentation xmlns:p="' + ns +
            'presentationml/2006/main" xmlns:r="' + rel + '"><p:sldIdLst>'
            '<p:sldId id="256" r:id="rId1"/></p:sldIdLst></p:presentation>')
        parts['ppt/_rels/presentation.xml.rels'] = ('<Relationships xmlns="' + ns +
            'package/2006/relationships"><Relationship Id="rId1" Target="slides/slide1.xml"/></Relationships>')
        parts['ppt/slides/slide1.xml'] = ('<p:sld xmlns:p="' + ns +
            'presentationml/2006/main" xmlns:a="' + ns + 'drawingml/2006/main">'
            '<p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>Protected Office text'
            '</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>')
    else:
        parts['xl/workbook.xml'] = ('<workbook xmlns="' + ns +
            'spreadsheetml/2006/main" xmlns:r="' + rel + '"><sheets>'
            '<sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>')
        parts['xl/_rels/workbook.xml.rels'] = ('<Relationships xmlns="' + ns +
            'package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        parts['xl/worksheets/sheet1.xml'] = ('<worksheet xmlns="' + ns +
            'spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr">'
            '<is><t>Protected Office text</t></is></c></row></sheetData></worksheet>')
    target = io.BytesIO()
    with zipfile.ZipFile(target, 'w') as archive:
        for name, value in parts.items():
            archive.writestr(name, value)
    return target.getvalue()


@pytest.mark.parametrize('kind', ['docx', 'pptx', 'xlsx'])
@pytest.mark.parametrize('mode', ['standard', 'agile'])
def test_encrypted_ooxml_dispatch_is_in_memory(tmp_path, monkeypatch, kind, mode):
    import test_ooxml_crypt as fixtures
    monkeypatch.setattr(fixtures, '_zip', lambda: _plain_office_package(kind))
    streams, payload = getattr(fixtures, '_' + mode)()
    # Office can include a compatibility WordDocument stream alongside the
    # encrypted package (observed in public bug53475-password-is-solrcell.docx).
    streams.streams['WordDocument'] = b'compatibility notice'
    class Container:
        def __init__(self, path):
            pass
        def exists(self, name):
            return name in streams.streams
        def get_size(self, name):
            return streams.get_size(name)
        def openstream(self, name):
            return streams.openstream(name)
        def close(self):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
    encrypted = tmp_path / 'misleading.hwp'
    encrypted.write_bytes(b'\xd0\xcf\x11\xe0synthetic')
    plain = tmp_path / ('plain.' + kind)
    plain.write_bytes(payload)
    expected = Dochan(str(plain))
    monkeypatch.setattr('dochan.reader.olefile.OleFileIO', Container)
    actual = Dochan(str(encrypted), password='secret')
    assert actual.doc.source_format == kind
    assert 'Protected Office text' in actual.to_plain_text()
    assert actual.to_dict() == expected.to_dict()
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(['misleading.hwp', 'plain.' + kind])
