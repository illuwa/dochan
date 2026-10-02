import pytest

from dochan.pdf.reader import PDFReader
from dochan.output.markdown import to_markdown
from dochan.output.json_out import to_dict
from test_pdf_structure import _build_pdf, _minimal_objects


def _read(tmp_path, annotations, extra=None, content=b"BT /F1 12 Tf 72 720 Td (Body) Tj ET"):
    objects = _minimal_objects(content)
    # 기하 테스트의 500-unit 폭을 폰트 사전에 선언한다. Helvetica의 누락 폭을
    # 500으로 추측하던 이전 픽스처는 링크 경계 오류를 고정하고 있었다.
    objects[4] = ("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /FirstChar 0 "
                  "/Widths [%s] >>" % " ".join(["500"] * 256))
    objects[3] = objects[3][:-2] + " /Annots [%s] >>" % " ".join(
        "%d 0 R" % (6 + i) for i in range(len(annotations)))
    for index, annot in enumerate(annotations, 6):
        objects[index] = annot
    objects.update(extra or {})
    path = tmp_path / "annotations.pdf"
    path.write_bytes(_build_pdf(objects))
    return PDFReader().read(str(path))


def test_pdf_markup_comments_author_contents_and_popup_dedup(tmp_path):
    doc = _read(tmp_path, [
        "<< /Subtype /Text /Contents (Review) /T (Alice) /Popup 7 0 R >>",
        "<< /Subtype /Popup /Parent 6 0 R /Contents (Review) >>",
        "<< /Subtype /Highlight /Contents (Emphasis) /T <feff0042006f0062> >>",
        "<< /Subtype /Link /Contents (Not a comment) >>",
    ])
    comments = doc.find_all("comment")
    assert [(c.number, c.author, c.text) for c in comments] == [(1, "Alice", "Review"), (2, "Bob", "Emphasis")]
    markdown = to_markdown(doc)
    assert markdown.count("[^comment-1]: Review") == 1
    assert markdown.count("[^comment-2]: Emphasis") == 1
    encoded = to_dict(doc)
    assert [e["author"] for e in encoded["sections"][0]["elements"] if e["type"] == "comment"] == ["Alice", "Bob"]


def test_pdf_richtext_comment_fallback_is_plain_text_without_entities(tmp_path):
    doc = _read(tmp_path, [
        "<< /Subtype /FreeText /RC (<body><p>First &amp; second</p><p>Third</p></body>) /T (Author) >>",
        "<< /Subtype /Underline /Contents (Plain wins) /RC (<body>Rich</body>) >>",
        "<< /Subtype /Text /RC (<!DOCTYPE body [<!ENTITY secret SYSTEM 'file:///etc/passwd'>]><body>&secret;</body>) >>",
    ])
    comments = doc.find_all("comment")
    assert [c.text for c in comments] == ["First & second\nThird", "Plain wins"]
    assert any("RC" in error for error in doc.errors)


def test_pdf_comments_share_document_numbering_and_ignore_empty(tmp_path):
    objects = _minimal_objects()
    objects[2] = "<< /Type /Pages /Kids [3 0 R 7 0 R] /Count 2 >>"
    objects[3] = objects[3][:-2] + " /Annots [6 0 R 6 0 R] >>"
    objects[6] = "<< /Subtype /Text /Contents (One) >>"
    objects[7] = "<< /Type /Page /Parent 2 0 R /Annots [8 0 R 9 0 R] >>"
    objects[8] = "<< /Subtype /StrikeOut /Contents (Two) >>"
    objects[9] = "<< /Subtype /Text /Contents () >>"
    path = tmp_path / "comments.pdf"
    path.write_bytes(_build_pdf(objects))
    comments = PDFReader().read(str(path)).find_all("comment")
    assert [(c.number, c.text) for c in comments] == [(1, "One"), (2, "Two")]


def test_pdf_internal_link_direct_named_and_name_tree(tmp_path):
    extra = {
        1: "<< /Type /Catalog /Pages 2 0 R /Dests << /old [10 0 R /Fit] >> /Names << /Dests 11 0 R >> >>",
        2: "<< /Type /Pages /Kids [3 0 R 10 0 R] /Count 2 >>",
        10: "<< /Type /Page /Parent 2 0 R >>",
        11: "<< /Kids [12 0 R] >>",
        12: "<< /Names [(modern) << /D [10 0 R /XYZ 0 0 null] >>] >>",
    }
    doc = _read(tmp_path, [
        "<< /Subtype /Link /Dest [10 0 R /Fit] >>",
        "<< /Subtype /Link /A << /S /GoTo /D /old >> >>",
        "<< /Subtype /Link /A << /S /GoTo /D (modern) >> >>",
    ], extra)
    links = [r.link for p in doc.find_all("paragraph") for r in p.runs if r.link]
    assert links == ["#page-2"]  # 같은 대상의 페이지 끝 링크는 중복시키지 않는다.
    assert "[bookmark: page-2]" in to_markdown(doc)
    assert "[Page 2](#page-2)" in to_markdown(doc)


def test_pdf_destination_cycles_and_remote_actions_are_not_local(tmp_path):
    doc = _read(tmp_path, [
        "<< /Subtype /Link /Dest (loop) >>",
        "<< /Subtype /Link /A << /S /GoToR /F (other.pdf) /D [0 /Fit] >> >>",
    ], {1: "<< /Type /Catalog /Pages 2 0 R /Dests << /loop (loop) >> /Names << /Dests 10 0 R >> >>",
        10: "<< /Kids [10 0 R] >>"})
    assert not any(r.link for p in doc.find_all("paragraph") for r in p.runs)
    assert any("목적지" in error for error in doc.errors)


