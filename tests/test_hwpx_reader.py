import zipfile

from dochan import Dochan
from dochan.batch import batch_convert
from dochan.cli import _cmd_info
from dochan.hwpx.parser import HWPXParser
from dochan.output.json_out import to_dict
from dochan.output.markdown import to_markdown
from dochan.output.plain_text import to_plain_text

# OWPML 실제 네임스페이스. 합성 픽스처라도 URI 는 실물과 같아야
# _local_tag() 우회 같은 회귀를 잡을 수 있다.
_NS = (
    'xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph" '
    'xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section" '
    'xmlns:hh="http://www.hancom.co.kr/hwpml/2011/head" '
    'xmlns:hc="http://www.hancom.co.kr/hwpml/2011/core"'
)


def _write_hwpx(path, section_xml, header_xml=None, content_hpf_xml=None, extra_parts=None):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/hwp+zip")
        zf.writestr("version.xml", "<hv:HCFVersion/>")
        for name, data in (extra_parts or {}).items():
            zf.writestr(name, data)
        if header_xml:
            zf.writestr("Contents/header.xml", header_xml)
        if content_hpf_xml:
            zf.writestr("Contents/content.hpf", content_hpf_xml)
        zf.writestr("Contents/section0.xml", section_xml)


def _section(body):
    """<hs:sec> 루트로 감싼 section0.xml"""
    return '<hs:sec %s>%s</hs:sec>' % (_NS, body)


def _head(body):
    """<hh:head> 루트로 감싼 header.xml"""
    return '<hh:head %s>%s</hh:head>' % (_NS, body)


def _para(runs, para_pr="0", style="0"):
    return (
        '<hp:p id="0" paraPrIDRef="%s" styleIDRef="%s" pageBreak="0" '
        'columnBreak="0" merged="0">%s</hp:p>' % (para_pr, style, runs)
    )


def _run(inner, char_pr="0"):
    return '<hp:run charPrIDRef="%s">%s</hp:run>' % (char_pr, inner)


def _text_para(text, para_pr="0", style="0", char_pr="0"):
    return _para(_run('<hp:t>%s</hp:t>' % text, char_pr), para_pr, style)


def _char_properties(strikeout_shapes):
    """<hh:charProperties> — strikeout_shapes 는 charPr 순서대로의 shape 값 목록."""
    items = []
    for index, shape in enumerate(strikeout_shapes):
        items.append(
            '<hh:charPr id="%d" height="1000" textColor="#000000">'
            '<hh:underline type="NONE" shape="SOLID" color="#000000"/>'
            '<hh:strikeout shape="%s" color="#000000"/>'
            '</hh:charPr>' % (index, shape)
        )
    return '<hh:charProperties itemCnt="%d">%s</hh:charProperties>' % (
        len(strikeout_shapes), ''.join(items)
    )


def _sub_list(paragraphs):
    return (
        '<hp:subList id="" textDirection="HORIZONTAL" lineWrap="BREAK" '
        'vertAlign="TOP">%s</hp:subList>' % paragraphs
    )


def _cell(text_or_xml, row, col, row_span=1, col_span=1, raw=False):
    body = text_or_xml if raw else _run('<hp:t>%s</hp:t>' % text_or_xml)
    return (
        '<hp:tc name="" header="0" hasMargin="1" protect="0" editable="0" dirty="0">'
        '%s'
        '<hp:cellAddr colAddr="%d" rowAddr="%d"/>'
        '<hp:cellSpan colSpan="%d" rowSpan="%d"/>'
        '<hp:cellSz width="1000" height="1000"/>'
        '</hp:tc>' % (_sub_list(_para(body)), col, row, col_span, row_span)
    )


def _tbl(rows_xml, row_cnt, col_cnt, extra=""):
    return (
        '<hp:tbl id="1" zOrder="0" numberingType="TABLE" textWrap="TOP_AND_BOTTOM" '
        'rowCnt="%d" colCnt="%d" cellSpacing="0" borderFillIDRef="1" noAdjust="0">'
        '<hp:sz width="10000" widthRelTo="ABSOLUTE" height="1000" heightRelTo="ABSOLUTE"/>'
        '%s%s</hp:tbl>' % (row_cnt, col_cnt, extra, rows_xml)
    )


def _hyperlink_begin(url):
    return (
        '<hp:ctrl><hp:fieldBegin id="1" type="HYPERLINK" name="" editable="0" '
        'dirty="1" zorder="-1" fieldid="1">'
        '<hp:parameters cnt="2" name="">'
        '<hp:integerParam name="Prop">0</hp:integerParam>'
        '<hp:stringParam name="Command">%s;1;0;0;</hp:stringParam>'
        '<hp:stringParam name="Path">%s</hp:stringParam>'
        '<hp:stringParam name="Category">HWPHYPERLINK_TYPE_URL</hp:stringParam>'
        '</hp:parameters></hp:fieldBegin></hp:ctrl>'
        % (url.replace(':', '\\:'), url)
    )


