import zipfile

import pytest

from dochan.cli import main
from dochan.model.document import Document, Paragraph, Section, TextRun
from dochan.model.image import Image
from dochan.model.table import Cell, Table
from dochan.utils.image_export import export_images

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
EMF = b"\x01\x00\x00\x00" + b"\x00" * 36 + b" EMF" + b"\x00" * 8


def _doc_with_images():
    cell = Cell(paragraphs=[Image(image_data=JPEG)])
    table = Table(rows=[[cell]])
    section = Section(elements=[
        Paragraph(runs=[TextRun(text="본문")]),
        Image(image_data=PNG, image_format="png"),
        table,
        Image(image_data=PNG),            # 같은 바이트 — 한 번만 저장
        Image(image_data=b""),            # 데이터 없는 참조 — 건너뜀
        Image(image_data=EMF, image_format=""),
    ])
    return Document(sections=[section])


def test_export_images_writes_unique_images_in_document_order(tmp_path):
    written = export_images(_doc_with_images(), str(tmp_path / "out"), "보고서")
    names = [p.rsplit("/", 1)[-1] for p in written]
    assert names == ["보고서-image-001.png", "보고서-image-002.jpg", "보고서-image-003.emf"]
    assert (tmp_path / "out" / "보고서-image-001.png").read_bytes() == PNG
    assert (tmp_path / "out" / "보고서-image-002.jpg").read_bytes() == JPEG


def test_export_images_rejects_unsafe_stem(tmp_path):
    written = export_images(_doc_with_images(), str(tmp_path), "../escape")
    assert all(p.startswith(str(tmp_path) + "/") for p in written)
    assert not (tmp_path.parent / "escape-image-001.png").exists()


def test_export_images_refuses_file_as_directory(tmp_path):
    target = tmp_path / "not-a-dir"
    target.write_text("x")
    with pytest.raises(NotADirectoryError):
        export_images(_doc_with_images(), str(target), "doc")


def _docx_with_png(path):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("word/document.xml", """
        <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
          xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
          xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
          <w:body><w:p><w:r><w:drawing><wp:inline>
            <wp:docPr id="1" name="Pic"/>
            <a:graphic><a:graphicData><pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">
              <pic:blipFill><a:blip r:embed="rId1"/></pic:blipFill>
            </pic:pic></a:graphicData></a:graphic>
          </wp:inline></w:drawing></w:r></w:p></w:body>
        </w:document>
        """)
        zf.writestr("word/_rels/document.xml.rels", """
        <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image1.png"/>
        </Relationships>
        """)
        zf.writestr("word/media/image1.png", PNG)


def test_cli_convert_images_dir_saves_embedded_images(tmp_path, capsys):
    source = tmp_path / "sample.docx"
    _docx_with_png(source)
    out_dir = tmp_path / "images"
    assert main(["convert", str(source), "-o", str(tmp_path / "sample.md"),
                 "--images-dir", str(out_dir)]) == 0
    assert (out_dir / "sample-image-001.png").read_bytes() == PNG
    assert "이미지 1개 저장" in capsys.readouterr().err


def test_reader_save_images_api(tmp_path):
    from dochan import Dochan

    source = tmp_path / "sample.docx"
    _docx_with_png(source)
    written = Dochan(str(source)).save_images(str(tmp_path / "imgs"))
    assert [p.rsplit("/", 1)[-1] for p in written] == ["sample-image-001.png"]
