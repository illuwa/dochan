"""Fast XML path must preserve the bounded parser's observable contract."""
import pytest

from dochan.utils import safe_xml as xml


def test_plain_elements_do_not_call_python_element_targets(monkeypatch):
    def forbidden(*args):
        raise AssertionError('Python element callback used')
    monkeypatch.setattr(xml._PlainBoundedTree, 'start', forbidden)
    monkeypatch.setattr(xml._PlainBoundedTree, 'end', forbidden)
    root = xml.fromstring(b'<r xmlns:q="urn:q"><q:a x="1">text</q:a><b/></r>')
    assert root[0].text == 'text'
    assert xml.namespace_uris(root) == frozenset({'urn:q'})


def outcome(source, **kwargs):
    try:
        root = xml.fromstring(source, **kwargs)
        return xml.tostring(root), xml.namespace_uris(root)
    except Exception as exc:
        return type(exc), str(exc)


@pytest.mark.parametrize('source', [
    b'<r>' * 100_000 + b'</r>' * 100_000,
    b'<r>' + b'<a/>' * 2_000_000 + b'</r>',
    b'<r><a value="' + b'x' * (2 * 1024 * 1024) + b'"/></r>',
    b'<!DOCTYPE r [<!ENTITY x "boom">]><r>&x;</r>',
    b'<!DOCTYPE r SYSTEM "https://example.invalid/x"><r/>',
    '<!DOCTYPE r><r/>'.encode('utf-16'),
    b'<r><a>ok</a><bad',
    b'<r><a>ok</a></bad>',
    b'<r xmlns:a="urn:a" xmlns:b="urn:b"/>',
    b'<r xmlns:a="urn:&#125;x"><a:b/></r>',
    b'<r a="/>" b=\'"\'><a><b/></a></r>',
    b'<r><!-- </r> --><![CDATA[</r>]]><a/></r>',
    b'<r><?pi </r>?><a/></r>',
    b'<r xmlns="urn:r"><a xmlns=""/></r>',
])
@pytest.mark.parametrize('options', [{}, {'recover': True}, {'truncate': True, 'max_depth': 2},
                                    {'max_namespaces': 1}])
def test_fast_and_legacy_outcomes_match(source, options, monkeypatch):
    actual = outcome(source, **options)
    monkeypatch.setattr(xml, '_fast_structure', lambda *args: False)
    assert actual == outcome(source, **options)


@pytest.mark.parametrize('native', [False, True])
def test_random_mutations_match_legacy(native, monkeypatch):
    import random
    if native and xml._c_structure is None:
        pytest.skip('optional C scanner is not built')
    if not native:
        monkeypatch.setattr(xml, '_c_structure', None)
    rng = random.Random(310)
    fast = xml._fast_structure
    base = b'<r xmlns:q="urn:q"><q:a x="/&gt;">text</q:a><b/><c><d/></c></r>'
    for _ in range(1000):
        start = rng.randrange(len(base))
        end = min(len(base), start + rng.randrange(8))
        source = base[:start] + rng.choice([b'', b'<', b'>', b'/', b'"', b"'", b'&', b'\0', b'<!--', b'<?']) + base[end:]
        options = {'max_depth': rng.choice([1, 2, 3, 256]),
                   'max_namespaces': rng.choice([0, 1, 100]),
                   'recover': rng.choice([False, True]), 'truncate': rng.choice([False, True])}
        monkeypatch.setattr(xml, '_fast_structure', fast)
        actual = outcome(source, **options)
        monkeypatch.setattr(xml, '_fast_structure', lambda *args: False)
        assert actual == outcome(source, **options), (source, options)


@pytest.mark.parametrize('source', [
    b'<r><!-- comment --></r>', b'<r><?pi value?></r>',
    b'<r><![CDATA[</r>]]><a/></r>',
    b'<r xmlns:mc="urn:mc"><mc:Choice Requires="x"/></r>',
    '<r><a/></r>'.encode('utf-16'),
])
def test_uncertain_inputs_keep_original_target(source, monkeypatch):
    monkeypatch.setattr(xml, '_c_structure', None)
    assert not xml._fast_structure(source, 256)


def test_truncation_comment_boundary_matches_legacy(monkeypatch):
    source = b'<r><!--comment--><?pi data?></r>'
    actual = outcome(source, max_depth=1, truncate=True)
    monkeypatch.setattr(xml, '_fast_structure', lambda *args: False)
    assert actual == outcome(source, max_depth=1, truncate=True)


