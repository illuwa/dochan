import json
import subprocess
import sys
import zipfile


def test_mcp_stdio_document_roundtrip(tmp_path):
    path = tmp_path / 'sample.docx'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        archive.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>안녕하세요</w:t></w:r></w:p></w:body></w:document>')
    messages = [
        {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-06-18', 'capabilities': {}, 'clientInfo': {'name': 'test', 'version': '1'}}},
        {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
        {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
        {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': 'convert_document', 'arguments': {'path': str(path)}}},
        {'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call', 'params': {'name': 'convert_document', 'arguments': {'path': str(tmp_path / 'missing.pdf')}}},
        {'jsonrpc': '2.0', 'id': 5, 'method': 'tools/call', 'params': {'name': 'convert_document', 'arguments': {'path': str(path), 'format': 'json'}}},
    ]
    result = subprocess.run([sys.executable, '-m', 'dochan.cli', 'mcp'], input=''.join(json.dumps(m) + '\n' for m in messages), text=True, capture_output=True, check=True)  # nosemgrep: dangerous-subprocess-use-audit
    replies = [json.loads(line) for line in result.stdout.splitlines()]
    assert [r['id'] for r in replies] == [1, 2, 3, 4, 5]
    assert replies[0]['result']['protocolVersion'] == '2025-06-18'
    assert replies[1]['result']['tools'][0]['name'] == 'convert_document'
    assert '안녕하세요' in replies[2]['result']['content'][0]['text']
    assert replies[3]['result']['isError'] is True
    assert '안녕하세요' in json.dumps(json.loads(replies[4]['result']['content'][0]['text']), ensure_ascii=False)


def test_mcp_rejects_invalid_arguments_and_unknown_method():
    messages = [
        {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'convert_document', 'arguments': {'path': 123}}},
        {'jsonrpc': '2.0', 'id': 2, 'method': 'unknown'},
    ]
    result = subprocess.run([sys.executable, '-m', 'dochan.cli', 'mcp'], input=''.join(json.dumps(m) + '\n' for m in messages), text=True, capture_output=True, check=True)  # nosemgrep: dangerous-subprocess-use-audit
    replies = [json.loads(line) for line in result.stdout.splitlines()]
    assert replies[0]['result']['isError'] is True
    assert replies[1]['error']['code'] == -32601