_HYPERLINK_END = '<hp:ctrl><hp:fieldEnd beginIDRef="1" fieldid="1"/></hp:ctrl>'


# ── 1. <hp:t> 자식 뒤 tail 텍스트 ──


def test_hwpx_t_element_keeps_tail_text_after_children(tmp_path):
    path = tmp_path / "tail.hwpx"
    _write_hwpx(path, _section(
        _para(_run('<hp:t>앞<hp:fwSpace/>뒤에오는긴문장</hp:t>'))
        + _para(_run('<hp:t>왼쪽<hp:tab/>오른쪽</hp:t>'))
        + _para(_run('<hp:t>강조<hp:markpenBegin/>구간<hp:markpenEnd/>끝</hp:t>'))
    ))

    doc = HWPXParser().parse(str(path))
    texts = [elem.text for elem in doc.sections[0].elements]

    assert texts[0] == "앞 뒤에오는긴문장"
    assert texts[1] == "왼쪽\t오른쪽"
    assert texts[2] == "강조구간끝"


# ── 2. cellAddr/cellSpan 격자 배치 ──


def test_hwpx_table_uses_cell_addr_grid_with_merge_placeholders(tmp_path):
    path = tmp_path / "grid.hwpx"
    # rowCnt=3, colCnt=3.
    # (0,0) 은 rowSpan=2 라 (1,0) 을 가린다 → 두 번째 <hp:tr> 에는 <hp:tc> 가 2개뿐이다.
    # 등장 순서로 배치하면 B1 이 0열로 밀린다.
    rows = (
        '<hp:tr>'
        + _cell("A0", 0, 0, row_span=2)
        + _cell("A1", 0, 1)
        + _cell("A2", 0, 2)
        + '</hp:tr>'
        '<hp:tr>'
        + _cell("B1", 1, 1)
        + _cell("B2", 1, 2)
        + '</hp:tr>'
        '<hp:tr>'
        + _cell("C0", 2, 0, col_span=3)
        + '</hp:tr>'
    )
    _write_hwpx(path, _section(_para(_run(_tbl(rows, 3, 3)))))

    doc = HWPXParser().parse(str(path))
    table = doc.sections[0].elements[0]

    assert table.row_count == 3
    assert table.col_count == 3
    assert table.rows[0][0].text == "A0"
    assert table.rows[0][0].row_span == 2

    # 병합에 가려진 자리는 자리표시자로 남아야 한다
    assert table.rows[1][0].is_merged_away
    assert table.rows[1][1].text == "B1"
    assert table.rows[1][2].text == "B2"

    assert table.rows[2][0].text == "C0"
    assert table.rows[2][1].is_merged_away
    assert table.rows[2][2].is_merged_away

    md_lines = to_markdown(doc).splitlines()
    assert md_lines[0] == "| A0 | A1 | A2 |"
    assert md_lines[2] == "|  | B1 | B2 |"
    assert md_lines[3] == "| C0 |  |  |"

    # plain text 에서도 열이 밀리면 안 된다
    assert to_plain_text(doc).splitlines()[1] == "\tB1\tB2"


# ── 3. 개요(OUTLINE) 기반 제목 ──


_OUTLINE_HEADER = _head(
    _char_properties(["NONE", "NONE"])
    + '<hh:paraProperties itemCnt="4">'
    '<hh:paraPr id="0"><hh:align horizontal="JUSTIFY" vertical="BASELINE"/>'
    '<hh:heading type="NONE" idRef="0" level="0"/></hh:paraPr>'
    '<hh:paraPr id="11"><hh:align horizontal="LEFT" vertical="BASELINE"/>'
    '<hh:heading type="OUTLINE" idRef="0" level="0"/></hh:paraPr>'
    '<hh:paraPr id="12"><hh:align horizontal="LEFT" vertical="BASELINE"/>'
    '<hh:heading type="OUTLINE" idRef="0" level="1"/></hh:paraPr>'
    '<hh:paraPr id="13"><hh:align horizontal="LEFT" vertical="BASELINE"/>'
    '<hh:heading type="OUTLINE" idRef="0" level="4"/></hh:paraPr>'
    '<hh:paraPr id="14"><hh:align horizontal="LEFT" vertical="BASELINE"/>'
    '<hh:heading type="OUTLINE" idRef="0" level="2"/></hh:paraPr>'
    '</hh:paraProperties>'
    '<hh:styles itemCnt="5">'
    '<hh:style id="0" type="PARA" name="바탕글" engName="Normal" '
    'paraPrIDRef="0" charPrIDRef="0" nextStyleIDRef="0"/>'
    '<hh:style id="1" type="PARA" name="개요 1" engName="Outline 1" '
    'paraPrIDRef="11" charPrIDRef="0" nextStyleIDRef="1"/>'
    '<hh:style id="2" type="PARA" name="사용자정의" engName="Custom" '
    'paraPrIDRef="12" charPrIDRef="0" nextStyleIDRef="2"/>'
    '<hh:style id="3" type="PARA" name="개요 5" engName="Outline 5" '
    'paraPrIDRef="13" charPrIDRef="0" nextStyleIDRef="3"/>'
    '<hh:style id="4" type="PARA" name="사용자정의3" engName="Custom3" '
    'paraPrIDRef="14" charPrIDRef="0" nextStyleIDRef="4"/>'
    '</hh:styles>'
)


