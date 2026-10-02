"""독립 구문 계수기가 단순 별표 홀짝 검사로 퇴행하지 않도록 한다."""

import pytest
import hashlib

from scripts.probe_markdown_commonmark import measure


@pytest.mark.parametrize('text,unclosed,alts', [
    ('**path\\** \n**next**', 1, 0),
    ('**path\\\\** \n**next**', 0, 0),
    ('# **first\nsecond**', 1, 0),
    ('**first\nsecond**', 0, 0),
    ('`**code` and \\*literal and * text', 0, 0),
    ('![first**\n**second](url)', 0, 1),
    ('**![first\nsecond](url)**', 0, 0),
    ('[**first](url)', 1, 0),
    ('[**first**](url)', 0, 0),
])
def test_commonmark_probe_interprets_delimiters(text, unclosed, alts):
    pytest.importorskip('markdown_it')
    result = measure(text)
    assert result['unclosed_emphasis_lines'] == unclosed
    assert result['image_alts_with_stars'] == alts


@pytest.mark.parametrize('text', [
    '**first\r\nsecond**', '# **first\rsecond**',
    '![first**][pic]\n\n[pic]: image.png',
    '[**label**][link]\n\n[link]: https://example.org',
    '- **bold**\n- *italic*', '```\n**code\n```',
    'text\0end',
])
def test_commonmark_probe_matches_standard_rendering(text):
    parser = pytest.importorskip('markdown_it').MarkdownIt('commonmark')
    expected = hashlib.sha256(parser.render(text).encode()).hexdigest()
    assert measure(text)['html_sha256'] == expected
