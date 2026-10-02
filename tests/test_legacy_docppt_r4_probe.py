"""Check review metrics against rendered text, not Markdown marker counts."""
import pytest

from scripts.probe_legacy_docppt_r4 import compare_text, rendered, text_digest


@pytest.fixture
def parser():
    return pytest.importorskip('markdown_it').MarkdownIt().enable('table').enable('strikethrough')


@pytest.mark.parametrize('before,after,lost', [
    ('**keep missing**', '**keep**', 1),
    ('<div>keep missing</div>', '<div>keep</div>', 1),
    ('<sup>keep missing</sup>', '<sup>keep</sup>', 1),
    ('**keep**', '*keep*', 0),
    ('![image](image)', '', 0),
])
def test_r4_probe_detects_rendered_body_loss(parser, before, after, lost):
    assert compare_text(before, after, parser)['lost_body_words'] == lost


def test_r4_probe_does_not_net_off_stray_increases(parser):
    old = 'first ** text\n\nunchanged\n\nlast'
    new = 'first text\n\nunchanged\n\nlast ** text'
    assert compare_text(old, new, parser)['stray_increase_hunks'] == 1


def test_r4_probe_tracks_html_and_markdown_images(parser):
    body, alts, targets = rendered('text ![a](image) <img src="other.png" alt="b">', parser)
    assert body.strip() == 'text'
    assert alts == ['a', 'b']
    assert targets == ['image', 'other.png']


def test_r4_probe_identical_plain_output_needs_no_renderer():
    result = compare_text('**same**\n' * 1000, '**same**\n' * 1000, None)
    assert result['lost_body_words'] == result['stray_increase_hunks'] == 0
    assert result['empty_target_refs'] == [0, 0]
    assert result['rendered_stars'] == [None, None]


def test_r4_probe_chunked_digest_preserves_unicode():
    import hashlib
    text = 'a' * (1024 * 1024 - 1) + '가😀ending'
    assert text_digest(text) == hashlib.sha256(text.encode()).hexdigest()