def test_hwpx_outline_style_name_becomes_heading(tmp_path):
    path = tmp_path / "outline-name.hwpx"
    _write_hwpx(
        path,
        _section(
            _text_para("제1장 총칙", para_pr="11", style="1")
            + _text_para("보통 문단", para_pr="0", style="0")
        ),
        header_xml=_OUTLINE_HEADER,
    )

    doc = HWPXParser().parse(str(path))
    elements = doc.sections[0].elements

    assert elements[0].heading_level == 1
    assert elements[1].heading_level == 0
    assert to_markdown(doc) == "# 제1장 총칙\n\n보통 문단"


def test_hwpx_outline_para_pr_becomes_heading(tmp_path):
    path = tmp_path / "outline-parapr.hwpx"
    _write_hwpx(
        path,
        _section(
            # 스타일 이름은 개요 패턴이 아니다 → style→paraPr 경유로만 개요를 알 수 있다
            _text_para("제1절 목적", para_pr="12", style="2")
            # 스타일은 바탕글이고 문단 자신의 paraPr 만 개요다
            + _text_para("직접 지정 개요", para_pr="11", style="0")
        ),
        header_xml=_OUTLINE_HEADER,
    )

    doc = HWPXParser().parse(str(path))
    elements = doc.sections[0].elements

    assert elements[0].heading_level == 2
    assert elements[1].heading_level == 1
    assert to_markdown(doc) == "## 제1절 목적\n\n# 직접 지정 개요"


def test_hwpx_deep_outline_level_is_not_heading(tmp_path):
    path = tmp_path / "outline-deep.hwpx"
    _write_hwpx(
        path,
        _section(
            # level 2 → 헤딩 3 (상한 경계 안쪽)
            _text_para("1) 경계 안쪽", para_pr="14", style="4")
            # level 4 → 헤딩 5 였을 것 (상한 밖)
            + _text_para("가. 세부 항목", para_pr="13", style="3")
        ),
        header_xml=_OUTLINE_HEADER,
    )

    doc = HWPXParser().parse(str(path))
    elements = doc.sections[0].elements

    assert elements[0].heading_level == 3
    # MAX_OUTLINE_HEADING_LEVEL=3 상한 — '개요 5'(level 4)는 본문 열거 항목이다
    assert elements[1].heading_level == 0
    assert to_markdown(doc) == "### 1) 경계 안쪽\n\n가. 세부 항목"


# ── 4. 하이퍼링크 ──


def test_hwpx_hyperlink_inside_single_run(tmp_path):
    path = tmp_path / "link-single-run.hwpx"
    _write_hwpx(path, _section(_para(_run(
        '<hp:t>방문: </hp:t>'
        + _hyperlink_begin("https://example.com")
        + '<hp:t>예제 사이트</hp:t>'
        + _HYPERLINK_END
        + '<hp:t> 참고</hp:t>'
    ))))

    doc = HWPXParser().parse(str(path))
    runs = doc.sections[0].elements[0].runs

    assert [r.text for r in runs] == ["방문: ", "예제 사이트", " 참고"]
    assert [r.link for r in runs] == ["", "https://example.com", ""]
    assert to_markdown(doc) == "방문: [예제 사이트](https://example.com) 참고"
    assert to_plain_text(doc) == "방문: 예제 사이트 <https://example.com> 참고"


