"""PDF 구조 전제조건 프로브는 본문 번호를 각주로 세지 않는다."""
from dochan.pdf.content import Fragment
from scripts.probe_pdf_structure import footnote_candidates


def frag(text, x, y, size=12, order=0):
    return Fragment(x, y, len(text) * size / 2, size, text, size / 3, order=order)


def sample():
    return [frag("Body", 40, 500, order=0),
            frag("1)", 64, 502.5, size=9, order=1),
            frag("1) Detail", 40, 100, size=10.5, order=2)]


def test_probe_requires_matching_superscript_and_bottom_definition():
    found = footnote_candidates(sample(), (0, 800))
    assert len(found) == 1
    assert found[0]["reference_order"] == 1
    assert found[0]["definition_order"] == 2


def test_probe_rejects_number_on_body_baseline():
    fragments = sample()
    fragments[1].y = 500
    assert footnote_candidates(fragments, (0, 800)) == []


def test_probe_rejects_definition_in_body():
    fragments = sample()
    fragments[2].y = 300
    assert footnote_candidates(fragments, (0, 800)) == []


def test_probe_rejects_unmatched_number():
    fragments = sample()
    fragments[1].text = "2)"
    assert footnote_candidates(fragments, (0, 800)) == []


def test_probe_rejects_ambiguous_duplicate_references():
    fragments = sample()
    fragments.extend([frag("Body", 40, 450, order=3),
                      frag("1)", 64, 452.5, size=9, order=4)])
    assert footnote_candidates(fragments, (0, 800)) == []


def test_probe_rejects_noisy_high_cardinality_page():
    fragments = sample() * 20000
    assert footnote_candidates(fragments, (0, 800)) == []
