"""Compile-time instrumentation and glyph allocation contract regressions."""
import importlib
import os

import pytest

from dochan.pdf import content
from dochan.pdf.cmap import ToUnicodeCMap
from dochan.pdf.widths import WidthMap


@pytest.mark.skipif(os.environ.get('DOCHAN_EXPECT_INTERNAL_PROFILE') != '1',
                    reason='requires instrumented build')
@pytest.mark.parametrize('name', ['_cinterp', '_clines', '_cobjects'])
def test_profile_counters_are_monotonic(name):
    module = importlib.import_module('dochan.pdf.' + name)
    before = module._profile()
    content.ContentTextExtractor.from_fonts({}).extract_page(b'1 2 m 3 4 l S')
    after = module._profile()
    assert len(before) == len(after) == 8
    assert all(t >= old_t and n >= old_n
               for (t, n), (old_t, old_n) in zip(after, before))


@pytest.mark.parametrize('text', ['A', 'fi', '', ' ', '\u3000', '\U0001f600'])
def test_single_glyph_fields_and_independent_defaults(text):
    pytest.importorskip('dochan.pdf._cinterp')
    cmap = ToUnicodeCMap()
    cmap.code_lengths = {1}
    cmap.mapping = {(1, 65): text}
    font = content.FontInfo(cmap.decode, WidthMap({65: 500.0}, 600.0))
    owner = content.ContentTextExtractor.from_fonts({'F': font}, track_char_positions=True)
    data = b'/F 12 Tf (A) Tj (A) Tj'
    expected = owner._extract_page_python(data)
    actual = content.ContentTextExtractor.from_fonts({'F': font}, track_char_positions=True).extract_page(data)
    assert [vars(f) for f in actual.fragments] == [vars(f) for f in expected.fragments]
    if len(actual.fragments) == 2:
        for name in ('link_spans', 'comment_spans', 'comment_markers'):
            assert getattr(actual.fragments[0], name) is not getattr(actual.fragments[1], name)