def test_hwpx_hyperlink_spanning_separate_runs(tmp_path):
    path = tmp_path / "link-multi-run.hwpx"
    _write_hwpx(path, _section(_para(
        _run('<hp:t>문의: </hp:t>' + _hyperlink_begin("https://www.example.org"))
        + _run('<hp:t>예제 도메인</hp:t>')
        + _run(_HYPERLINK_END + '<hp:t> 으로</hp:t>')
    )))

    doc = HWPXParser().parse(str(path))
    runs = doc.sections[0].elements[0].runs

    assert [r.text for r in runs] == ["문의: ", "예제 도메인", " 으로"]
    assert [r.link for r in runs] == ["", "https://www.example.org", ""]
    assert to_markdown(doc) == "문의: [예제 도메인](https://www.example.org) 으로"

    run_dict = to_dict(doc)['sections'][0]['elements'][0]['runs']
    assert run_dict[1]['link'] == "https://www.example.org"
    assert 'link' not in run_dict[0]


def test_hwpx_hyperlink_falls_back_to_command_when_path_missing(tmp_path):
    """실측(corpus 80168_regulatory_analysis.hwpx): 일부 생성기는 Path 없이
    Command 만 싣는다. Command 의 이스케이프를 풀어 URL 로 써야 한다."""
    begin = (
        '<hp:ctrl><hp:fieldBegin id="1" type="HYPERLINK" name="" editable="0">'
        '<hp:parameters cnt="1" name="">'
        '<hp:stringParam name="Command">https\\://www.law.go.kr/lsSc.do\\?query=1\\#AJAX;1;0;0;</hp:stringParam>'
        '</hp:parameters></hp:fieldBegin></hp:ctrl>'
    )
    path = tmp_path / "link-command-only.hwpx"
    _write_hwpx(path, _section(_para(
        _run(begin + '<hp:t>조례</hp:t>' + _HYPERLINK_END)
    )))

    doc = HWPXParser().parse(str(path))
    runs = doc.sections[0].elements[0].runs

    assert [(r.text, r.link) for r in runs] == [
        ("조례", "https://www.law.go.kr/lsSc.do?query=1#AJAX")]


def test_hwpx_hyperlink_command_only_internal_bookmark_and_script(tmp_path):
    """책갈피형('?참조')은 문서 내 책갈피로 가는 내부 하이퍼링크(#참조)로 만들고,
    스크립트형('javascript...')은 여전히 버린다 (실측: 143E433F503322BD33 —
    HWP %hlk '?참조' ↔ HWPX HYPERLINK TargetType=BOOKMARK '?참조', HWP 경로와 동일)."""
    def begin(cmd):
        return (
            '<hp:ctrl><hp:fieldBegin id="1" type="HYPERLINK" name="" editable="0">'
            '<hp:parameters cnt="1" name="">'
            '<hp:stringParam name="Command">%s</hp:stringParam>'
            '</hp:parameters></hp:fieldBegin></hp:ctrl>' % cmd
        )

    path = tmp_path / "link-internal.hwpx"
    _write_hwpx(path, _section(
        _para(_run(begin('?참조;0;0;0;') + '<hp:t>내부참조</hp:t>' + _HYPERLINK_END))
        + _para(_run(begin('javascript\\:\\;;1;0;0;') + '<hp:t>제1항</hp:t>' + _HYPERLINK_END))
    ))

    doc = HWPXParser().parse(str(path))
    elements = doc.sections[0].elements
    # 책갈피형 → 내부 하이퍼링크 #참조
    assert [(r.text, r.link) for r in elements[0].runs] == [("내부참조", "#참조")]
    # 스크립트형 → 링크 없음
    assert all(not r.link for r in elements[1].runs)
    assert to_markdown(doc).splitlines()[0] == "[내부참조](#참조)"


def test_hwpx_field_result_text_is_captured(tmp_path):
    """필드(누름틀 CLICK_HERE / 계산식 FORMULA)의 결과 텍스트가 본문에 그대로
    남고 하이퍼링크는 걸리지 않는다.
    (필드 결과 텍스트 + 컨트롤/스마트 태그 텍스트) — 실측 문서관리규칙 '공개',
    사내벤처 창업 및 운영지침 '100'."""
    def field(ftype, result):
        return (
            ('<hp:ctrl><hp:fieldBegin id="1" type="%s" name="" editable="1">'
             '<hp:parameters cnt="0" name=""/></hp:fieldBegin></hp:ctrl>' % ftype)
            + ('<hp:t>%s</hp:t>' % result)
            + '<hp:ctrl><hp:fieldEnd beginIDRef="1" fieldid="1"/></hp:ctrl>'
        )

    path = tmp_path / "field-result.hwpx"
    _write_hwpx(path, _section(
        _para(_run('<hp:t>구분: </hp:t>' + field("CLICK_HERE", "공개")))
        + _para(_run('<hp:t>합계 </hp:t>' + field("FORMULA", "100")))
    ))

    doc = HWPXParser().parse(str(path))
    elements = doc.sections[0].elements
    assert elements[0].text == "구분: 공개"
    assert elements[1].text == "합계 100"
    for elem in elements:
        assert all(not r.link for r in elem.runs)


