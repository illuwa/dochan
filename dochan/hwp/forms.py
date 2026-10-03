"""Visible text of HWP form objects and click-here fields.

HWP 5's FORM_OBJECT payload contains a length-delimited UTF-16 parameter
string. The envelope and typed names below were checked against public
form-01/form-02 and their HWPX pairs; values are never found by substring
search, since a user value can itself contain parameter-looking text.
"""
import re
import struct


MAX_PARAMETER_UNITS = 65_535
MAX_PARAMETER_ITEMS = 4096
MAX_PARAMETER_DEPTH = 16
_IDENTIFIER = re.compile(r'[A-Za-z][A-Za-z0-9_]*\Z')
_FORM_FIELDS = {
    b'tbp+': ('ButtonSet', 'Caption'),
    b'tbc+': ('ButtonSet', 'Caption'),
    b'tbr+': ('ButtonSet', 'Caption'),
    b'boc+': ('ComboBoxSet', 'Text'),
    b'tde+': ('EditSet', 'Text'),
}


def parse_parameter_text(text):
    """Parse bounded name:type:value entries, including nested set values.

    Lengths count UTF-16 code units. Convert to a one-character-per-code-unit
    string for slicing, then decode user strings back to Unicode scalars.
    Duplicate keys and unknown value types fail closed instead of guessing.
    """
    encoded = text.encode('utf-16-le', errors='surrogatepass')
    if len(encoded) // 2 > MAX_PARAMETER_UNITS:
        raise ValueError('HWP form parameter text exceeds size limit')
    units = ''.join(chr(value[0]) for value in struct.iter_unpack('<H', encoded))
    item_count = [0]

    def decode(value):
        raw = b''.join(struct.pack('<H', ord(c)) for c in value)
        return raw.decode('utf-16-le', errors='replace')

    def parse(value, depth):
        if depth > MAX_PARAMETER_DEPTH:
            raise ValueError('HWP form parameter depth exceeds limit')
        result = {}
        pos = 0
        while pos < len(value):
            while pos < len(value) and value[pos] == ' ':
                pos += 1
            if pos == len(value):
                break
            first = value.find(':', pos)
            second = value.find(':', first + 1) if first >= 0 else -1
            if first < 0 or second < 0:
                raise ValueError('truncated HWP form parameter header')
            name, kind = value[pos:first], value[first + 1:second]
            if not _IDENTIFIER.fullmatch(name) or name in result:
                raise ValueError('invalid or duplicate HWP form parameter name')
            item_count[0] += 1
            if item_count[0] > MAX_PARAMETER_ITEMS:
                raise ValueError('HWP form parameter count exceeds limit')
            pos = second + 1
            if kind in ('wstring', 'set'):
                colon = value.find(':', pos)
                length_text = value[pos:colon] if colon >= 0 else ''
                if not length_text.isdigit() or len(length_text) > 5:
                    raise ValueError('invalid HWP form parameter length')
                length = int(length_text)
                start, end = colon + 1, colon + 1 + length
                if end > len(value):
                    raise ValueError('truncated HWP form parameter value')
                chunk = value[start:end]
                result[name] = parse(chunk, depth + 1) if kind == 'set' else decode(chunk)
                pos = end
            elif kind in ('int', 'bool'):
                end = value.find(' ', pos)
                if end < 0:
                    end = len(value)
                raw = value[pos:end]
                if not re.fullmatch(r'-?[0-9]{1,11}', raw):
                    raise ValueError('invalid HWP form numeric parameter')
                result[name] = int(raw)
                pos = end
            else:
                raise ValueError('unsupported HWP form parameter type')
            if pos < len(value) and value[pos] != ' ':
                raise ValueError('missing HWP form parameter separator')
        return result

    return parse(units, 0)


_MNEMONIC = re.compile(r'&(&?)')


def caption_display(caption):
    """Show a button/check/radio caption as Hancom Office does.

    Captions use the Windows mnemonic convention, confirmed on screen with
    Hancom Office HWP: '&&' shows one '&'; a lone '&' marks the access key
    and is hidden, including a trailing one. Edit/combo text is literal.
    """
    return _MNEMONIC.sub(lambda match: match.group(1), caption)


def form_text(data):
    """Return the stored caption/current text of the five supported forms."""
    if len(data) < 14:
        raise ValueError('truncated HWP form object')
    kind = data[:4]
    if kind not in _FORM_FIELDS:
        raise ValueError('unsupported HWP form object type')
    if data[4:8] != kind:
        raise ValueError('inconsistent HWP form object type')
    count = struct.unpack_from('<I', data, 8)[0]
    short_count = struct.unpack_from('<H', data, 12)[0]
    if count > MAX_PARAMETER_UNITS or short_count != count:
        raise ValueError('invalid HWP form object text length')
    end = 14 + count * 2
    if end > len(data):
        raise ValueError('truncated HWP form object text')
    params = parse_parameter_text(data[14:end].decode('utf-16-le', errors='replace'))
    group, key = _FORM_FIELDS[kind]
    values = params.get(group, {})
    if not isinstance(values, dict):
        raise ValueError('invalid HWP form object parameter group')
    # Password edit controls do not expose their private contents in output.
    if kind == b'tde+' and values.get('PasswordChar'):
        return ''
    value = values.get(key, '')
    value = value if isinstance(value, str) else ''
    if group == 'ButtonSet':
        value = caption_display(value)
    if kind in (b'tbc+', b'tbr+'):
        marker = '[x]' if values.get('Value') == 1 else '[ ]'
        return marker + value
    return value


def clickhere_prompt(data):
    """Inspect click-here Direction metadata; it is not stored body text."""
    if len(data) < 11 or data[:4] != b'klc%':
        return ''
    count = struct.unpack_from('<H', data, 9)[0]
    end = 11 + count * 2
    if end > len(data):
        raise ValueError('truncated HWP click-here command')
    params = parse_parameter_text(data[11:end].decode('utf-16-le', errors='replace'))
    clickhere = params.get('Clickhere', {})
    if not isinstance(clickhere, dict):
        return ''
    value = clickhere.get('Direction', '')
    return value if isinstance(value, str) else ''