def test_pdf_link_attaches_only_overlapping_body_characters(tmp_path):
    doc = _read(tmp_path, [
        "<< /Subtype /Link /Rect [96 717 114 731] /A << /S /URI /URI (https://example.org) >> >>",
    ], content=b"BT /F1 12 Tf 72 720 Td (abc def ghi) Tj ET")
    runs = doc.sections[0].elements[0].runs
    assert [(r.text, r.link) for r in runs] == [("abc ", ""), ("def", "https://example.org"), (" ghi", "")]
    assert "abc [def](https://example.org) ghi" == to_markdown(doc)


def test_pdf_quadpoints_limit_multiline_rect_link_and_leave_neighbors(tmp_path):
    content = (b"BT /F1 12 Tf 72 720 Td (link) Tj ET "
               b"BT /F1 12 Tf 150 720 Td (neighbor) Tj ET "
               b"BT /F1 12 Tf 72 690 Td (second) Tj ET")
    doc = _read(tmp_path, [
        "<< /Subtype /Link /Rect [72 686 198 732] /QuadPoints [72 732 96 732 72 716 96 716] "
        "/A << /S /URI /URI (https://example.org) >> >>",
    ], content=content)
    linked = [(r.text, r.link) for p in doc.find_all("paragraph") for r in p.runs if r.link]
    assert linked == [("link", "https://example.org")]


def test_pdf_link_matches_ctm_coordinates_and_preserves_table_runs(tmp_path):
    content = (b"0 600 200 100 re S 100 600 m 100 700 l S 0 650 m 200 650 l S "
               b"q 2 0 0 2 10 610 cm BT /F1 10 Tf (Cell) Tj ET Q "
               b"BT /F1 10 Tf 120 660 Td (Other) Tj ET")
    doc = _read(tmp_path, [
        "<< /Subtype /Link /Rect [10 607 50 630] /A << /S /URI /URI (https://cell.example) >> >>",
    ], content=content)
    table = doc.find_all("table")[0]
    linked = [(r.text, r.link) for row in table.rows for cell in row
              for p in cell.paragraphs for r in getattr(p, "runs", []) if r.link]
    assert linked == [("Cell", "https://cell.example")]
    assert "[Cell](https://cell.example)" in to_markdown(doc)


def test_pdf_ambiguous_and_nonoverlapping_links_do_not_attach(tmp_path):
    doc = _read(tmp_path, [
        "<< /Subtype /Link /Rect [72 716 96 732] /A << /S /URI /URI (https://one.example) >> >>",
        "<< /Subtype /Link /Rect [72 716 96 732] /A << /S /URI /URI (https://two.example) >> >>",
        "<< /Subtype /Link /Rect [400 40 450 60] /A << /S /URI /URI (https://far.example) >> >>",
    ], content=b"BT /F1 12 Tf 72 720 Td (Body) Tj ET")
    assert all(not r.link for r in doc.sections[0].elements[0].runs)


def test_pdf_richtext_utf16_dtd_rejected_and_xml_comments_ignored():
    from dochan.pdf.annotations import _rich_text
    warnings = []
    encoded = b"\xfe\xff" + '<!DOCTYPE body SYSTEM "file:///etc/passwd"><body>safe</body>'.encode("utf-16-be")
    assert _rich_text(encoded, warnings) == ""
    assert warnings
    assert _rich_text(b"<body><!--note--><?note hello?><p>Keep me</p></body>", []) == "Keep me"


def test_pdf_richtext_utf16le_dtd_is_also_rejected():
    from dochan.pdf.annotations import _rich_text
    warnings = []
    value = b"\xff\xfe" + '<!DOCTYPE body SYSTEM "file:///etc/passwd"><body>safe</body>'.encode("utf-16-le")
    assert _rich_text(value, warnings) == ""
    assert warnings


def test_pdf_comments_apply_document_text_budget_including_author(tmp_path, monkeypatch):
    from dochan.pdf import annotations
    monkeypatch.setattr(annotations, "MAX_COMMENT_TEXT_TOTAL", 10)
    doc = _read(tmp_path, [
        "<< /Subtype /Text /Contents (One) /T (Alice) >>",
        "<< /Subtype /Text /Contents (Two) /T (Bob) >>",
    ])
    assert [(c.author, c.text) for c in doc.find_all("comment")] == [("Alice", "One")]
    assert any("주석" in warning and "한도" in warning for warning in doc.errors)


@pytest.mark.parametrize("subtype", ["FileAttachment", "Sound", "Redact"])
def test_pdf_other_markup_subtypes_keep_comment_contents(tmp_path, subtype):
    doc = _read(tmp_path, ["<< /Subtype /%s /Contents (Review) /T (Alice) >>" % subtype])
    assert [(c.author, c.text) for c in doc.find_all("comment")] == [("Alice", "Review")]


def test_pdf_destination_failure_keeps_page_body(tmp_path, monkeypatch):
    from dochan.pdf import reader
    original = reader.DestinationResolver

    def fail_names(pdf, pages, load_names=True):
        if load_names:
            raise RuntimeError("damaged destination")
        return original(pdf, pages, load_names=False)

    monkeypatch.setattr(reader, "DestinationResolver", fail_names)
    doc = _read(tmp_path, [])
    assert doc.sections[0].elements[0].text == "Body"
    assert any("목적지 해석 실패" in warning for warning in doc.errors)
