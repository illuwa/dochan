"""Download a small license-audited public OOXML benchmark corpus."""
import argparse
import hashlib
import json
import os
import secrets
import stat
import time
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Dict, Iterable, List


ALLOWED_OOXML_FORMATS = frozenset({"docx", "pptx", "xlsx"})
DOWNLOAD_TIMEOUT_SECONDS = 30.0
MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024
DOWNLOAD_CHUNK_BYTES = 64 * 1024


PUBLIC_OOXML_FIXTURES = [
    {
        "name": "python-docx-test.docx",
        "format": "docx",
        "url": "https://raw.githubusercontent.com/python-openxml/python-docx/e45454602b53e8e572b179ccf1c91093ec9f4ed7/tests/test_files/test.docx",
        "source": "python-openxml/python-docx",
        "license": "MIT",
        "license_url": "https://github.com/python-openxml/python-docx/blob/e45454602b53e8e572b179ccf1c91093ec9f4ed7/LICENSE",
    },
    {
        "name": "python-docx-having-images.docx",
        "format": "docx",
        "url": "https://raw.githubusercontent.com/python-openxml/python-docx/e45454602b53e8e572b179ccf1c91093ec9f4ed7/tests/test_files/having-images.docx",
        "source": "python-openxml/python-docx",
        "license": "MIT",
        "license_url": "https://github.com/python-openxml/python-docx/blob/e45454602b53e8e572b179ccf1c91093ec9f4ed7/LICENSE",
    },
    {
        "name": "python-docx-blk-inner-content.docx",
        "format": "docx",
        "url": "https://raw.githubusercontent.com/python-openxml/python-docx/e45454602b53e8e572b179ccf1c91093ec9f4ed7/tests/test_files/blk-inner-content.docx",
        "source": "python-openxml/python-docx",
        "license": "MIT",
        "license_url": "https://github.com/python-openxml/python-docx/blob/e45454602b53e8e572b179ccf1c91093ec9f4ed7/LICENSE",
    },
    {
        "name": "python-docx-comments-rich-para.docx",
        "format": "docx",
        "url": "https://raw.githubusercontent.com/python-openxml/python-docx/e45454602b53e8e572b179ccf1c91093ec9f4ed7/features/steps/test_files/comments-rich-para.docx",
        "source": "python-openxml/python-docx",
        "license": "MIT",
        "license_url": "https://github.com/python-openxml/python-docx/blob/e45454602b53e8e572b179ccf1c91093ec9f4ed7/LICENSE",
    },
    {
        "name": "python-docx-hdr-header-footer.docx",
        "format": "docx",
        "url": "https://raw.githubusercontent.com/python-openxml/python-docx/e45454602b53e8e572b179ccf1c91093ec9f4ed7/features/steps/test_files/hdr-header-footer.docx",
        "source": "python-openxml/python-docx",
        "license": "MIT",
        "license_url": "https://github.com/python-openxml/python-docx/blob/e45454602b53e8e572b179ccf1c91093ec9f4ed7/LICENSE",
    },
    {
        "name": "python-docx-num-having-numbering-part.docx",
        "format": "docx",
        "url": "https://raw.githubusercontent.com/python-openxml/python-docx/e45454602b53e8e572b179ccf1c91093ec9f4ed7/features/steps/test_files/num-having-numbering-part.docx",
        "source": "python-openxml/python-docx",
        "license": "MIT",
        "license_url": "https://github.com/python-openxml/python-docx/blob/e45454602b53e8e572b179ccf1c91093ec9f4ed7/LICENSE",
    },
    {
        "name": "doxx-comprehensive.docx",
        "format": "docx",
        "url": "https://raw.githubusercontent.com/bgreenwell/doxx/51c9bc40c0a178abe51377cf692293b1723c63b7/tests/fixtures/comprehensive.docx",
        "source": "bgreenwell/doxx",
        "license": "MIT",
        "license_url": "https://github.com/bgreenwell/doxx/blob/51c9bc40c0a178abe51377cf692293b1723c63b7/LICENSE",
    },
    {
        "name": "doxx-images.docx",
        "format": "docx",
        "url": "https://raw.githubusercontent.com/bgreenwell/doxx/51c9bc40c0a178abe51377cf692293b1723c63b7/tests/fixtures/images.docx",
        "source": "bgreenwell/doxx",
        "license": "MIT",
        "license_url": "https://github.com/bgreenwell/doxx/blob/51c9bc40c0a178abe51377cf692293b1723c63b7/LICENSE",
    },
    {
        "name": "apache-poi-sample.docx",
        "format": "docx",
        "url": "https://raw.githubusercontent.com/apache/poi/379bcdcc4cfe9d899eabc2e226a1322161413c7f/test-data/document/SampleDoc.docx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-footnotes.docx",
        "format": "docx",
        "url": "https://raw.githubusercontent.com/apache/poi/379bcdcc4cfe9d899eabc2e226a1322161413c7f/test-data/document/footnotes.docx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-bookmarks.docx",
        "format": "docx",
        "url": "https://raw.githubusercontent.com/apache/poi/379bcdcc4cfe9d899eabc2e226a1322161413c7f/test-data/document/bookmarks.docx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-checkboxes.docx",
        "format": "docx",
        "url": "https://raw.githubusercontent.com/apache/poi/379bcdcc4cfe9d899eabc2e226a1322161413c7f/test-data/document/checkboxes.docx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-deep-table-cell.docx",
        "format": "docx",
        "url": "https://raw.githubusercontent.com/apache/poi/379bcdcc4cfe9d899eabc2e226a1322161413c7f/test-data/document/deep-table-cell.docx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-shapes-with-text.docx",
        "format": "docx",
        "url": "https://raw.githubusercontent.com/apache/poi/379bcdcc4cfe9d899eabc2e226a1322161413c7f/test-data/document/shapes-with-text.docx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-endnotes.docx",
        "format": "docx",
        "url": "https://raw.githubusercontent.com/apache/poi/379bcdcc4cfe9d899eabc2e226a1322161413c7f/test-data/document/endnotes.docx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-heading123.docx",
        "format": "docx",
        "url": "https://raw.githubusercontent.com/apache/poi/379bcdcc4cfe9d899eabc2e226a1322161413c7f/test-data/document/heading123.docx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-header-footer-unicode.docx",
        "format": "docx",
        "url": "https://raw.githubusercontent.com/apache/poi/379bcdcc4cfe9d899eabc2e226a1322161413c7f/test-data/document/HeaderFooterUnicode.docx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-embedded-document.docx",
        "format": "docx",
        "url": "https://raw.githubusercontent.com/apache/poi/379bcdcc4cfe9d899eabc2e226a1322161413c7f/test-data/document/EmbeddedDocument.docx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "python-pptx-test.pptx",
        "format": "pptx",
        "url": "https://raw.githubusercontent.com/scanny/python-pptx/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/tests/test_files/test.pptx",
        "source": "scanny/python-pptx",
        "license": "MIT",
        "license_url": "https://github.com/scanny/python-pptx/blob/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/LICENSE",
    },
    {
        "name": "python-pptx-test-slides.pptx",
        "format": "pptx",
        "url": "https://raw.githubusercontent.com/scanny/python-pptx/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/tests/test_files/test_slides.pptx",
        "source": "scanny/python-pptx",
        "license": "MIT",
        "license_url": "https://github.com/scanny/python-pptx/blob/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/LICENSE",
    },
    {
        "name": "python-pptx-minimal.pptx",
        "format": "pptx",
        "url": "https://raw.githubusercontent.com/scanny/python-pptx/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/tests/test_files/minimal.pptx",
        "source": "scanny/python-pptx",
        "license": "MIT",
        "license_url": "https://github.com/scanny/python-pptx/blob/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/LICENSE",
    },
    {
        "name": "python-pptx-prs-notes.pptx",
        "format": "pptx",
        "url": "https://raw.githubusercontent.com/scanny/python-pptx/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/features/steps/test_files/prs-notes.pptx",
        "source": "scanny/python-pptx",
        "license": "MIT",
        "license_url": "https://github.com/scanny/python-pptx/blob/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/LICENSE",
    },
    {
        "name": "python-pptx-shp-shapes.pptx",
        "format": "pptx",
        "url": "https://raw.githubusercontent.com/scanny/python-pptx/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/features/steps/test_files/shp-shapes.pptx",
        "source": "scanny/python-pptx",
        "license": "MIT",
        "license_url": "https://github.com/scanny/python-pptx/blob/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/LICENSE",
    },
    {
        "name": "python-pptx-shp-picture.pptx",
        "format": "pptx",
        "url": "https://raw.githubusercontent.com/scanny/python-pptx/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/features/steps/test_files/shp-picture.pptx",
        "source": "scanny/python-pptx",
        "license": "MIT",
        "license_url": "https://github.com/scanny/python-pptx/blob/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/LICENSE",
    },
    {
        "name": "python-pptx-cht-charts.pptx",
        "format": "pptx",
        "url": "https://raw.githubusercontent.com/scanny/python-pptx/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/features/steps/test_files/cht-charts.pptx",
        "source": "scanny/python-pptx",
        "license": "MIT",
        "license_url": "https://github.com/scanny/python-pptx/blob/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/LICENSE",
    },
    {
        "name": "python-pptx-tbl-cell.pptx",
        "format": "pptx",
        "url": "https://raw.githubusercontent.com/scanny/python-pptx/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/features/steps/test_files/tbl-cell.pptx",
        "source": "scanny/python-pptx",
        "license": "MIT",
        "license_url": "https://github.com/scanny/python-pptx/blob/278b47b1dedd5b46ee84c286e77cdfb0bf4594be/LICENSE",
    },
    {
        "name": "apache-poi-shapes.pptx",
        "format": "pptx",
        "url": "https://raw.githubusercontent.com/apache/poi/379bcdcc4cfe9d899eabc2e226a1322161413c7f/test-data/slideshow/shapes.pptx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-with-japanese.pptx",
        "format": "pptx",
        "url": "https://raw.githubusercontent.com/apache/poi/379bcdcc4cfe9d899eabc2e226a1322161413c7f/test-data/slideshow/with_japanese.pptx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-bar-chart.pptx",
        "format": "pptx",
        "url": "https://raw.githubusercontent.com/apache/poi/379bcdcc4cfe9d899eabc2e226a1322161413c7f/test-data/slideshow/bar-chart.pptx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-sample.pptx",
        "format": "pptx",
        "url": "https://raw.githubusercontent.com/apache/poi/379bcdcc4cfe9d899eabc2e226a1322161413c7f/test-data/slideshow/sample.pptx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-with-master.pptx",
        "format": "pptx",
        "url": "https://raw.githubusercontent.com/apache/poi/379bcdcc4cfe9d899eabc2e226a1322161413c7f/test-data/slideshow/WithMaster.pptx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-comments.pptx",
        "format": "pptx",
        "url": "https://raw.githubusercontent.com/apache/poi/379bcdcc4cfe9d899eabc2e226a1322161413c7f/test-data/slideshow/45545_Comment.pptx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "pyexcel-bug-176.xlsx",
        "format": "xlsx",
        "url": "https://raw.githubusercontent.com/pyexcel/pyexcel/0bfeee32704678a9da498d62b5c55dc8d474853e/tests/fixtures/bug_176.xlsx",
        "source": "pyexcel/pyexcel",
        "license": "BSD-3-Clause",
        "license_url": "https://github.com/pyexcel/pyexcel/blob/0bfeee32704678a9da498d62b5c55dc8d474853e/LICENSE",
    },
    {
        "name": "pyexcel-empty-sheet.xlsx",
        "format": "xlsx",
        "url": "https://raw.githubusercontent.com/pyexcel/pyexcel/0bfeee32704678a9da498d62b5c55dc8d474853e/tests/fixtures/file_with_an_empty_sheet.xlsx",
        "source": "pyexcel/pyexcel",
        "license": "BSD-3-Clause",
        "license_url": "https://github.com/pyexcel/pyexcel/blob/0bfeee32704678a9da498d62b5c55dc8d474853e/LICENSE",
    },
    {
        "name": "eparse-nested.xlsx",
        "format": "xlsx",
        "url": "https://raw.githubusercontent.com/ChrisPappalardo/eparse/039e55266aad31711954be4d6fb74f3765104207/tests/eparse_nested_test_data.xlsx",
        "source": "ChrisPappalardo/eparse",
        "license": "MIT",
        "license_url": "https://github.com/ChrisPappalardo/eparse/blob/039e55266aad31711954be4d6fb74f3765104207/LICENSE",
    },
    {
        "name": "eparse-unit.xlsx",
        "format": "xlsx",
        "url": "https://raw.githubusercontent.com/ChrisPappalardo/eparse/039e55266aad31711954be4d6fb74f3765104207/tests/eparse_unit_test_data.xlsx",
        "source": "ChrisPappalardo/eparse",
        "license": "MIT",
        "license_url": "https://github.com/ChrisPappalardo/eparse/blob/039e55266aad31711954be4d6fb74f3765104207/LICENSE",
    },
    {
        "name": "apache-poi-sample.xlsx",
        "format": "xlsx",
        "url": "https://raw.githubusercontent.com/apache/poi/379bcdcc4cfe9d899eabc2e226a1322161413c7f/test-data/spreadsheet/SampleSS.xlsx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-simple-comments.xlsx",
        "format": "xlsx",
        "url": "https://raw.githubusercontent.com/apache/poi/379bcdcc4cfe9d899eabc2e226a1322161413c7f/test-data/spreadsheet/SimpleWithComments.xlsx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-inline-strings.xlsx",
        "format": "xlsx",
        "url": "https://raw.githubusercontent.com/apache/poi/379bcdcc4cfe9d899eabc2e226a1322161413c7f/test-data/spreadsheet/InlineStrings.xlsx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-sample-strict.xlsx",
        "format": "xlsx",
        "url": "https://raw.githubusercontent.com/apache/poi/379bcdcc4cfe9d899eabc2e226a1322161413c7f/test-data/spreadsheet/SampleSS.strict.xlsx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-shared-hyperlink.xlsx",
        "format": "xlsx",
        "url": "https://raw.githubusercontent.com/apache/poi/379bcdcc4cfe9d899eabc2e226a1322161413c7f/test-data/spreadsheet/sharedhyperlink.xlsx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-header-footer.xlsx",
        "format": "xlsx",
        "url": "https://raw.githubusercontent.com/apache/poi/379bcdcc4cfe9d899eabc2e226a1322161413c7f/test-data/spreadsheet/headerFooterTest.xlsx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-ampersand-header.xlsx",
        "format": "xlsx",
        "url": "https://raw.githubusercontent.com/apache/poi/379bcdcc4cfe9d899eabc2e226a1322161413c7f/test-data/spreadsheet/AmpersandHeader.xlsx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-header-footer-complex.xlsx",
        "format": "xlsx",
        "url": "https://raw.githubusercontent.com/apache/poi/379bcdcc4cfe9d899eabc2e226a1322161413c7f/test-data/spreadsheet/HeaderFooterComplexFormats.xlsx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-simple-strict.xlsx",
        "format": "xlsx",
        "url": "https://raw.githubusercontent.com/apache/poi/379bcdcc4cfe9d899eabc2e226a1322161413c7f/test-data/spreadsheet/SimpleStrict.xlsx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-with-textbox.xlsx",
        "format": "xlsx",
        "url": "https://raw.githubusercontent.com/apache/poi/379bcdcc4cfe9d899eabc2e226a1322161413c7f/test-data/spreadsheet/WithTextBox.xlsx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-with-drawing.xlsx",
        "format": "xlsx",
        "url": "https://raw.githubusercontent.com/apache/poi/379bcdcc4cfe9d899eabc2e226a1322161413c7f/test-data/spreadsheet/WithDrawing.xlsx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-picture.xlsx",
        "format": "xlsx",
        "url": "https://raw.githubusercontent.com/apache/poi/379bcdcc4cfe9d899eabc2e226a1322161413c7f/test-data/spreadsheet/picture.xlsx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-with-chart.xlsx",
        "format": "xlsx",
        "url": "https://raw.githubusercontent.com/apache/poi/379bcdcc4cfe9d899eabc2e226a1322161413c7f/test-data/spreadsheet/WithChart.xlsx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
    {
        "name": "apache-poi-chart-title-formula.xlsx",
        "format": "xlsx",
        "url": "https://raw.githubusercontent.com/apache/poi/379bcdcc4cfe9d899eabc2e226a1322161413c7f/test-data/spreadsheet/chartTitle_withTitleFormula.xlsx",
        "source": "apache/poi",
        "license": "Apache-2.0",
        "license_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
    },
]

SOURCE_REVISIONS = {
    "python-openxml/python-docx": "e45454602b53e8e572b179ccf1c91093ec9f4ed7",
    "bgreenwell/doxx": "51c9bc40c0a178abe51377cf692293b1723c63b7",
    "apache/poi": "379bcdcc4cfe9d899eabc2e226a1322161413c7f",
    "scanny/python-pptx": "278b47b1dedd5b46ee84c286e77cdfb0bf4594be",
    "pyexcel/pyexcel": "0bfeee32704678a9da498d62b5c55dc8d474853e",
    "ChrisPappalardo/eparse": "039e55266aad31711954be4d6fb74f3765104207",
}
INTEGRITY_MANIFEST_PATH = Path(__file__).with_name("public_ooxml_fixture_integrity.json")


def _pin_builtin_fixture(fixture: dict, integrity: dict) -> None:
    source = fixture["source"]
    revision = SOURCE_REVISIONS[source]
    parsed = urllib.parse.urlsplit(fixture["url"])
    try:
        decoded_path = urllib.parse.unquote_to_bytes(parsed.path).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(
            "fixture URL path is not valid UTF-8: {}".format(fixture["name"])
        ) from exc
    expected_prefix = "/{}/{}/".format(source, revision)
    if (
        parsed.scheme != "https"
        or parsed.netloc.lower() != "raw.githubusercontent.com"
        or parsed.query
        or parsed.fragment
        or not decoded_path.startswith(expected_prefix)
        or decoded_path == expected_prefix
    ):
        raise ValueError("fixture URL is not pinned to its source revision: {}".format(fixture["name"]))
    fixture["source_revision"] = revision
    fixture["source_name"] = decoded_path[len(expected_prefix):]
    fixture.update(integrity[fixture["name"]])


_INTEGRITY_MANIFEST = json.loads(INTEGRITY_MANIFEST_PATH.read_text(encoding="utf-8"))
if _INTEGRITY_MANIFEST.get("source_revisions") != SOURCE_REVISIONS:
    raise ValueError("fixture integrity manifest source revisions are stale")
for _fixture in PUBLIC_OOXML_FIXTURES:
    _pin_builtin_fixture(_fixture, _INTEGRITY_MANIFEST["fixtures"])
del _fixture

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
            "Eto ochen prostoy[^1] text so snoskoy",
            "snoska",
        ],
        "expected_markdown": [
            "[^1]: snoska",
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
            "A pendant worn in place of the red spot (tilaka [^1]or 'tika')",
            "Apache Tika is a subproject of the Lucene",
        ],
        "expected_markdown": [
            "[^1]: XXX",
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

APACHE_POI_PROBE_MANIFEST_VERSION = 3


def _validate_fixture_identity(fixture: dict) -> None:
    if not isinstance(fixture, dict):
        raise ValueError("fixture index entries must be JSON objects")

    file_format = fixture.get("format")
    if not isinstance(file_format, str) or file_format not in ALLOWED_OOXML_FORMATS:
        allowed = ", ".join(sorted(ALLOWED_OOXML_FORMATS))
        raise ValueError("fixture format must be one of: {}".format(allowed))

    name = fixture.get("name")
    invalid_name = (
        not isinstance(name, str)
        or not name.strip()
        or name in {".", ".."}
        or "\x00" in name
        or "/" in name
        or "\\" in name
    )
    if not invalid_name:
        invalid_name = (
            PurePosixPath(name).is_absolute()
            or PureWindowsPath(name).is_absolute()
            or PurePosixPath(name).name != name
            or PureWindowsPath(name).name != name
        )
    if invalid_name:
        raise ValueError("fixture name must be a non-empty single basename")

    source_revision = _fixture_source_revision(fixture)
    if source_revision and (
        not isinstance(source_revision, str)
        or not source_revision.strip()
        or "/" in source_revision
        or "\\" in source_revision
    ):
        raise ValueError("fixture source revision must be a non-empty path segment")

    url = fixture.get("url")
    if isinstance(url, str):
        parsed = urllib.parse.urlsplit(url)
        if parsed.hostname == "raw.githubusercontent.com":
            source = fixture.get("source")
            source_name = fixture.get("source_name")
            source_parts = source.split("/") if isinstance(source, str) else []
            source_name_parts = (
                source_name.split("/") if isinstance(source_name, str) else []
            )
            immutable_revision = (
                len(source_revision) == 40
                and all(
                    character in "0123456789abcdef"
                    for character in source_revision
                )
            )
            unsafe_source = (
                len(source_parts) != 2
                or any(part in ("", ".", "..") for part in source_parts)
            )
            unsafe_source_name = (
                not source_name_parts
                or any(part in ("", ".", "..") for part in source_name_parts)
                or "\\" in source_name
            )
            invalid_percent_escape = any(
                character == "%"
                and (
                    index + 2 >= len(parsed.path)
                    or any(
                        digit not in "0123456789abcdefABCDEF"
                        for digit in parsed.path[index + 1:index + 3]
                    )
                )
                for index, character in enumerate(parsed.path)
            )
            try:
                decoded_path = urllib.parse.unquote_to_bytes(parsed.path).decode(
                    "utf-8"
                )
            except UnicodeDecodeError:
                decoded_path = ""
            expected_path = "/{}/{}/{}".format(
                source,
                source_revision,
                source_name,
            )
            if (
                parsed.scheme != "https"
                or parsed.netloc.lower() != "raw.githubusercontent.com"
                or parsed.query
                or parsed.fragment
                or not immutable_revision
                or unsafe_source
                or unsafe_source_name
                or invalid_percent_escape
                or decoded_path != expected_path
            ):
                raise ValueError(
                    "fixture URL does not exactly match its source revision and name"
                )

    recorded_fixture_id = fixture.get("fixture_id")
    if recorded_fixture_id is not None:
        if not fixture.get("identity_sha256") and not fixture.get("sha256"):
            raise ValueError(
                "fixture fixture_id requires a sha256-backed canonical identity"
            )
        canonical_fixture_id = _canonical_apache_poi_fixture_id(fixture)
        if recorded_fixture_id != canonical_fixture_id:
            raise ValueError("fixture fixture_id does not match its canonical identity")


def _fixture_source_revision(fixture: dict) -> str:
    for key in ("source_revision", "source_ref", "ref"):
        value = fixture.get(key)
        if value not in (None, ""):
            revision = str(value).strip()
            if len(revision) == 40 and all(
                character in "0123456789abcdefABCDEF" for character in revision
            ):
                return revision.lower()
            return revision
    return ""


def _normalize_manifest_id_map(value, field_name: str) -> Dict[str, List[str]]:
    if not isinstance(value, dict):
        raise ValueError("probe manifest {} must be a JSON object".format(field_name))
    normalized: Dict[str, List[str]] = {}
    for file_format, fixture_ids in value.items():
        if isinstance(fixture_ids, (str, bytes)) or not isinstance(
            fixture_ids,
            (list, tuple, set),
        ):
            raise ValueError(
                "probe manifest {} entries must be JSON arrays".format(field_name)
            )
        normalized[str(file_format).lower().lstrip(".")] = sorted(
            {str(item) for item in fixture_ids}
        )
    return normalized


def _expected_fixture_sha256(fixture: dict):
    if "sha256" not in fixture:
        return None
    expected = fixture["sha256"]
    if (
        not isinstance(expected, str)
        or len(expected) != 64
        or any(character not in "0123456789abcdefABCDEF" for character in expected)
    ):
        raise ValueError("fixture sha256 must be a 64-character hexadecimal digest")
    return expected.lower()


def _expected_fixture_bytes(fixture: dict):
    if "bytes" not in fixture:
        return None
    expected = fixture["bytes"]
    if isinstance(expected, bool) or not isinstance(expected, int) or expected < 0:
        raise ValueError("fixture bytes must be a non-negative integer")
    return expected


def _fixture_destination(fixture: dict, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_root = output_dir.resolve(strict=False)
    format_dir = output_dir / fixture["format"]
    destination = format_dir / fixture["name"]
    resolved_destination = destination.resolve(strict=False)
    try:
        resolved_destination.relative_to(output_root)
    except ValueError:
        raise ValueError("fixture destination resolves outside output directory")
    return destination


def _open_fixture_parent(output_dir: Path, file_format: str):
    """Open one corpus format directory without following a replaced symlink."""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_root = output_dir.resolve(strict=True)
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    root_fd = os.open(str(output_root), directory_flags)
    try:
        try:
            parent_fd = os.open(file_format, directory_flags, dir_fd=root_fd)
        except FileNotFoundError:
            try:
                os.mkdir(file_format, mode=0o777, dir_fd=root_fd)
            except FileExistsError:
                pass
            parent_fd = os.open(file_format, directory_flags, dir_fd=root_fd)
    except OSError as exc:
        os.close(root_fd)
        raise ValueError("fixture destination resolves outside output directory") from exc
    os.close(root_fd)
    return output_root, parent_fd


def _fixture_parent_is_current(
    output_root: Path,
    file_format: str,
    parent_fd: int,
) -> bool:
    """Return whether the live corpus path still names the opened directory."""
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    root_fd = None
    current_fd = None
    try:
        root_fd = os.open(str(output_root), directory_flags)
        current_fd = os.open(file_format, directory_flags, dir_fd=root_fd)
        opened = os.fstat(parent_fd)
        current = os.fstat(current_fd)
        return (opened.st_dev, opened.st_ino) == (current.st_dev, current.st_ino)
    except OSError:
        return False
    finally:
        if current_fd is not None:
            os.close(current_fd)
        if root_fd is not None:
            os.close(root_fd)


def _open_fixture_temp(parent_fd: int, destination_name: str):
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    for _ in range(128):
        temporary_name = ".{}.{}.part".format(
            destination_name,
            secrets.token_hex(8),
        )
        try:
            temporary_fd = os.open(
                temporary_name,
                flags,
                0o666,
                dir_fd=parent_fd,
            )
        except FileExistsError:
            continue
        return temporary_name, temporary_fd
    raise FileExistsError(
        "could not allocate download temporary file for: {}".format(
            destination_name
        )
    )


def selected_fixtures(formats: Iterable[str], fixtures: Iterable[dict] = None) -> List[dict]:
    fixtures = list(PUBLIC_OOXML_FIXTURES if fixtures is None else fixtures)
    for fixture in fixtures:
        _validate_fixture_identity(fixture)
    requested = {fmt.lower().lstrip(".") for fmt in formats}
    return [fixture for fixture in fixtures if fixture["format"] in requested]


def load_fixture_index(path: Path) -> List[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    fixtures = payload.get("fixtures", payload) if isinstance(payload, dict) else payload
    if not isinstance(fixtures, list):
        raise ValueError("fixture index must be a JSON list or an object with a 'fixtures' list")
    loaded = []
    for fixture in fixtures:
        _validate_fixture_identity(fixture)
        loaded.append(dict(fixture))
    return loaded


def empty_apache_poi_probe_manifest() -> dict:
    return {
        "version": APACHE_POI_PROBE_MANIFEST_VERSION,
        "used": {},
        "used_sources": {},
        "legacy_used": {},
        "probes": [],
    }


def load_apache_poi_probe_manifest(path: Path) -> dict:
    if not path.exists():
        return empty_apache_poi_probe_manifest()
    payload = json.loads(path.read_text(encoding="utf-8"))
    manifest = empty_apache_poi_probe_manifest()
    if not isinstance(payload, dict):
        raise ValueError("probe manifest must be a JSON object")
    version = payload.get("version", 1)
    if type(version) is not int:
        raise ValueError("probe manifest version must be an integer")
    if version < 1 or version > APACHE_POI_PROBE_MANIFEST_VERSION:
        raise ValueError("probe manifest version is not supported")
    normalized_used = _normalize_manifest_id_map(payload.get("used", {}), "used")
    normalized_used_sources = _normalize_manifest_id_map(
        payload.get("used_sources", {}),
        "used_sources",
    )
    normalized_legacy = _normalize_manifest_id_map(
        payload.get("legacy_used", {}),
        "legacy_used",
    )
    probes = payload.get("probes", [])
    if not isinstance(probes, list) or not all(
        isinstance(probe, dict) for probe in probes
    ):
        raise ValueError("probe manifest probes must be a JSON array of objects")
    if version < APACHE_POI_PROBE_MANIFEST_VERSION:
        legacy_formats = set(normalized_legacy) | set(normalized_used)
        normalized_legacy = {
            file_format: sorted(
                set(normalized_legacy.get(file_format, ()))
                | set(normalized_used.get(file_format, ()))
            )
            for file_format in legacy_formats
        }
        normalized_used = {}
        normalized_used_sources = {}
    manifest["used"] = normalized_used
    manifest["used_sources"] = normalized_used_sources
    manifest["legacy_used"] = normalized_legacy
    manifest["probes"] = [dict(probe) for probe in probes]
    return manifest


def _fixture_source_name(fixture: dict) -> str:
    source_name = fixture.get("source_name")
    if not source_name and fixture.get("url"):
        source_name = str(fixture["url"]).rstrip("/").rsplit("/", 1)[-1]
    if not source_name and fixture.get("path"):
        source_name = Path(str(fixture["path"])).name
    if not source_name:
        source_name = fixture.get("name", "")
    return str(source_name)


def apache_poi_fixture_source_id(fixture: dict) -> str:
    components = {
        "source": str(fixture.get("source", "")).strip(),
        "source_name": _fixture_source_name(fixture),
        "source_revision": _fixture_source_revision(fixture),
    }
    canonical = json.dumps(
        components,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "source-v1:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _canonical_apache_poi_fixture_id(fixture: dict) -> str:
    sha256 = fixture.get("identity_sha256") or fixture.get("sha256", "")
    if sha256:
        sha256 = _expected_fixture_sha256({"sha256": sha256})
    components = {
        "sha256": sha256 or "",
        "source": str(fixture.get("source", "")).strip(),
        "source_name": _fixture_source_name(fixture),
        "source_revision": _fixture_source_revision(fixture),
    }
    canonical = json.dumps(components, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "v2:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def apache_poi_fixture_id(fixture: dict) -> str:
    canonical = _canonical_apache_poi_fixture_id(fixture)
    recorded = fixture.get("fixture_id")
    if recorded is not None and recorded != canonical:
        raise ValueError("fixture fixture_id does not match its canonical identity")
    return canonical


def _legacy_apache_poi_fixture_id(fixture: dict) -> str:
    if fixture.get("source_name"):
        return str(fixture["source_name"])
    if fixture.get("url"):
        return str(fixture["url"]).rstrip("/").rsplit("/", 1)[-1]
    if fixture.get("path"):
        return Path(str(fixture["path"])).name
    return str(fixture.get("name", ""))


def select_unseen_apache_poi_fixtures(
    candidates: Iterable[dict],
    formats: Iterable[str],
    per_format: int,
    manifest: dict = None,
) -> List[dict]:
    manifest = manifest or empty_apache_poi_probe_manifest()
    requested = [fmt.lower().lstrip(".") for fmt in formats]
    manifest_version = manifest.get("version", 1)
    direct_legacy_used = (
        manifest.get("used", {})
        if manifest_version < APACHE_POI_PROBE_MANIFEST_VERSION
        else {}
    )
    used_by_format = {
        file_format: set(fixture_ids)
        for file_format, fixture_ids in (
            {} if direct_legacy_used else manifest.get("used", {})
        ).items()
    }
    used_sources_by_format = {
        file_format: set(source_ids)
        for file_format, source_ids in manifest.get("used_sources", {}).items()
    }
    legacy_used_by_format = {
        file_format: set(fixture_ids)
        for file_format, fixture_ids in manifest.get("legacy_used", {}).items()
    }
    for file_format, fixture_ids in direct_legacy_used.items():
        legacy_used_by_format.setdefault(file_format, set()).update(fixture_ids)
    selected = []
    counts: Dict[str, int] = {file_format: 0 for file_format in requested}

    for fixture in sorted(candidates, key=lambda item: (item.get("format", ""), apache_poi_fixture_id(item))):
        file_format = str(fixture.get("format", "")).lower().lstrip(".")
        if file_format not in counts or counts[file_format] >= per_format:
            continue
        fixture_id = apache_poi_fixture_id(fixture)
        if fixture_id in used_by_format.get(file_format, set()):
            continue
        source_id = apache_poi_fixture_source_id(fixture)
        if source_id in used_sources_by_format.get(file_format, set()):
            continue
        has_immutable_identity = bool(
            _fixture_source_revision(fixture) or fixture.get("sha256")
        )
        if (
            not has_immutable_identity
            and _legacy_apache_poi_fixture_id(fixture)
            in legacy_used_by_format.get(file_format, set())
        ):
            continue
        selected.append(fixture)
        counts[file_format] += 1
    return selected


def record_probe_outcome(
    path: Path,
    records: List[dict],
    probe_name: str,
    *,
    successful_records: Iterable[dict] = (),
    invalid: Iterable[dict] = (),
    failure_reasons: Iterable[str] = (),
) -> dict:
    manifest = load_apache_poi_probe_manifest(path)
    used = {
        file_format: set(fixture_ids)
        for file_format, fixture_ids in manifest.get("used", {}).items()
    }
    used_sources = {
        file_format: set(source_ids)
        for file_format, source_ids in manifest.get("used_sources", {}).items()
    }
    successful = {
        (apache_poi_fixture_id(record), str(record.get("path", "")))
        for record in successful_records
    }
    invalid_by_path = {
        str(item.get("path", "")): str(item.get("error", ""))
        for item in invalid
    }
    probe_files = []

    for record in records:
        file_format = str(record.get("format", "")).lower().lstrip(".")
        fixture_id = apache_poi_fixture_id(record)
        if not file_format or not fixture_id:
            continue
        record_path = str(record.get("path", ""))
        if record_path in invalid_by_path:
            status = "invalid"
        elif (fixture_id, record_path) in successful:
            status = "success"
            used.setdefault(file_format, set()).add(fixture_id)
            used_sources.setdefault(file_format, set()).add(
                apache_poi_fixture_source_id(record)
            )
        else:
            status = "failed"
        probe_file = {
            "format": file_format,
            "id": fixture_id,
            "path": record_path,
            "status": status,
        }
        if status == "invalid" and invalid_by_path[record_path]:
            probe_file["error"] = invalid_by_path[record_path]
        probe_files.append(probe_file)

    manifest["used"] = {
        file_format: sorted(fixture_ids)
        for file_format, fixture_ids in sorted(used.items())
    }
    manifest["used_sources"] = {
        file_format: sorted(source_ids)
        for file_format, source_ids in sorted(used_sources.items())
    }
    reasons = [str(reason) for reason in failure_reasons]
    manifest["probes"].append({
        "name": probe_name,
        "ok": not reasons and all(item["status"] == "success" for item in probe_files),
        "failure_reasons": reasons,
        "files": sorted(
            probe_files,
            key=lambda item: (item["format"], item["path"], item["id"]),
        ),
    })
    atomic_write_text(
        path,
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    )
    return manifest


def record_apache_poi_probe_manifest(
    path: Path,
    records: List[dict],
    probe_name: str,
) -> dict:
    """Compatibility wrapper for callers recording an all-success probe."""
    return record_probe_outcome(
        path,
        records,
        probe_name,
        successful_records=records,
    )


def download_fixture(
    fixture: dict,
    output_dir: Path,
    *,
    timeout: float = DOWNLOAD_TIMEOUT_SECONDS,
    max_download_bytes: int = MAX_DOWNLOAD_BYTES,
) -> dict:
    _validate_fixture_identity(fixture)
    supplied_fixture_id = fixture.get("fixture_id")
    expected_sha256 = _expected_fixture_sha256(fixture)
    expected_bytes = _expected_fixture_bytes(fixture)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ValueError("download timeout must be a positive number")
    if (
        isinstance(max_download_bytes, bool)
        or not isinstance(max_download_bytes, int)
        or max_download_bytes < 0
    ):
        raise ValueError("maximum download size must be a non-negative integer")

    output_dir = Path(output_dir)
    destination = _fixture_destination(fixture, output_dir)
    digest = hashlib.sha256()
    downloaded_bytes = 0
    output_root = None
    parent_fd = None
    temporary_name = None
    temporary_fd = None
    try:
        parsed_url = urllib.parse.urlsplit(fixture["url"])
        if parsed_url.scheme != "https" or not parsed_url.hostname:
            raise ValueError("fixture URL must use HTTPS")

        output_root, parent_fd = _open_fixture_parent(
            output_dir,
            fixture["format"],
        )
        try:
            destination_stat = os.stat(
                destination.name,
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            destination_mode = None
        else:
            if not stat.S_ISREG(destination_stat.st_mode):
                raise OSError(
                    "fixture destination is not a regular file: {}".format(
                        destination
                    )
                )
            destination_mode = destination_stat.st_mode & 0o777

        temporary_name, temporary_fd = _open_fixture_temp(
            parent_fd,
            destination.name,
        )
        if destination_mode is not None:
            os.fchmod(temporary_fd, destination_mode)

        # The external index URL is constrained immediately above to HTTPS
        # with a non-empty host, then streamed under time and byte limits.
        deadline = time.monotonic() + float(timeout)
        with urllib.request.urlopen(  # nosemgrep: dynamic-urllib-use-detected
            fixture["url"],
            timeout=timeout,
        ) as response:
            with os.fdopen(temporary_fd, mode="wb") as temporary_file:
                temporary_fd = None
                read_chunk = getattr(response, "read1", None)
                if read_chunk is None:
                    read_chunk = response.read
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError(
                            "download exceeded wall clock timeout of {} seconds".format(
                                timeout
                            )
                        )
                    _set_response_timeout(response, remaining)
                    chunk = read_chunk(DOWNLOAD_CHUNK_BYTES)
                    if time.monotonic() > deadline:
                        raise TimeoutError(
                            "download exceeded wall clock timeout of {} seconds".format(
                                timeout
                            )
                        )
                    if not chunk:
                        break
                    next_size = downloaded_bytes + len(chunk)
                    if next_size > max_download_bytes:
                        raise ValueError(
                            "download exceeds maximum download size of {} bytes".format(
                                max_download_bytes
                            )
                        )
                    temporary_file.write(chunk)
                    digest.update(chunk)
                    downloaded_bytes = next_size
                temporary_file.flush()
                os.fsync(temporary_file.fileno())

        actual_sha256 = digest.hexdigest()
        if expected_bytes is not None and downloaded_bytes != expected_bytes:
            raise ValueError(
                "downloaded bytes {} does not match expected bytes {}".format(
                    downloaded_bytes,
                    expected_bytes,
                )
            )
        if expected_sha256 is not None and actual_sha256 != expected_sha256:
            raise ValueError(
                "downloaded sha256 {} does not match expected sha256 {}".format(
                    actual_sha256,
                    expected_sha256,
                )
            )

        identity_record = dict(fixture)
        identity_record.pop("fixture_id", None)
        identity_record["identity_sha256"] = actual_sha256
        identity_record["sha256"] = actual_sha256
        actual_fixture_id = apache_poi_fixture_id(identity_record)
        if (
            supplied_fixture_id is not None
            and supplied_fixture_id != actual_fixture_id
        ):
            raise ValueError(
                "fixture fixture_id does not match downloaded content identity"
            )

        if not _fixture_parent_is_current(
            output_root,
            fixture["format"],
            parent_fd,
        ):
            raise OSError("fixture destination directory changed during download")
        os.replace(
            temporary_name,
            destination.name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        temporary_name = None
        os.fsync(parent_fd)
        if not _fixture_parent_is_current(
            output_root,
            fixture["format"],
            parent_fd,
        ):
            try:
                os.unlink(destination.name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
            raise OSError("fixture destination directory changed during download")
    finally:
        if temporary_fd is not None:
            os.close(temporary_fd)
        if temporary_name is not None and parent_fd is not None:
            try:
                os.unlink(temporary_name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
        if parent_fd is not None:
            os.close(parent_fd)

    record = dict(fixture)
    record.pop("fixture_id", None)
    record["identity_sha256"] = actual_sha256
    record["path"] = destination.relative_to(output_dir).as_posix()
    record["bytes"] = downloaded_bytes
    record["sha256"] = actual_sha256
    record["fixture_id"] = actual_fixture_id
    return record


def write_sources(output_dir: Path, records: List[dict]) -> None:
    atomic_write_text(
        output_dir / "SOURCES.json",
        json.dumps(records, ensure_ascii=False, indent=2),
    )
    lines = [
        "# Public OOXML Corpus Sources",
        "",
        "| File | Format | Source | Revision | License | Bytes | SHA-256 | URL |",
        "| --- | --- | --- | --- | --- | ---: | --- | --- |",
    ]
    for record in records:
        lines.append(
            "| {path} | {format} | {source} | {source_revision} | {license} | {bytes} | {sha256} | {url} |".format(
                path=record["path"],
                format=record["format"],
                source=record["source"],
                source_revision=record.get("source_revision", ""),
                license=record["license"],
                bytes=record["bytes"],
                sha256=record.get("sha256", ""),
                url=record["url"],
            )
        )
    lines.append("")
    atomic_write_text(output_dir / "SOURCES.md", "\n".join(lines))


def _set_response_timeout(response, timeout: float) -> None:
    """Best-effort socket deadline tightening; read1 keeps slow-drip reads bounded."""
    try:
        response.fp.raw._sock.settimeout(max(timeout, 0.001))
    except (AttributeError, OSError):
        return


def _open_parent_directory(path: Path):
    absolute_parent = Path(os.path.abspath(str(path.parent)))
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    parent_fd = os.open(os.path.sep, directory_flags)
    try:
        for part in absolute_parent.parts[1:]:
            try:
                child_fd = os.open(part, directory_flags, dir_fd=parent_fd)
            except FileNotFoundError:
                try:
                    os.mkdir(part, mode=0o777, dir_fd=parent_fd)
                except FileExistsError:
                    pass
                child_fd = os.open(part, directory_flags, dir_fd=parent_fd)
            os.close(parent_fd)
            parent_fd = child_fd
    except Exception:
        os.close(parent_fd)
        raise
    return absolute_parent, parent_fd


def _parent_directory_is_current(parent: Path, parent_fd: int) -> bool:
    try:
        live = os.stat(str(parent), follow_symlinks=False)
        opened = os.fstat(parent_fd)
    except OSError:
        return False
    return stat.S_ISDIR(live.st_mode) and (
        live.st_dev,
        live.st_ino,
    ) == (
        opened.st_dev,
        opened.st_ino,
    )


def atomic_write_text(path: Path, payload: str) -> None:
    path = Path(path)
    if path.name in {"", ".", ".."}:
        raise ValueError("atomic output path must name a file")
    parent, parent_fd = _open_parent_directory(path)
    temporary_name = None
    temporary_fd = None
    try:
        try:
            destination_stat = os.stat(
                path.name,
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            destination_mode = None
        else:
            if not stat.S_ISREG(destination_stat.st_mode):
                raise OSError("atomic output destination is not a regular file: {}".format(path))
            destination_mode = stat.S_IMODE(destination_stat.st_mode)
        flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        for _ in range(128):
            temporary_name = ".{}.{}.tmp".format(path.name, secrets.token_hex(8))
            try:
                temporary_fd = os.open(
                    temporary_name,
                    flags,
                    0o666,
                    dir_fd=parent_fd,
                )
            except FileExistsError:
                continue
            break
        else:
            raise FileExistsError("could not allocate manifest temporary file: {}".format(path))

        if destination_mode is not None:
            os.fchmod(temporary_fd, destination_mode)

        with os.fdopen(temporary_fd, mode="w", encoding="utf-8") as temporary_file:
            temporary_fd = None
            temporary_file.write(payload)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        if not _parent_directory_is_current(parent, parent_fd):
            raise OSError("atomic output directory changed during write: {}".format(parent))
        os.replace(
            temporary_name,
            path.name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        temporary_name = None
        os.fsync(parent_fd)
        if not _parent_directory_is_current(parent, parent_fd):
            try:
                os.unlink(path.name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
            raise OSError("atomic output directory changed during write: {}".format(parent))
    finally:
        if temporary_fd is not None:
            os.close(temporary_fd)
        if temporary_name is not None:
            try:
                os.unlink(temporary_name, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
        os.close(parent_fd)


_atomic_write_text = atomic_write_text


def write_expected_manifest(output_dir: Path, records: List[dict]) -> None:
    expected = {
        record["path"]: PUBLIC_OOXML_EXPECTATIONS[record["path"]]
        for record in records
        if record.get("path") in PUBLIC_OOXML_EXPECTATIONS
    }
    _atomic_write_text(
        output_dir / "expected.json",
        json.dumps(expected, ensure_ascii=False, indent=2),
    )


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