def test_hwpx_bookmark_becomes_marker(tmp_path):
    """<hp:bookmark name="참조"/> 가 [bookmark: 참조] 마커로 나온다.
    (내부 북마크) — 실측 143E433F503322BD33 '참조', 전략물자 종합교육 'wrapper'."""
    path = tmp_path / "bookmark.hwpx"
    _write_hwpx(path, _section(_para(_run(
        '<hp:ctrl><hp:bookmark name="참조"/></hp:ctrl>'
        + '<hp:t>국민연금 보험료</hp:t>'
    ))))

    doc = HWPXParser().parse(str(path))
    para = doc.sections[0].elements[0]
    assert "[bookmark: 참조]" in para.text
    assert "국민연금 보험료" in para.text


def test_hwpx_bookmark_underscore_name_is_ignored(tmp_path):
    """_GoBack 등 밑줄로 시작하는 자동 책갈피는 마커로 내보내지 않는다 (DOCX 규약)."""
    path = tmp_path / "bookmark-goback.hwpx"
    _write_hwpx(path, _section(_para(_run(
        '<hp:ctrl><hp:bookmark name="_GoBack"/></hp:ctrl>'
        + '<hp:t>본문</hp:t>'
    ))))

    doc = HWPXParser().parse(str(path))
    para = doc.sections[0].elements[0]
    assert para.text == "본문"


def test_hwpx_hidden_comment_becomes_comment_footnote(tmp_path):
    """<hp:hiddenComment>(HWP 바이너리의 tcmt 대응 — 실측 hwp2hwpx-from_18.hwpx)
    가 Footnote(type='comment') 로 나온다."""
    from dochan.model.header_footer import Footnote

    hidden = (
        '<hp:ctrl><hp:hiddenComment>'
        + _sub_list(_para(_run('<hp:t>이것은 숨은 설명입니다.</hp:t>')))
        + '</hp:hiddenComment></hp:ctrl>'
    )
    path = tmp_path / "hidden-comment.hwpx"
    _write_hwpx(path, _section(_para(_run('<hp:t>본문</hp:t>' + hidden))))

    doc = HWPXParser().parse(str(path))
    comments = [e for e in doc.sections[0].elements
                if isinstance(e, Footnote) and e.type == 'comment']

    assert len(comments) == 1
    assert comments[0].text == "이것은 숨은 설명입니다."
    assert "[^comment-1]: 이것은 숨은 설명입니다." in to_markdown(doc)


def test_hwpx_memogroup_memos_become_comment_footnotes(tmp_path):
    """섹션 루트의 <hp:memogroup>/<hp:memo>(실측 leap-source.hwpx 구조)가
    Footnote(type='comment') 로 나온다."""
    from dochan.model.header_footer import Footnote

    memos = (
        '<hp:memogroup>'
        '<hp:memo id="memo-0"><hp:paraList>'
        + _para(_run('<hp:t>첫 번째 메모</hp:t>'))
        + '</hp:paraList></hp:memo>'
        '<hp:memo id="memo-1"><hp:paraList>'
        + _para(_run('<hp:t>두 번째 메모</hp:t>'))
        + '</hp:paraList></hp:memo>'
        '</hp:memogroup>'
    )
    path = tmp_path / "memogroup.hwpx"
    _write_hwpx(path, _section(_para(_run('<hp:t>본문</hp:t>')) + memos))

    doc = HWPXParser().parse(str(path))
    comments = [e for e in doc.sections[0].elements
                if isinstance(e, Footnote) and e.type == 'comment']

    assert [c.text for c in comments] == ["첫 번째 메모", "두 번째 메모"]
    md = to_markdown(doc)
    assert "[^comment-1]: 첫 번째 메모" in md
    assert "[^comment-2]: 두 번째 메모" in md


# ── 5. 표 캡션 ──


def test_hwpx_table_caption_top_renders_above_table(tmp_path):
    path = tmp_path / "caption.hwpx"
    caption = (
        '<hp:caption side="TOP" fullSz="0" width="8504" gap="850">'
        + _sub_list(_para(_run('<hp:t>표 1 지원 현황</hp:t>')))
        + '</hp:caption>'
    )
    rows = '<hp:tr>' + _cell("항목", 0, 0) + _cell("값", 0, 1) + '</hp:tr>'
    _write_hwpx(path, _section(_para(_run(_tbl(rows, 1, 2, extra=caption)))))

    doc = HWPXParser().parse(str(path))
    table = doc.sections[0].elements[0]

    assert table.caption_side == "TOP"
    assert table.caption_text == "표 1 지원 현황"

    md = to_markdown(doc)
    assert md.startswith("*표 1 지원 현황*\n\n| 항목 | 값 |")

    assert to_plain_text(doc).splitlines()[0] == "표 1 지원 현황"
    assert to_dict(doc)['sections'][0]['elements'][0]['caption']['side'] == "TOP"


