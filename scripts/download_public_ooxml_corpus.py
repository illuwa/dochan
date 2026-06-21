"""Download a small license-audited public OOXML benchmark corpus."""
import argparse
import json
import urllib.request
from pathlib import Path
from typing import Dict, Iterable, List


PUBLIC_OOXML_FIXTURES = [
    {
        "name": "python-docx-test.docx",
        "format": "docx",
        "url": "https://raw.githubusercontent.com/python-openxml/python-docx/master/tests/test_files/test.docx",
        "source": "python-openxml/python-docx",
        "license": "MIT",
        "license_url": "https://github.com/python-openxml/python-docx/blob/master/LICENSE",
    },
    {
        "name": "python-docx-having-images.docx",
        "format": "docx",
        "url": "https://raw.githubusercontent.com/python-openxml/python-docx/master/tests/test_files/having-images.docx",
        "source": "python-openxml/python-docx",
        "license": "MIT",
        "license_url": "https://github.com/python-openxml/python-docx/blob/master/LICENSE",
    },
    {
        "name": "python-docx-blk-inner-content.docx",
        "format": "docx",
        "url": "https://raw.githubusercontent.com/python-openxml/python-docx/master/tests/test_files/blk-inner-content.docx",
        "source": "python-openxml/python-docx",
        "license": "MIT",
        "license_url": "https://github.com/python-openxml/python-docx/blob/master/LICENSE",
    },
    {
        "name": "python-docx-comments-rich-para.docx",
        "format": "docx",
        "url": "https://raw.githubusercontent.com/python-openxml/python-docx/master/features/steps/test_files/comments-rich-para.docx",
        "source": "python-openxml/python-docx",
        "license": "MIT",
        "license_url": "https://github.com/python-openxml/python-docx/blob/master/LICENSE",
    },
    {
        "name": "python-docx-hdr-header-footer.docx",
        "format": "docx",
        "url": "https://raw.githubusercontent.com/python-openxml/python-docx/master/features/steps/test_files/hdr-header-footer.docx",
        "source": "python-openxml/python-docx",
        "license": "MIT",
        "license_url": "https://github.com/python-openxml/python-docx/blob/master/LICENSE",
    },
    {
        "name": "python-docx-num-having-numbering-part.docx",
        "format": "docx",
        "url": "https://raw.githubusercontent.com/python-openxml/python-docx/master/features/steps/test_files/num-having-numbering-part.docx",
        "source": "python-openxml/python-docx",
        "license": "MIT",
        "license_url": "https://github.com/python-openxml/python-docx/blob/master/LICENSE",
    },
    {
        "name": "doxx-comprehensive.docx",
        "format": "docx",
        "url": "https://raw.githubusercontent.com/bgreenwell/doxx/main/tests/fixtures/comprehensive.docx",
        "source": "bgreenwell/doxx",
        "license": "MIT",
        "license_url": "https://github.com/bgreenwell/doxx/blob/main/LICENSE",
    },
    {
        "name": "doxx-images.docx",
        "format": "docx",
        "url": "https://raw.githubusercontent.com/bgreenwell/doxx/main/tests/fixtures/images.docx",
        "source": "bgreenwell/doxx",
        "license": "MIT",
        "license_url": "https://github.com/bgreenwell/doxx/blob/main/LICENSE",
    },
    {
        "name": "apache-poi-sample.docx",
        "format": "docx",
        "url": "https://raw.githubusercontent.com/apache/poi/trunk/test-data/document/SampleDoc.docx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-footnotes.docx",
        "format": "docx",
        "url": "https://raw.githubusercontent.com/apache/poi/trunk/test-data/document/footnotes.docx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-bookmarks.docx",
        "format": "docx",
        "url": "https://raw.githubusercontent.com/apache/poi/trunk/test-data/document/bookmarks.docx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-checkboxes.docx",
        "format": "docx",
        "url": "https://raw.githubusercontent.com/apache/poi/trunk/test-data/document/checkboxes.docx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-deep-table-cell.docx",
        "format": "docx",
        "url": "https://raw.githubusercontent.com/apache/poi/trunk/test-data/document/deep-table-cell.docx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-shapes-with-text.docx",
        "format": "docx",
        "url": "https://raw.githubusercontent.com/apache/poi/trunk/test-data/document/shapes-with-text.docx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-endnotes.docx",
        "format": "docx",
        "url": "https://raw.githubusercontent.com/apache/poi/trunk/test-data/document/endnotes.docx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-heading123.docx",
        "format": "docx",
        "url": "https://raw.githubusercontent.com/apache/poi/trunk/test-data/document/heading123.docx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-header-footer-unicode.docx",
        "format": "docx",
        "url": "https://raw.githubusercontent.com/apache/poi/trunk/test-data/document/HeaderFooterUnicode.docx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-embedded-document.docx",
        "format": "docx",
        "url": "https://raw.githubusercontent.com/apache/poi/trunk/test-data/document/EmbeddedDocument.docx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "python-pptx-test.pptx",
        "format": "pptx",
        "url": "https://raw.githubusercontent.com/scanny/python-pptx/master/tests/test_files/test.pptx",
        "source": "scanny/python-pptx",
        "license": "MIT",
        "license_url": "https://github.com/scanny/python-pptx/blob/master/LICENSE",
    },
    {
        "name": "python-pptx-test-slides.pptx",
        "format": "pptx",
        "url": "https://raw.githubusercontent.com/scanny/python-pptx/master/tests/test_files/test_slides.pptx",
        "source": "scanny/python-pptx",
        "license": "MIT",
        "license_url": "https://github.com/scanny/python-pptx/blob/master/LICENSE",
    },
    {
        "name": "python-pptx-minimal.pptx",
        "format": "pptx",
        "url": "https://raw.githubusercontent.com/scanny/python-pptx/master/tests/test_files/minimal.pptx",
        "source": "scanny/python-pptx",
        "license": "MIT",
        "license_url": "https://github.com/scanny/python-pptx/blob/master/LICENSE",
    },
    {
        "name": "python-pptx-prs-notes.pptx",
        "format": "pptx",
        "url": "https://raw.githubusercontent.com/scanny/python-pptx/master/features/steps/test_files/prs-notes.pptx",
        "source": "scanny/python-pptx",
        "license": "MIT",
        "license_url": "https://github.com/scanny/python-pptx/blob/master/LICENSE",
    },
    {
        "name": "python-pptx-shp-shapes.pptx",
        "format": "pptx",
        "url": "https://raw.githubusercontent.com/scanny/python-pptx/master/features/steps/test_files/shp-shapes.pptx",
        "source": "scanny/python-pptx",
        "license": "MIT",
        "license_url": "https://github.com/scanny/python-pptx/blob/master/LICENSE",
    },
    {
        "name": "python-pptx-shp-picture.pptx",
        "format": "pptx",
        "url": "https://raw.githubusercontent.com/scanny/python-pptx/master/features/steps/test_files/shp-picture.pptx",
        "source": "scanny/python-pptx",
        "license": "MIT",
        "license_url": "https://github.com/scanny/python-pptx/blob/master/LICENSE",
    },
    {
        "name": "python-pptx-cht-charts.pptx",
        "format": "pptx",
        "url": "https://raw.githubusercontent.com/scanny/python-pptx/master/features/steps/test_files/cht-charts.pptx",
        "source": "scanny/python-pptx",
        "license": "MIT",
        "license_url": "https://github.com/scanny/python-pptx/blob/master/LICENSE",
    },
    {
        "name": "python-pptx-tbl-cell.pptx",
        "format": "pptx",
        "url": "https://raw.githubusercontent.com/scanny/python-pptx/master/features/steps/test_files/tbl-cell.pptx",
        "source": "scanny/python-pptx",
        "license": "MIT",
        "license_url": "https://github.com/scanny/python-pptx/blob/master/LICENSE",
    },
    {
        "name": "apache-poi-shapes.pptx",
        "format": "pptx",
        "url": "https://raw.githubusercontent.com/apache/poi/trunk/test-data/slideshow/shapes.pptx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-with-japanese.pptx",
        "format": "pptx",
        "url": "https://raw.githubusercontent.com/apache/poi/trunk/test-data/slideshow/with_japanese.pptx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-bar-chart.pptx",
        "format": "pptx",
        "url": "https://raw.githubusercontent.com/apache/poi/trunk/test-data/slideshow/bar-chart.pptx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-sample.pptx",
        "format": "pptx",
        "url": "https://raw.githubusercontent.com/apache/poi/trunk/test-data/slideshow/sample.pptx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-with-master.pptx",
        "format": "pptx",
        "url": "https://raw.githubusercontent.com/apache/poi/trunk/test-data/slideshow/WithMaster.pptx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-comments.pptx",
        "format": "pptx",
        "url": "https://raw.githubusercontent.com/apache/poi/trunk/test-data/slideshow/45545_Comment.pptx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "pyexcel-bug-176.xlsx",
        "format": "xlsx",
        "url": "https://raw.githubusercontent.com/pyexcel/pyexcel/dev/tests/fixtures/bug_176.xlsx",
        "source": "pyexcel/pyexcel",
        "license": "BSD-3-Clause",
        "license_url": "https://github.com/pyexcel/pyexcel/blob/dev/LICENSE",
    },
    {
        "name": "pyexcel-empty-sheet.xlsx",
        "format": "xlsx",
        "url": "https://raw.githubusercontent.com/pyexcel/pyexcel/dev/tests/fixtures/file_with_an_empty_sheet.xlsx",
        "source": "pyexcel/pyexcel",
        "license": "BSD-3-Clause",
        "license_url": "https://github.com/pyexcel/pyexcel/blob/dev/LICENSE",
    },
    {
        "name": "eparse-nested.xlsx",
        "format": "xlsx",
        "url": "https://raw.githubusercontent.com/ChrisPappalardo/eparse/main/tests/eparse_nested_test_data.xlsx",
        "source": "ChrisPappalardo/eparse",
        "license": "MIT",
        "license_url": "https://github.com/ChrisPappalardo/eparse/blob/main/LICENSE",
    },
    {
        "name": "eparse-unit.xlsx",
        "format": "xlsx",
        "url": "https://raw.githubusercontent.com/ChrisPappalardo/eparse/main/tests/eparse_unit_test_data.xlsx",
        "source": "ChrisPappalardo/eparse",
        "license": "MIT",
        "license_url": "https://github.com/ChrisPappalardo/eparse/blob/main/LICENSE",
    },
    {
        "name": "apache-poi-sample.xlsx",
        "format": "xlsx",
        "url": "https://raw.githubusercontent.com/apache/poi/trunk/test-data/spreadsheet/SampleSS.xlsx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-simple-comments.xlsx",
        "format": "xlsx",
        "url": "https://raw.githubusercontent.com/apache/poi/trunk/test-data/spreadsheet/SimpleWithComments.xlsx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-inline-strings.xlsx",
        "format": "xlsx",
        "url": "https://raw.githubusercontent.com/apache/poi/trunk/test-data/spreadsheet/InlineStrings.xlsx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-sample-strict.xlsx",
        "format": "xlsx",
        "url": "https://raw.githubusercontent.com/apache/poi/trunk/test-data/spreadsheet/SampleSS.strict.xlsx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-shared-hyperlink.xlsx",
        "format": "xlsx",
        "url": "https://raw.githubusercontent.com/apache/poi/trunk/test-data/spreadsheet/sharedhyperlink.xlsx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-header-footer.xlsx",
        "format": "xlsx",
        "url": "https://raw.githubusercontent.com/apache/poi/trunk/test-data/spreadsheet/headerFooterTest.xlsx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-ampersand-header.xlsx",
        "format": "xlsx",
        "url": "https://raw.githubusercontent.com/apache/poi/trunk/test-data/spreadsheet/AmpersandHeader.xlsx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-header-footer-complex.xlsx",
        "format": "xlsx",
        "url": "https://raw.githubusercontent.com/apache/poi/trunk/test-data/spreadsheet/HeaderFooterComplexFormats.xlsx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-simple-strict.xlsx",
        "format": "xlsx",
        "url": "https://raw.githubusercontent.com/apache/poi/trunk/test-data/spreadsheet/SimpleStrict.xlsx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-with-textbox.xlsx",
        "format": "xlsx",
        "url": "https://raw.githubusercontent.com/apache/poi/trunk/test-data/spreadsheet/WithTextBox.xlsx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-with-drawing.xlsx",
        "format": "xlsx",
        "url": "https://raw.githubusercontent.com/apache/poi/trunk/test-data/spreadsheet/WithDrawing.xlsx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-picture.xlsx",
        "format": "xlsx",
        "url": "https://raw.githubusercontent.com/apache/poi/trunk/test-data/spreadsheet/picture.xlsx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-with-chart.xlsx",
        "format": "xlsx",
        "url": "https://raw.githubusercontent.com/apache/poi/trunk/test-data/spreadsheet/WithChart.xlsx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-chart-title-formula.xlsx",
        "format": "xlsx",
        "url": "https://raw.githubusercontent.com/apache/poi/trunk/test-data/spreadsheet/chartTitle_withTitleFormula.xlsx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
]

PUBLIC_OOXML_EXPECTATIONS = {
    "docx/apache-poi-sample.docx": {
        "expected_text": [
            "Author: Nick Burch",
            "I am a test document",
            "This is page 1",
            "This is page two",
            "It’s also in blue",
        ],
        "expected_markdown": [
            "# Test Document",
        ],
    },
    "docx/apache-poi-footnotes.docx": {
        "expected_text": [
            "Author: Anton Trekin",
            "Eto ochen prostoy<sup>[1]</sup> text so snoskoy",
            "snoska",
        ],
        "expected_markdown": [
            "[^각주]: snoska",
        ],
    },
    "docx/apache-poi-bookmarks.docx": {
        "expected_text": [
            "Author: Keith Bennett",
            "Sample Word Document",
        ],
        "expected_markdown": [
            "# Sample Word Document",
            "[bookmark: poi] Sample Word Document",
            "[bookmark: xwpf]",
            "This is a sample Microsoft Word Document",
            "having bookmarks",
        ],
    },
    "docx/apache-poi-checkboxes.docx": {
        "expected_text": [
            "Author: lab",
            "This is a small test for checkboxes",
            "unchecked: [ ]",
            "Or checked:",
            "[x]",
            "In Sequence:",
        ],
        "expected_table_rows": [
            ["[ ]", "[x]"],
        ],
    },
    "docx/apache-poi-deep-table-cell.docx": {
        "expected_text": [
            "Nested level 0",
            "Nested level 31",
        ],
        "expected_markdown": [
            "[nested table omitted: depth limit exceeded]",
        ],
    },
    "docx/apache-poi-shapes-with-text.docx": {
        "expected_text": [
            "Author: Perez, Jacobo",
            "Floating text box",
            "A square shape with text inside",
            "An ellipse with text inside",
            "A group of shapes",
            "Where some contain text",
        ],
        "expected_markdown": [
            "Floating text box\nA square shape with text inside\nAn ellipse with text inside\nA group of shapes\nWhere some contain text",
        ],
    },
    "docx/apache-poi-endnotes.docx": {
        "expected_text": [
            "Author: pavel",
            "A Nepalese name for Tilaka",
            "A pendant worn in place of the red spot (tilaka <sup>[1]</sup>or 'tika')",
            "Apache Tika is a subproject of the Lucene",
        ],
        "expected_markdown": [
            "[^미주]: XXX",
        ],
    },
    "docx/apache-poi-heading123.docx": {
        "expected_text": [
            "Author: Paolo Mottadelli",
            "FffLorem ipsum dolor sit amet",
            "FfPellentesque tristique scelerisque libero ut sagittis",
        ],
        "expected_markdown": [
            "# First paragraph",
            "## Second paragraph",
            "### Third paragraph",
        ],
    },
    "docx/apache-poi-header-footer-unicode.docx": {
        "expected_text": [
            "This is a simple header, with a € euro symbol in it.",
            "This is a fairly simple word document, over two pages, with headers and footers.",
            "GBP - £",
            "EUR - €",
            "L'Avare ou l'École du mensonge",
            "The footer, with Molière, has Unicode in it.",
        ],
        "expected_markdown": [
            "# \tMolière",
            "<!-- header: This is a simple header, with a € euro symbol in it. -->",
            "<!-- footer: The footer, with Molière, has Unicode in it. -->",
        ],
    },
    "docx/apache-poi-embedded-document.docx": {
        "expected_text": [
            "Author: win user",
            "Let me see what happens if I insert a worksheet.",
        ],
        "expected_markdown": [
            "![image](word/media/image1.emf)",
        ],
        "expected_assets": [
            "word/embeddings/Microsoft_Office_Excel_97-2003_Worksheet1.xls",
            "word/media/image1.emf",
        ],
    },
    "docx/doxx-comprehensive.docx": {
        "expected_text": [
            "Comprehensive Test Document",
            "Normal paragraph with no special formatting.",
            "Q4 revenue figure was the strongest quarter.",
            "Chinese: 你好世界",
            "Math symbols: ∑ ∫ ∞ π",
        ],
        "expected_markdown": [
            "# Comprehensive Test Document",
            "## Heading Level Two",
            "###### Heading Level Six",
            "1. First step",
        ],
        "expected_tables": [
            [
                ["Product", "Quantity", "Price"],
                ["Widget A", "10", "$5.00"],
                ["Widget B", "20", "$3.50"],
                ["Widget C", "5", "$12.00"],
            ]
        ],
    },
    "docx/python-docx-comments-rich-para.docx": {
        "expected_text": [
            "Document text",
            "Some text worthy of note. [comment 1: Text with hyperlink https://google.com embedded.]",
            "Other text worthy of note. [comment 2: Text with inline image  in the middle.]",
            "Paragraph 5 [comment 3: Text with character style.]",
        ],
    },
    "docx/python-docx-blk-inner-content.docx": {
        "expected_text": [
            "P1",
            "P3",
        ],
        "expected_table_rows": [
            ["T2", ""],
            ["", ""],
        ],
    },
    "docx/python-docx-having-images.docx": {
        "expected_markdown": [
            "Author: Steve Canny",
            "![Picture 1](word/media/image1.png)",
            "![Picture 5](word/media/image3.png)",
        ],
    },
    "docx/python-docx-hdr-header-footer.docx": {
        "expected_text": [
            "section with header",
            "section without header of its own.",
        ],
        "expected_markdown": [
            "<!-- header: Header for section-1 -->",
            "<!-- footer: Footer for section 1 -->",
        ],
    },
    "docx/python-docx-num-having-numbering-part.docx": {
        "expected_text": [
            "Author: Steve Canny",
            "Paragraph having List Number style.",
        ],
    },
    "docx/python-docx-test.docx": {
        "expected_text": [
            "Author: Cisco Employee",
            "python-docx was here too!",
        ],
        "expected_markdown": [
            "# python-docx was here!",
        ],
    },
    "docx/doxx-images.docx": {
        "expected_text": [
            "Author: Brandon Greenwell",
            "Sample document with images",
            "Photo of boulders on beach in bright sunshine",
            "Milky way galaxy, under mostly clear night skies",
            "Abacus with solid fill",
        ],
        "expected_markdown": [
            "# Heading 1",
            "![Photo of boulders on beach in bright sunshine Picture 2](word/media/image1.jpg)",
            "![Milky way galaxy, under mostly clear night skies Picture 5](word/media/image2.jpeg)",
            "![Abacus with solid fill Graphic 4](word/media/image3.png)",
        ],
    },
    "pptx/python-pptx-test.pptx": {
        "expected_text": [
            "Presentation Title Text",
            "Subtitle Text",
        ],
    },
    "pptx/python-pptx-minimal.pptx": {
        "expected_markdown": [
            "# Presentation",
            "Author: python-pptx",
        ],
    },
    "pptx/python-pptx-prs-notes.pptx": {
        "expected_text": [
            "Notes",
            "1",
        ],
    },
    "pptx/python-pptx-test-slides.pptx": {
        "expected_text": [
            "Test text",
            "Box 1",
            "Box 2",
            "Group test text",
        ],
        "expected_markdown": [
            "![python-logo.gif Picture 5](ppt/media/image1.gif)",
            "![python-icon.jpeg Picture 8](ppt/media/image2.jpeg)",
        ],
        "expected_table_rows": [
            ["Col head 1", "Col head 2"],
            ["Cell text 1", "Cell text 2"],
        ],
    },
    "pptx/apache-poi-shapes.pptx": {
        "expected_text": [
            "Learning PPTX",
            "Hyperlinks",
        ],
        "expected_markdown": [
            "## Slide 1",
            "# PPTX <u>Title</u>",
            "![Picture 1](ppt/media/image1.jpg)",
            "Web Page <http://poi.apache.org/>",
            "Email <mailto:dev@poi.apache.org?subject=Hi%20There>",
        ],
        "expected_table_rows": [
            ["Column1", "Column2", "Column3"],
            ["data1", "data2", "data3"],
            ["A1", "B1", "C1"],
            ["Link Type", "Target URI"],
        ],
    },
    "pptx/apache-poi-with-japanese.pptx": {
        "expected_text": [
            "This is a hyperlink <http://tika.apache.org/>",
            "ゾルゲと尾崎、淡々と最期",
            "𐌲𐌿𐍄𐌹𐍃𐌺",
            "This is a footnote.",
            "Here is a text box",
        ],
        "expected_markdown": [
            "**Bold** *italic* <u>underline</u> superscript subscript",
        ],
        "expected_table_rows": [
            ["Row 1 Col 1", "Row 1 Col 2", "Row 1 Col 3"],
            ["Row 2 Col 1", "Row 2 Col 2", "Row 2 Col 3"],
        ],
    },
    "pptx/apache-poi-bar-chart.pptx": {
        "expected_markdown": [
            "# My Bar Chart",
        ],
        "expected_table_rows": [
            ["Category", "Sales"],
            ["1st Qtr", "8.200000000000001"],
            ["2nd Qtr", "3.2"],
            ["4th Qtr", "1.2"],
        ],
    },
    "pptx/apache-poi-sample.pptx": {
        "expected_text": [
            "Nunc at risus vel erat tempus posuere. Aenean non ante.",
            "Lorem",
            "ipsum",
            "dolor",
            "sit",
            "amet",
        ],
        "expected_markdown": [
            "# Lorem ipsum dolor sit amet",
            "## Slide 1",
            "## Slide 2",
        ],
    },
    "pptx/apache-poi-with-master.pptx": {
        "expected_text": [
            "This text comes from the Master Slide",
            "First page title",
            "First page subtitle",
            "2nd page subtitle",
            "Footer from the master slide",
        ],
        "expected_markdown": [
            "# First page title",
            "## Slide 1",
            "## Slide 2",
        ],
    },
    "pptx/apache-poi-comments.pptx": {
        "expected_text": [
            "Water Finance",
            "Outline of the presentation",
            "[comment: XPVMWARE01: testdoc]",
            "[comment: XPVMWARE01: test phrase]",
        ],
    },
    "pptx/python-pptx-shp-picture.pptx": {
        "expected_markdown": [
            "## Slide 1",
            "## Slide 2",
            "![python-powered.png Picture 2](ppt/media/image1.png)",
            "![Picture 3](ppt/media/image2.png)",
        ],
    },
    "pptx/python-pptx-cht-charts.pptx": {
        "expected_table_rows": [
            ["Category", "Series 1", "Series 2", "Series 3"],
            ["Category 1", "4.3", "2.4", "2.0"],
            ["Category 2", "2.5", "4.4", "2.0"],
            ["Category 4", "4.5", "2.8", "5.0"],
        ],
    },
    "pptx/python-pptx-shp-shapes.pptx": {
        "expected_markdown": [
            "## Slide 1",
            "## Slide 2",
            "![python-powered.png Picture 5](ppt/media/image1.png)",
            "![sonic.gif Picture 7](ppt/media/image2.gif)",
        ],
        "expected_table_rows": [
            ["Category", "Sales"],
            ["1st Qtr", "8.2"],
            ["4th Qtr", "1.2"],
        ],
    },
    "pptx/python-pptx-tbl-cell.pptx": {
        "expected_markdown": [
            "## Slide 1",
            "## Slide 2",
            "## Slide 3",
        ],
        "expected_table_rows": [
            ["having custom margins", "vert anchor is inherited", "vert anchor is top", "vert anchor is bottom"],
            ["merged cell", "", ""],
            ["merged cell", "", "", "", ""],
            ["a", "b", "c"],
            ["d", "e", "f"],
            ["g", "h", "i"],
        ],
    },
    "xlsx/eparse-nested.xlsx": {
        "expected_table_rows": [
            ["", "", "", "ID", "Name", "Category", "Value", "Status", "Date", "Notes", "Extra", "More"],
            ["", "", "", "ID001", "Item 1", "Category A", "100", "Active", "2024-01-01", "Note 1", "Extra 1", "More 1"],
            ["", "", "", "ID008", "Item 8", "", "", "SubID", "SubVal", "SubCat", "", ""],
            ["", "", "", "ID010", "Item 10", "", "", "S2", "100", "Type2", "", ""],
            ["", "", "", "ID025", "Item 25", "Category A", "2500", "Active", "2024-01-25", "Note 25", "Extra 25", "More 25"],
        ],
    },
    "xlsx/apache-poi-sample.xlsx": {
        "expected_markdown": [
            "## First Sheet",
            "## Sheet Number 2",
            "## Sheet3",
        ],
        "expected_table_rows": [
            ["Test spreadsheet", ""],
            ["2nd row", "2nd row 2nd column"],
            ["This one is red", ""],
            ["Start of 2nd sheet", "", "", ""],
            ["1", "10", "2", "13 (=SUM(A7:C7))"],
        ],
    },
    "xlsx/apache-poi-simple-comments.xlsx": {
        "expected_markdown": [
            "## Sheet1",
            "## Sheet2",
            "## Sheet3",
        ],
        "expected_table_rows": [
            ["1", "one [comment: Yegor Kozlov: Yegor Kozlov: first cell]"],
            ["2", "two [comment: Yegor Kozlov: Yegor Kozlov: second cell]"],
            ["3", "three [comment: Yegor Kozlov: Yegor Kozlov: third cell]"],
        ],
    },
    "xlsx/apache-poi-inline-strings.xlsx": {
        "expected_markdown": [
            "## Sheet1",
            "## Sheet2",
            "## Sheet3",
        ],
        "expected_table_rows": [
            ["Numbers", "Strings", "Inline Strings", "Formulas"],
            ["12", "A", "1st Inline String", "12 (=A2)"],
            ["32", "B", "2nd Inline String", "44 (=A3+A2)"],
            ["21", "Longer Text", "The End", "9 (=A7-A$2)"],
        ],
    },
    "xlsx/apache-poi-sample-strict.xlsx": {
        "expected_markdown": [
            "## First Sheet",
            "## Sheet Number 2",
            "## Sheet3",
        ],
        "expected_table_rows": [
            ["Test spreadsheet", ""],
            ["2nd row", "2nd row 2nd column"],
            ["This one is red", ""],
            ["Start of 2nd sheet", "", "", ""],
            ["1", "10", "2", "13 (=SUM(A7:C7))"],
        ],
    },
    "xlsx/apache-poi-header-footer.xlsx": {
        "expected_markdown": [
            "<!-- header: top left | top center | top right -->",
            "<!-- footer: bottom left | bottom center | bottom right -->",
        ],
        "expected_table_rows": [
            ["abc", "123"],
        ],
    },
    "xlsx/apache-poi-ampersand-header.xlsx": {
        "expected_markdown": [
            "Author: Viru Gajanayake",
            "<!-- header: one & two && -->",
        ],
    },
    "xlsx/apache-poi-header-footer-complex.xlsx": {
        "expected_markdown": [
            "<!-- header: Header Bold RedUnderlined Bolditalics -->",
            "<!-- footer: Footer ArialBlue TahomaBoldGreen -->",
        ],
    },
    "xlsx/apache-poi-shared-hyperlink.xlsx": {
        "expected_markdown": [
            "http://www.apache.org <http://www.apache.org/>",
        ],
        "expected_table_rows": [
            ["http://www.apache.org <http://www.apache.org/>"],
        ],
    },
    "xlsx/apache-poi-simple-strict.xlsx": {
        "expected_markdown": [
            "## Sheet1",
            "## Sheet Number 2",
        ],
        "expected_table_rows": [
            ["test", "", "1"],
            ["test 2", "", "2"],
            ["This is sheet 2", "", "", "", "", ""],
            ["1", "2", "3", "4", "5", "6"],
            ["10 (=SUM(A3:D3))", "", "3 (=C3)", "", "", ""],
        ],
    },
    "xlsx/apache-poi-with-textbox.xlsx": {
        "expected_markdown": [
            "## Sheet1",
            "Line 1\nLine 2\nLine 3",
        ],
    },
    "xlsx/apache-poi-with-drawing.xlsx": {
        "expected_markdown": [
            "## Sheet1",
            "![clock.jpg Picture 1](xl/media/image1.jpeg)",
            "![cow.pict Picture 2](xl/media/image2.emf)",
            "![tomcat.png Picture 4](xl/media/image3.png)",
            "![santa.wmf Picture 7](xl/media/image5.wmf)",
            "![wrench.emf Picture 6](xl/media/image4.emf)",
            "Sheet with various pictures\n(jpeg, png, wmf, emf and pict)",
        ],
    },
    "xlsx/apache-poi-picture.xlsx": {
        "expected_markdown": [
            "## Sheet1",
            "![Graphics 1 Graphics 1](xl/media/10000000000006450000032120C875D8.jpg)",
        ],
        "expected_table_rows": [
            ["Lorem", "111"],
            ["at", "4995"],
        ],
    },
    "xlsx/apache-poi-with-chart.xlsx": {
        "expected_markdown": [
            "## Sheet2",
        ],
        "expected_table_rows": [
            ["Category", "1st Column", "2nd Column"],
            ["4", "5", "15"],
            ["5", "6", "17"],
        ],
    },
    "xlsx/apache-poi-chart-title-formula.xlsx": {
        "expected_markdown": [
            "### Formula Title from Excel 2016",
        ],
        "expected_table_rows": [
            ["1", "7.2"],
            ["5", "3.1"],
        ],
    },
    "xlsx/pyexcel-bug-176.xlsx": {
        "expected_markdown": [
            "## ag data",
            "## aph data",
            "## ad data",
        ],
        "expected_table_rows": [
            ["GLOBAL ATTRIBUTES", "", "Comments", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
            ["title", "Coffs Harbour", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
            ["project", "Integrated Marine Observing System (IMOS)", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
            ["Row name", "CF standard_name", "IMOS long_name", "Units", "Fill value", "Comments", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
            ["Time", "time", "analysis_time", "YYYY-MM-DDThh:mm:ssZ", "", "UTC date and time", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
        ],
    },
    "xlsx/eparse-unit.xlsx": {
        "expected_table_rows": [
            ["", "", "Field1", "ABC Co.", "", "ABC Co.", "", "ABC Co.", "", "ABC Co.", ""],
            ["", "General Information", "Business Description", "ABC Company, Inc. was founded in 1950 and manufactures As, Bs, and Cs.", "", "ABC Company, Inc. was founded in 1950 and manufactures As, Bs, and Cs.", "", "ABC Company, Inc. was founded in 1950 and manufactures As, Bs, and Cs.", "", "ABC Company, Inc. was founded in 1950 and manufactures As, Bs, and Cs.", ""],
            ["", "", "Current Business Update", "ABCs are flying off the shelf.", "", "ABCs are flying off the shelf.", "", "ABCs are flying off the shelf.", "", "ABCs are flying off the shelf.", ""],
            ["", "", "Business Conclusions", "", "", "", "", "", "", "ABC Company is doing well.", ""],
            ["", "Financials", "Revenue", "809127967.91789377", "964987674.26480222", "354635194.54920423", "644839345.4671768", "297294601.68441468", "808624104.77259195", "22288256.012496509", "576767887.49204695"],
            ["", "", "EBITDA", "847831.96449385432", "545877.15070734732", "943836.91573895374", "797576.93518698367", "275173.55369749339", "775792.89556771098", "636593.29909355869", "506771.70771095669"],
            ["", "General", "Include", "No", "", "No", "", "No", "", "Yes", ""],
        ],
    },
    "xlsx/pyexcel-empty-sheet.xlsx": {
        "expected_markdown": [
            "## Sheet1",
            "## Sheet2",
            "## Sheet3",
        ],
        "expected_table_rows": [
            ["1", "2", "3"],
            ["4", "5", "6"],
            ["7", "8", "9"],
            ["10", "11", "12"],
        ],
    },
}

APACHE_POI_PROBE_MANIFEST_VERSION = 1


def selected_fixtures(formats: Iterable[str], fixtures: Iterable[dict] = None) -> List[dict]:
    fixtures = list(fixtures or PUBLIC_OOXML_FIXTURES)
    requested = {fmt.lower().lstrip(".") for fmt in formats}
    return [fixture for fixture in fixtures if fixture["format"] in requested]


def load_fixture_index(path: Path) -> List[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    fixtures = payload.get("fixtures", payload) if isinstance(payload, dict) else payload
    if not isinstance(fixtures, list):
        raise ValueError("fixture index must be a JSON list or an object with a 'fixtures' list")
    return [dict(fixture) for fixture in fixtures]


def empty_apache_poi_probe_manifest() -> dict:
    return {
        "version": APACHE_POI_PROBE_MANIFEST_VERSION,
        "used": {},
        "probes": [],
    }


def load_apache_poi_probe_manifest(path: Path) -> dict:
    if not path.exists():
        return empty_apache_poi_probe_manifest()
    payload = json.loads(path.read_text(encoding="utf-8"))
    manifest = empty_apache_poi_probe_manifest()
    manifest["version"] = payload.get("version", APACHE_POI_PROBE_MANIFEST_VERSION)
    manifest["used"] = {
        str(file_format).lower().lstrip("."): sorted({str(item) for item in fixture_ids})
        for file_format, fixture_ids in payload.get("used", {}).items()
    }
    manifest["probes"] = list(payload.get("probes", []))
    return manifest


def apache_poi_fixture_id(fixture: dict) -> str:
    if fixture.get("source_name"):
        return str(fixture["source_name"])
    if fixture.get("url"):
        return str(fixture["url"]).rstrip("/").rsplit("/", 1)[-1]
    if fixture.get("path"):
        return Path(str(fixture["path"])).name
    return str(fixture["name"])


def select_unseen_apache_poi_fixtures(
    candidates: Iterable[dict],
    formats: Iterable[str],
    per_format: int,
    manifest: dict = None,
) -> List[dict]:
    manifest = manifest or empty_apache_poi_probe_manifest()
    requested = [fmt.lower().lstrip(".") for fmt in formats]
    used_by_format = {
        file_format: set(fixture_ids)
        for file_format, fixture_ids in manifest.get("used", {}).items()
    }
    selected = []
    counts: Dict[str, int] = {file_format: 0 for file_format in requested}

    for fixture in sorted(candidates, key=lambda item: (item.get("format", ""), apache_poi_fixture_id(item))):
        file_format = str(fixture.get("format", "")).lower().lstrip(".")
        if file_format not in counts or counts[file_format] >= per_format:
            continue
        fixture_id = apache_poi_fixture_id(fixture)
        if fixture_id in used_by_format.get(file_format, set()):
            continue
        selected.append(fixture)
        counts[file_format] += 1
    return selected


def record_apache_poi_probe_manifest(path: Path, records: List[dict], probe_name: str) -> dict:
    manifest = load_apache_poi_probe_manifest(path)
    used = {
        file_format: set(fixture_ids)
        for file_format, fixture_ids in manifest.get("used", {}).items()
    }
    probe_files = []

    for record in records:
        file_format = str(record.get("format", "")).lower().lstrip(".")
        fixture_id = apache_poi_fixture_id(record)
        if not file_format or not fixture_id:
            continue
        used.setdefault(file_format, set()).add(fixture_id)
        probe_files.append({
            "format": file_format,
            "id": fixture_id,
            "path": record.get("path", ""),
        })

    manifest["used"] = {
        file_format: sorted(fixture_ids)
        for file_format, fixture_ids in sorted(used.items())
    }
    manifest["probes"].append({
        "name": probe_name,
        "files": sorted(probe_files, key=lambda item: (item["format"], item["id"])),
    })
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def download_fixture(fixture: dict, output_dir: Path) -> dict:
    format_dir = output_dir / fixture["format"]
    format_dir.mkdir(parents=True, exist_ok=True)
    destination = format_dir / fixture["name"]
    urllib.request.urlretrieve(fixture["url"], destination)
    record = dict(fixture)
    record["path"] = destination.relative_to(output_dir).as_posix()
    record["bytes"] = destination.stat().st_size
    return record


def write_sources(output_dir: Path, records: List[dict]) -> None:
    (output_dir / "SOURCES.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Public OOXML Corpus Sources",
        "",
        "| File | Format | Source | License | URL |",
        "| --- | --- | --- | --- | --- |",
    ]
    for record in records:
        lines.append(
            "| {path} | {format} | {source} | {license} | {url} |".format(
                path=record["path"],
                format=record["format"],
                source=record["source"],
                license=record["license"],
                url=record["url"],
            )
        )
    lines.append("")
    (output_dir / "SOURCES.md").write_text("\n".join(lines), encoding="utf-8")


def write_expected_manifest(output_dir: Path, records: List[dict]) -> None:
    expected = {
        record["path"]: PUBLIC_OOXML_EXPECTATIONS[record["path"]]
        for record in records
        if record.get("path") in PUBLIC_OOXML_EXPECTATIONS
    }
    if expected:
        (output_dir / "expected.json").write_text(json.dumps(expected, ensure_ascii=False, indent=2), encoding="utf-8")


def download_corpus(
    output_dir: Path,
    formats: Iterable[str],
    fixtures: Iterable[dict] = None,
    probe_manifest_path: Path = None,
    probe_name: str = "",
    probe_per_format: int = 0,
) -> List[dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates = selected_fixtures(formats, fixtures)
    if probe_manifest_path:
        manifest = load_apache_poi_probe_manifest(probe_manifest_path)
        if probe_per_format <= 0:
            raise ValueError("--probe-per-format must be positive when --probe-manifest is used")
        candidates = select_unseen_apache_poi_fixtures(candidates, formats, probe_per_format, manifest)

    records = [download_fixture(fixture, output_dir) for fixture in candidates]
    write_sources(output_dir, records)
    write_expected_manifest(output_dir, records)
    if probe_manifest_path:
        record_apache_poi_probe_manifest(probe_manifest_path, records, probe_name or output_dir.name)
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description="Download a small public OOXML corpus with source metadata.")
    parser.add_argument("output_dir", type=Path, help="Directory to write corpus files")
    parser.add_argument("--formats", default="docx,pptx,xlsx", help="Comma-separated extensions")
    parser.add_argument(
        "--fixture-index",
        type=Path,
        help="Optional JSON list of fixture records to use instead of the built-in public corpus",
    )
    parser.add_argument(
        "--probe-manifest",
        type=Path,
        help="Optional JSON manifest that records Apache POI probe fixture ids across runs",
    )
    parser.add_argument(
        "--probe-name",
        default="",
        help="Name to record for this probe in --probe-manifest",
    )
    parser.add_argument(
        "--probe-per-format",
        type=int,
        default=0,
        help="Number of unseen fixtures to select per requested format when --probe-manifest is used",
    )
    args = parser.parse_args()

    formats = [item.strip() for item in args.formats.split(",") if item.strip()]
    fixtures = load_fixture_index(args.fixture_index) if args.fixture_index else None
    records = download_corpus(
        args.output_dir,
        formats,
        fixtures=fixtures,
        probe_manifest_path=args.probe_manifest,
        probe_name=args.probe_name,
        probe_per_format=args.probe_per_format,
    )
    print(json.dumps({"output_dir": str(args.output_dir), "files": records}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
