"""PDF 각주 후보는 본문 표지·하단 정의·구분선이 모두 일치해야 한다."""
from dochan.pdf.content import Fragment
from dochan.pdf.paths import Segment
from dochan.pdf.notes import detect_notes


def frag(text, x, y, size=12, order=0):
    return Fragment(x, y, len(text) * size / 2, size, text, size / 3, order=order)


def sample():
    return [frag("Body", 40, 500, order=0),
            frag("1)", 64, 502.5, size=9, order=1),
            frag("1) Detail", 40, 100, size=10.5, order=2)]


def detect(fragments=None, segments=None, first_number=1):
    if fragments is None:
        fragments = sample()
    if segments is None:
        segments = [Segment(40, 115, 180, 115)]
    return detect_notes(fragments, segments, (0, 800), 3, first_number)


def test_note_has_existing_model_and_global_reference_number():
    notes, consumed, references, following = detect(first_number=7)
    assert len(notes) == 1 and notes[0].type == "footnote"
    assert notes[0].number == 7 and notes[0].text == "Detail"
    assert consumed == {2} and references == {1: 7} and following == 8
    assert notes[0].paragraphs[0].provenance.page == 3


def test_note_requires_separator_above_definition():
    assert detect(segments=[])[0] == []
    assert detect(segments=[Segment(40, 90, 180, 90)])[0] == []


def test_note_rejects_body_baseline_number_and_unmatched_definition():
    fragments = sample()
    fragments[1].y = 500
    assert detect(fragments)[0] == []
    fragments = sample()
    fragments[1].text = "2)"
    assert detect(fragments)[0] == []


def test_note_rejects_ambiguous_reference_and_body_definition():
    fragments = sample()
    fragments.extend([frag("Body", 40, 450, order=3),
                      frag("1)", 64, 452.5, size=9, order=4)])
    assert detect(fragments)[0] == []
    fragments = sample()
    fragments[2].y = 300
    assert detect(fragments)[0] == []


def test_note_consumes_continuation_once_and_leaves_footer():
    fragments = sample()
    fragments.extend([frag("Continued", 40, 85, size=10.5, order=3),
                      frag("3", 200, 20, size=8, order=4)])
    notes, consumed, references, following = detect(fragments)
    assert notes[0].text == "Detail\nContinued"
    assert consumed == {2, 3} and references == {1: 1}


def test_note_avoids_partial_block_when_another_marker_is_unresolved():
    fragments = sample()
    fragments.append(frag("2) Other", 40, 85, size=10.5, order=3))
    assert detect(fragments)[0] == []


def test_note_limits_noisy_page_without_allocating_candidates():
    assert detect(sample() * 20000)[0] == []


def test_note_reports_resource_limit_and_rejects_nonfinite_geometry():
    warnings = []
    result = detect_notes(sample() * 20000, [], (0, 800), 1, warnings=warnings)
    assert result[0] == [] and "한도" in warnings[0]
    fragments = sample()
    fragments[1].y = float("nan")
    assert detect(fragments)[0] == []


def test_note_preserves_links_inside_definition_runs():
    fragments = sample()
    fragments[2].link_spans = [(3, 9, "https://example.org/detail")]
    notes = detect(fragments)[0]
    assert notes[0].text == "Detail"
    assert notes[0].paragraphs[0].runs[0].link == "https://example.org/detail"


def test_note_geometry_budget_covers_separator_and_consumed_fragments(monkeypatch):
    import dochan.pdf.notes as module
    warnings = []
    monkeypatch.setattr(module, "MAX_NOTE_GEOMETRY_CHECKS", 1)
    result = module.detect_notes(sample(), [Segment(40, 115, 180, 115)],
                                 (0, 800), 1, warnings=warnings)
    assert result[:3] == ([], set(), {}) and "기하 검사" in warnings[0]
    monkeypatch.setattr(module, "MAX_NOTE_GEOMETRY_CHECKS", 5)
    fragments = sample()
    fragments.extend(frag("x", 100 + i * 6, 100, size=10.5, order=10 + i)
                     for i in range(10))
    warnings = []
    result = module.detect_notes(fragments, [Segment(40, 115, 180, 115)],
                                 (0, 800), 1, warnings=warnings)
    assert result[:3] == ([], set(), {}) and "기하 검사" in warnings[0]
