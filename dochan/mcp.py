"""MCP stdio server, implemented against the public protocol specification."""
import json
import os
import sys

from . import __version__
from .batch import _is_fatal_parser_error
from .reader import Dochan

_VERSION = '2025-06-18'
_SUPPORTED = {_VERSION, '2024-11-05', '2025-03-26'}
_TOOL = {
    'name': 'convert_document',
    'description': 'Read a local document and return its contents. Supports HWP, HWPX, Office and PDF.',
    'inputSchema': {
        'type': 'object',
        'properties': {
            'path': {'type': 'string', 'description': 'Absolute local document path'},
            'format': {'type': 'string', 'enum': ['markdown', 'text', 'json'], 'default': 'markdown'},
            'ocr': {'type': 'boolean', 'default': False},
            'pdf_text_tables': {'type': 'boolean', 'default': False},
            'revision_mode': {'type': 'string', 'enum': ['preserve', 'final', 'original'], 'default': 'preserve'},
        },
        'required': ['path'], 'additionalProperties': False,
    },
    'annotations': {'readOnlyHint': True, 'destructiveHint': False, 'openWorldHint': False},
}


def _result(text, error=False):
    result = {'content': [{'type': 'text', 'text': text}]}
    if error:
        result['isError'] = True
    return result


def _convert(args):
    if not isinstance(args, dict) or set(args) - {'path', 'format', 'ocr', 'pdf_text_tables', 'revision_mode'}:
        return _result('Invalid arguments.', True)
    path = args.get('path')
    fmt = args.get('format', 'markdown')
    revision = args.get('revision_mode', 'preserve')
    if (not isinstance(path, str) or not os.path.isabs(path) or
            not isinstance(fmt, str) or fmt not in ('markdown', 'text', 'json') or
            not isinstance(revision, str) or revision not in ('preserve', 'final', 'original') or
            any(type(args.get(key, False)) is not bool for key in ('ocr', 'pdf_text_tables'))):
        return _result('Invalid document path or options.', True)
    if not os.path.isfile(path):
        return _result('Document file not found.', True)
    try:
        doc = Dochan(path, ocr=args.get('ocr', False),
                     pdf_text_tables=args.get('pdf_text_tables', False), revision_mode=revision)
        if any(_is_fatal_parser_error(e) for e in doc.errors):
            return _result('\n'.join(doc.errors), True)
        content = {'markdown': doc.to_markdown, 'text': doc.to_plain_text, 'json': doc.to_json}[fmt]()
        result = _result(content)
        if doc.errors:
            result['content'].append({'type': 'text', 'text': 'Warnings: ' + '\n'.join(doc.errors)})
        return result
    except Exception:
        return _result('Document conversion failed; check the file and options.', True)


def _dispatch(method, params):
    if method == 'initialize':
        requested = params.get('protocolVersion')
        return {'protocolVersion': requested if isinstance(requested, str) and requested in _SUPPORTED else _VERSION,
                'capabilities': {'tools': {}}, 'serverInfo': {'name': 'dochan', 'version': __version__}}
    if method == 'ping':
        return {}
    if method == 'tools/list':
        return {'tools': [_TOOL]}
    if method == 'tools/call':
        if params.get('name') != 'convert_document':
            return _result('Unknown tool.', True)
        return _convert(params.get('arguments', {}))
    raise KeyError(method)


def serve():
    for line in sys.stdin:
        try:
            message = json.loads(line)
        except (ValueError, UnicodeError):
            response = {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'Parse error'}}
        else:
            if (not isinstance(message, dict) or message.get('jsonrpc') != '2.0' or
                    not isinstance(message.get('method'), str)):
                response = {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32600, 'message': 'Invalid Request'}}
            elif 'id' not in message:
                continue
            else:
                response = {'jsonrpc': '2.0', 'id': message['id']}
                params = message.get('params', {})
                if not isinstance(params, dict):
                    response['error'] = {'code': -32602, 'message': 'Invalid params'}
                else:
                    try:
                        response['result'] = _dispatch(message['method'], params)
                    except KeyError:
                        response['error'] = {'code': -32601, 'message': 'Method not found'}
        sys.stdout.write(json.dumps(response, ensure_ascii=True) + '\n')
        sys.stdout.flush()
    return 0
