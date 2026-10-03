"""표와 차트의 작은 글자가 페이지 최빈값을 차지해도 본문 크기를 고른다."""
from dochan.pdf.content import Fragment
from dochan.pdf.notes import detect_notes
from dochan.pdf.paths import Segment


def frag(text, x, y, size, order):
    return Fragment(x, y, len(text) * size / 2, size, text, size / 3, order=order)


def detect(fragments):
    return detect_notes(fragments, [Segment(40, 115, 180, 115)], (0, 800), 1)


def test_table_fragments_do_not_hide_smaller_definition():
    fragments = [frag("본문의 관측 지점 설명과 결과가 이어지는 긴 문장입니다", 40, 500, 12.96, 0),
                 frag("그림의 평균 수온과 비교 기간을 설명하는 긴 캡션입니다", 40, 600, 11.04, 1000),
                 frag("해역별 일평균 수온과 조사 지점을 길게 설명하는 캡션입니다", 40, 550, 11.04, 1001),
                 frag("지점", 40, 450, 12.96, 1),
                 frag("2)", 53, 453, 8, 2),
                 frag("2) 관측 지점에 관한 상세한 각주입니다", 40, 100, 9, 3)]
    fragments.extend(frag("표", 40 + index % 30 * 8, 300 + index // 30 * 20, 9.96, 4 + index)
                     for index in range(90))
    notes, _consumed, references, _next = detect(fragments)
    assert [note.text for note in notes] == ["관측 지점에 관한 상세한 각주입니다"]
    assert references == {2: 1}


def test_chart_fragments_do_not_hide_four_notes():
    fragments = [frag("본문에서는 여러 지표를 설명하고 각각의 근거를 각주로 제시합니다", 40, 550, 14.04, 0),
                 frag("남녀 모두 연령이 높아질수록 낮아지는 경향을 보였습니다", 40, 530, 14.04, 20)]
    for index in range(4):
        y = 500 - index * 40
        fragments += [frag("설명", 40, y, 14.04, 1 + index * 2),
                      frag("%d)" % (index + 1), 54, y + 3, 10.56, 2 + index * 2),
                      frag("%d) 지표 설명 %d" % (index + 1, index + 1), 40, 100 - index * 17.5, 9, 10 + index)]
    fragments.extend(frag("축", 200 + index % 30 * 5, 220 + index // 30 * 12, 9, 30 + index)
                     for index in range(120))
    notes, _consumed, references, _next = detect(fragments)
    assert len(notes) == 4
    assert references == {2: 1, 4: 2, 6: 3, 8: 4}


def test_genuinely_small_body_does_not_turn_same_size_definition_into_note():
    fragments = [frag("이 문서의 실제 본문 전체가 작은 글자로 작성되었습니다", 40, 500, 9, 0),
                 frag("본문", 40, 450, 9, 1),
                 frag("1)", 58, 452, 6, 2),
                 frag("1) 이 글은 본문과 같은 크기의 하단 설명입니다", 40, 100, 9, 3)]
    assert detect(fragments)[0] == []


def test_superscript_tolerates_pdf_position_rounding_but_not_deeper_overlap():
    fragments = [frag("본문에서는 측정 결과와 관측 방법을 긴 문장으로 설명합니다", 40, 550, 14.04, 0),
                 frag("남녀 모두 연령이 높아질수록 낮아지는 경향을 보였습니다", 40, 530, 14.04, 1000),
                 frag("지지율", 40, 500, 14.04, 1),
                 frag("1)", 59.62, 502.88, 10.56, 2),
                 frag("1) 지표에 관한 설명", 40, 100, 9, 3)]
    fragments.extend(frag("축", 200 + index % 30 * 5, 220 + index // 30 * 12, 9, 10 + index)
                     for index in range(90))
    assert len(detect(fragments)[0]) == 1
    fragments[2].x = 59.46  # 앞 글자와 1.60pt 겹치면 허용오차 밖이다.
    assert detect(fragments)[0] == []


def test_single_large_heading_does_not_upsize_genuinely_small_body():
    fragments = [frag("아주 긴 제목이 먼저 나오고 문서를 소개하면서 다양한 주제를 설명합니다", 40, 700, 15, 0),
                 frag("본문은 실제로 작은 글자로 쓰인 문장이고 더 많은 내용이 있습니다", 40, 500, 9.96, 1),
                 frag("본문", 40, 450, 9.96, 2),
                 frag("1)", 49.96, 452, 6, 3),
                 frag("1) 이 줄은 각주가 아닌 본문과 비슷한 크기입니다", 40, 100, 9, 4)]
    assert detect(fragments)[0] == []


def test_two_line_large_title_does_not_upsize_small_body():
    """제목이 두 줄로 넘어가도 본문 크기 기준이 커지지 않는다(감수 P2-2)."""
    fragments = [frag("아주 긴 제목이 먼저 나오고 문서를 소개하면서 다양한 주제를 설명합니다", 40, 700, 15, 0),
                 frag("두 줄로 넘어간 제목의 둘째 줄도 서른 글자를 넘는 긴 제목 문장입니다", 40, 682, 15, 5),
                 frag("본문은 실제로 작은 글자로 쓰인 문장이고 더 많은 내용이 있습니다", 40, 500, 9.96, 1),
                 frag("본문", 40, 450, 9.96, 2),
                 frag("1)", 49.96, 452, 6, 3),
                 frag("1) 이 줄은 각주가 아닌 본문과 비슷한 크기입니다", 40, 100, 9, 4)]
    fragments += [frag("본문은 실제로 작은 글자로 쓰인 문장이고 더 많은 내용이 있습니다", 40, 500 - 12 * k, 9.96, 10 + k)
                  for k in range(1, 6)]
    assert detect(fragments)[0] == []


def test_split_marker_leaves_no_gap_before_following_word(tmp_path):
    """두 조각 표지(`1`·`)`)를 소비해도 뒤 낱말 앞에 가짜 공백이 생기지 않는다(감수 P2-1)."""
    from dochan import Dochan
    from test_pdf_structure import _build_pdf
    parts = [b"BT /F1 12 Tf 40 %d Td (More body text here for the page) Tj ET" % (700 - 14 * k) for k in range(6)]
    parts += [b"BT /F1 12 Tf 40 500 Td (Rate) Tj ET", b"BT /F1 9 Tf 64 502.5 Td (1) Tj ET",
              b"BT /F1 9 Tf 68.5 502.5 Td (\\051) Tj ET", b"BT /F1 12 Tf 73 500 Td (rose) Tj ET",
              b"40 115 m 180 115 l S", b"BT /F1 9 Tf 40 100 Td (1\\051 Detail of the note) Tj ET"]
    content = b"\n".join(parts)
    objects = {1: "<< /Type /Catalog /Pages 2 0 R >>",
               2: "<< /Type /Pages /Kids [3 0 R] /Count 1 /MediaBox [0 0 600 800] "
                  "/Resources << /Font << /F1 5 0 R >> >> >>",
               3: "<< /Type /Page /Parent 2 0 R /Contents 4 0 R >>",
               4: b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content),
               5: "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /FirstChar 0 /Widths ["
                  + "500 " * 256 + "] >>"}
    path = tmp_path / "split-marker.pdf"
    path.write_bytes(_build_pdf(objects))
    markdown = Dochan(str(path)).to_markdown()
    assert "Rate[^1]rose" in markdown