# ── 6. shapeComment → alt_text ──


def test_hwpx_shape_comment_becomes_alt_text_not_body_text(tmp_path):
    path = tmp_path / "shape-comment.hwpx"
    comment = (
        '<hp:shapeComment>그림입니다.\n'
        '원본 그림의 이름: (횡_기본)로고.jpg\n'
        '원본 그림의 크기: 가로 5979pixel, 세로 1083pixel</hp:shapeComment>'
    )
    pic = (
        '<hp:pic reverse="0">'
        '<hc:img binaryItemIDRef="image1" bright="0" contrast="0" effect="REAL_PIC"/>'
        + comment
        + '</hp:pic>'
    )
    cell = _cell(_run(pic), 0, 0, raw=True)
    _write_hwpx(
        path,
        _section(
            _text_para("머리 문장")
            + _para(_run(pic))
            + _para(_run(_tbl('<hp:tr>' + cell + '</hp:tr>', 1, 1)))
        ),
        content_hpf_xml=(
            '<opf:package xmlns:opf="http://www.idpf.org/2007/opf/">'
            '<opf:manifest>'
            '<opf:item id="image1" href="BinData/image1.jpg" media-type="image/jpg"/>'
            '</opf:manifest></opf:package>'
        ),
        extra_parts={"BinData/image1.jpg": b"JPEGDATA-1"},
    )

    doc = HWPXParser().parse(str(path))
    images = doc.find_all('image')

    assert len(images) == 2
    assert images[0].alt_text.startswith("그림입니다.")
    assert "(횡_기본)로고.jpg" in images[0].alt_text

    md = to_markdown(doc)
    assert "![그림입니다. 원본 그림의 이름: (횡_기본)로고.jpg " \
           "원본 그림의 크기: 가로 5979pixel, 세로 1083pixel](BinData/image1.jpg)" in md

    # 본문으로는 절대 새면 안 된다 — 한글이 자동 생성한 메타데이터다
    plain = to_plain_text(doc)
    assert "원본 그림의 이름" not in plain
    assert plain.splitlines()[0] == "머리 문장"

    # 표 셀 안에서도 마찬가지
    table = doc.sections[0].elements[2]
    assert table.rows[0][0].text == ""


# ── 7. 도형 텍스트 (drawText) ──


def test_hwpx_draw_text_in_shape_and_container(tmp_path):
    path = tmp_path / "draw-text.hwpx"
    draw_text = (
        '<hp:drawText lastWidth="20377" name="" editable="0">'
        + _sub_list(_para(_run('<hp:t>%s</hp:t>')))
        + '<hp:textMargin left="284" right="284" top="284" bottom="284"/>'
        '</hp:drawText>'
    )
    rect = '<hp:rect ratio="0">' + (draw_text % "사각형 안 텍스트") + '</hp:rect>'
    nested = (
        '<hp:container>'
        '<hp:rect ratio="0">' + (draw_text % "중첩 도형 텍스트") + '</hp:rect>'
        '</hp:container>'
    )
    _write_hwpx(path, _section(
        _text_para("본문 문장")
        + _para(_run(rect))
        + _para(_run(nested))
    ))

    doc = HWPXParser().parse(str(path))
    texts = [elem.text for elem in doc.sections[0].elements]

    assert texts == ["본문 문장", "사각형 안 텍스트", "중첩 도형 텍스트"]


# ── 8. 각주/미주 번호 매기기 ──


def test_hwpx_footnotes_and_endnote_get_distinct_labels(tmp_path):
    path = tmp_path / "notes.hwpx"

    def note(tag, body):
        return (
            '<hp:ctrl><hp:%s suffixChar="41" instId="1">%s</hp:%s></hp:ctrl>'
            % (tag, _sub_list(_para(_run('<hp:t>%s</hp:t>' % body))), tag)
        )

    _write_hwpx(path, _section(
        _para(_run('<hp:t>첫 문장</hp:t>' + note('footNote', '첫 번째 각주')))
        + _para(_run('<hp:t>둘째 문장</hp:t>' + note('footNote', '두 번째 각주')))
        + _para(_run('<hp:t>셋째 문장</hp:t>' + note('endNote', '미주 본문')))
    ))

    doc = HWPXParser().parse(str(path))
    md = to_markdown(doc)

    # 본문에 참조 마커가 남고 정의는 문서 말미에 모인다.
    # 마커 없이 정의만 남기면 Markdown 렌더러가 미참조 정의를 통째로 버린다.
    assert md == (
        "첫 문장[^1]\n\n"
        "둘째 문장[^2]\n\n"
        "셋째 문장[^3]\n\n"
        "[^1]: 첫 번째 각주\n\n"
        "[^2]: 두 번째 각주\n\n"
        "[^3]: 미주 본문"
    )
    # 라벨이 종류 이름으로 뭉개지면 안 된다
    assert "[^각주]" not in md
    assert "[^미주]" not in md

    # 모든 정의에 대응하는 본문 참조가 있어야 한다
    for number in (1, 2, 3):
        assert md.count("[^%d]" % number) == 2  # 참조 1 + 정의 1