def test_native_preflight_boundary_and_quoted_delimiters():
    if xml._c_structure is None:
        pytest.skip('optional C scanner is not built')
    source = b'<r a="/>" b=\'>\'><a><b/></a></r>'
    assert not xml._c_structure(source, 2, xml.MAX_ELEMENTS)
    assert xml._c_structure(source, 3, xml.MAX_ELEMENTS)
    assert not xml._c_structure(b'<r>' + b'<a/>' * 1_000_000 + b'</r>', 256, xml.MAX_ELEMENTS)
    assert not xml._c_structure(b'<r>' * 100_000 + b'</r>' * 100_000, 256, xml.MAX_ELEMENTS)


def _expat_counts(source):
    """Observe callbacks before the first syntax error, without building a tree."""
    from xml.parsers import expat  # nosemgrep: use-defused-xml -- tree-less element counter over synthetic inputs (independent oracle)
    parser = expat.ParserCreate(namespace_separator='}')  # nosemgrep: use-defused-xml -- synthetic test inputs only
    depth = peak = starts = 0

    def start(name, attrs):
        nonlocal depth, peak, starts
        depth += 1
        peak = max(peak, depth)
        starts += 1

    def end(name):
        nonlocal depth
        depth -= 1

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    try:
        parser.Parse(source, True)
    except expat.ExpatError:
        pass
    return peak, starts


def test_native_independent_allocation_oracle():
    import random
    if xml._c_structure is None:
        pytest.skip('optional C scanner is not built')
    rng = random.Random(310)
    base = b'<r xmlns:q="urn:q"><q:a x="/&gt;">text</q:a><b/><c><d/></c></r>'
    cases = []
    for _ in range(1000):
        start = rng.randrange(len(base))
        end = min(len(base), start + rng.randrange(8))
        source = base[:start] + rng.choice([b'', b'<', b'>', b'/', b'"', b"'", b'&', b'\0', b'<!--', b'<?']) + base[end:]
        limit = rng.choice([1, 2, 3, 256])
        # Keep the same random stream as the existing outcome mutations.
        rng.choice([0, 1, 100])
        rng.choice([False, True])
        rng.choice([False, True])
        cases.append((source, limit))
    for limit in (2, 8, 256):
        for depth in (limit - 1, limit, limit + 1):
            body = b'<a><b/>' * (depth - 1) + b'<a/>' + b'</a>' * (depth - 1)
            for declaration in (b'', b'<?xml version="1.0"?>',
                                b'<?xml version="1.0" encoding="latin-1"?>',
                                b'<?xml version="1.0" encoding="utf-16"?>',
                                b'<?xml\tversion="1.0"?>', b'\xef\xbb\xbf'):
                cases.append((declaration + body, limit))
            cases.append((body[:-4] + b'</z>', limit))
    cases.extend((source, 256) for source in (
        '<뿌리><잎/></뿌리>'.encode(),
        b'<?xml version="1.0" encoding="latin-1"?><r>\xe9<a/></r>',
        b'<?xml version="1.0" encoding="utf-16"?><r>\xe9<a/></r>',
        b'<r xmlns="urn:}x"><a/></r>',
        b'<r><a/></r>garbage',
        '<r><a/></r>'.encode('utf-16'),
        b'<r>' + b'<a/>' * 999_999 + b'</r>',
        b'<r>' + b'<a/>' * 1_000_000 + b'</r>',
    ))
    accepted = 0
    for source, limit in cases:
        if xml._c_structure(source, limit, 1_000_000):
            peak, starts = _expat_counts(source)
            assert peak <= limit, (source[:100], limit, peak)
            assert starts <= 1_000_000
            accepted += 1
    assert accepted > 100


@pytest.mark.parametrize('source', [
    b'<r><!--comment--></r>', b'<r><?pi data?></r>',
    b'<r><![CDATA[<a>]]></r>', b'<!DOCTYPE r><r/>', b'<r><!bad></r>',
])
def test_native_directly_rejects_special_markup(source):
    if xml._c_structure is None:
        pytest.skip('optional C scanner is not built')
    assert not xml._c_structure(source, 256, 1_000_000)


@pytest.mark.parametrize('native', [False, True])
def test_element_limit_is_shared(native, monkeypatch):
    if native and xml._c_structure is None:
        pytest.skip('optional C scanner is not built')
    if not native:
        monkeypatch.setattr(xml, '_c_structure', None)
    monkeypatch.setattr(xml, 'MAX_ELEMENTS', 3)
    assert xml._fast_structure(b'<r><a/><b/></r>', 256) is native
    assert not xml._fast_structure(b'<r><a/><b/><c/></r>', 256)
    assert len(xml.fromstring(b'<r><a/><b/></r>')) == 2
    for namespaces in (False, True):
        with pytest.raises(ValueError, match='XML element limit exceeded'):
            xml.fromstring(b'<r><a/><b/><c/></r>', namespaces=namespaces)
