"""공개 보도자료 PDF 표·줄 결합 진단의 합성 검사."""
from scripts.probe_pdf_press_tables import join_outcomes, suspect_different_content


def test_join_outcomes_separates_missing_and_extra_spaces():
    answer = "초록 바다\n긴문장\n다른 단어"
    joins = [("초록", "바다", False), ("긴", "문장", True),
             ("다른", "단어", True), ("없는", "조각", False)]
    result = join_outcomes(answer, joins)
    assert result == {"missing_space": 1, "extra_space": 1,
                      "correct": 1, "ambiguous": 1}


def test_content_warning_requires_both_short_pdf_and_low_token_overlap():
    assert suspect_different_content(0.32, 1000, 180)
    assert not suspect_different_content(0.32, 1000, 900)
    assert not suspect_different_content(0.91, 1000, 180)
    assert not suspect_different_content(0.32, 0, 180)