# ── 9. 중첩 표 ──


def test_hwpx_nested_table_text_survives_in_cell(tmp_path):
    path = tmp_path / "nested-table.hwpx"
    inner_rows = (
        '<hp:tr>' + _cell("n00", 0, 0) + _cell("n01", 0, 1) + '</hp:tr>'
        '<hp:tr>' + _cell("n10", 1, 0) + _cell("n11", 1, 1) + '</hp:tr>'
    )
    inner = _tbl(inner_rows, 2, 2)
    outer_rows = (
        '<hp:tr>'
        + _cell(_run(inner), 0, 0, raw=True)
        + _cell("바깥 칸", 0, 1)
        + '</hp:tr>'
    )
    _write_hwpx(path, _section(_para(_run(_tbl(outer_rows, 1, 2)))))

    doc = HWPXParser().parse(str(path))
    outer = doc.sections[0].elements[0]

    assert outer.rows[0][0].text == "n00\tn01\nn10\tn11"

    md = to_markdown(doc)
    assert "| n00 / n01 ; n10 / n11 | 바깥 칸 |" in md

    plain = to_plain_text(doc)
    assert "n00" in plain and "n11" in plain

    cell_dict = to_dict(doc)['sections'][0]['elements'][0]['rows'][0][0]
    assert cell_dict['paragraphs'][0]['type'] == 'table'


# ── 10. 메타데이터 ──


def test_hwpx_metadata_reports_shape_counts_and_format(tmp_path):
    path = tmp_path / "metadata.hwpx"
    _write_hwpx(
        path,
        _section(_text_para("메타데이터 확인")),
        header_xml=_OUTLINE_HEADER,
    )

    doc = HWPXParser().parse(str(path))
    metadata = doc.metadata

    assert metadata['source_format'] == "hwpx"
    assert metadata['char_shapes'] == 2
    assert metadata['para_shapes'] == 5
    assert metadata['styles'] == 5
    assert metadata['sections'] == 1
    assert doc.styles[1].name == "개요 1"
    assert to_dict(doc)['metadata']['source_format'] == "hwpx"


# ── 11. content.hpf 바이너리 매핑 ──


def test_hwpx_content_hpf_maps_binary_ids_exactly(tmp_path):
    path = tmp_path / "bin-map.hwpx"

    def pic(bin_id):
        return _para(_run(
            '<hp:pic reverse="0">'
            '<hc:img binaryItemIDRef="%s" bright="0" contrast="0"/>'
            '</hp:pic>' % bin_id
        ))

    _write_hwpx(
        path,
        _section(pic("image1") + pic("image10")),
        content_hpf_xml=(
            '<opf:package xmlns:opf="http://www.idpf.org/2007/opf/">'
            '<opf:manifest>'
            '<opf:item id="header" href="Contents/header.xml" media-type="application/xml"/>'
            '<opf:item id="image1" href="BinData/image1.jpg" media-type="image/jpg"/>'
            '<opf:item id="image10" href="BinData/image10.png" media-type="image/png"/>'
            '<opf:item id="section0" href="Contents/section0.xml" media-type="application/xml"/>'
            '</opf:manifest></opf:package>'
        ),
        # image10 을 먼저 넣어 부분문자열 매칭이면 image1 이 image10 에 걸리게 만든다
        extra_parts={
            "BinData/image10.png": b"PNGDATA-10",
            "BinData/image1.jpg": b"JPEGDATA-1",
        },
    )

    doc = HWPXParser().parse(str(path))
    images = doc.find_all('image')

    assert [img.filename for img in images] == [
        "BinData/image1.jpg",
        "BinData/image10.png",
    ]
    assert images[0].image_data == b"JPEGDATA-1"
    assert images[1].image_data == b"PNGDATA-10"


# ── 12. 취소선 ──


_STRIKEOUT_SECTION = _section(
    _text_para("보통 문장", char_pr="0")
    + _text_para("표시된 문장", char_pr="1")
)


def test_hwpx_blanket_strikeout_is_dropped(tmp_path):
    path = tmp_path / "strikeout-all.hwpx"
    _write_hwpx(
        path,
        _STRIKEOUT_SECTION,
        header_xml=_head(_char_properties(["3D", "3D", "3D", "3D", "3D", "3D"])),
    )

    doc = HWPXParser().parse(str(path))

    # 전 글자모양에 취소선이 걸린 건 문서 기본값이지 실제 취소선이 아니다
    assert all(not run.strikeout
               for elem in doc.sections[0].elements
               for run in elem.runs)
    assert all(entry.strikeout == 0 for entry in doc.char_shapes)
    assert "~~" not in to_markdown(doc)


def test_hwpx_partial_strikeout_is_kept(tmp_path):
    path = tmp_path / "strikeout-partial.hwpx"
    _write_hwpx(
        path,
        _STRIKEOUT_SECTION,
        header_xml=_head(_char_properties(["NONE", "SOLID", "NONE", "NONE", "NONE", "NONE"])),
    )

    doc = HWPXParser().parse(str(path))
    elements = doc.sections[0].elements

    assert elements[0].runs[0].strikeout is False
    assert elements[1].runs[0].strikeout is True
    assert doc.char_shapes[0].strikeout == 0
    assert doc.char_shapes[1].strikeout == 1
    assert to_markdown(doc) == "보통 문장\n\n~~표시된 문장~~"


# ── 13. 머리글 안 표 셀의 이미지 ──


def test_hwpx_image_inside_header_table_is_found(tmp_path):
    path = tmp_path / "header-image.hwpx"
    pic = (
        '<hp:pic reverse="0">'
        '<hc:img binaryItemIDRef="image1" bright="0" contrast="0"/>'
        '</hp:pic>'
    )
    header_table = _tbl(
        '<hp:tr>' + _cell(_run(pic), 0, 0, raw=True) + _cell("문서명", 0, 1) + '</hp:tr>',
        1, 2,
    )
    header_ctrl = (
        '<hp:ctrl><hp:header id="9" applyPageType="BOTH">'
        + _sub_list(_para(_run(header_table)))
        + '</hp:header></hp:ctrl>'
    )
    _write_hwpx(
        path,
        _section(_para(_run(header_ctrl + '<hp:t>본문 시작</hp:t>'))),
        content_hpf_xml=(
            '<opf:package xmlns:opf="http://www.idpf.org/2007/opf/">'
            '<opf:manifest>'
            '<opf:item id="image1" href="BinData/image1.png" media-type="image/png"/>'
            '</opf:manifest></opf:package>'
        ),
        extra_parts={"BinData/image1.png": b"PNGDATA-HEADER"},
    )

    doc = HWPXParser().parse(str(path))
    images = doc.find_all('image')

    # 머리글 → 표 → 셀 안까지 재귀해야 찾을 수 있다
    assert len(images) == 1
    assert images[0].filename == "BinData/image1.png"
    # 바이너리 로드/OCR 대상에 들어왔다는 증거
    assert images[0].image_data == b"PNGDATA-HEADER"

    header = doc.sections[0].elements[0]
    assert header.type == "header"
    assert "문서명" in header.text


# ── 14. 통합 경로 ──


def test_dochan_routes_hwpx_to_native_reader(tmp_path):
    path = tmp_path / "integrated.hwpx"
    _write_hwpx(
        path,
        _section(
            _text_para("제1장 총칙", para_pr="11", style="1")
            + _text_para("본문 내용", para_pr="0", style="0")
        ),
        header_xml=_OUTLINE_HEADER,
    )

    doc = Dochan(str(path))

    assert doc.metadata['source_format'] == "hwpx"
    assert doc.to_markdown() == "# 제1장 총칙\n\n본문 내용"


def test_batch_convert_includes_hwpx_by_default(tmp_path):
    input_dir = tmp_path / "in"
    output_dir = tmp_path / "out"
    input_dir.mkdir()
    _write_hwpx(input_dir / "doc.hwpx", _section(_text_para("배치 HWPX")))

    summary = batch_convert(str(input_dir), str(output_dir), output_format="markdown", max_workers=1)

    assert summary.total == 1
    assert summary.success == 1
    assert (output_dir / "doc.md").read_text(encoding="utf-8") == "배치 HWPX"


def test_cli_info_reports_hwpx_format(tmp_path, capsys):
    class Args:
        pass

    path = tmp_path / "info.hwpx"
    _write_hwpx(path, _section(_text_para("정보 HWPX")))
    args = Args()
    args.file = str(path)

    _cmd_info(args)
    out = capsys.readouterr().out

    assert '"format": "hwpx"' in out
