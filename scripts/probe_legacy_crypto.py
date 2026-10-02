"""Read-only public POI encryption probe. Pass the test-data directory."""
import argparse
import json
from pathlib import Path

from dochan import Dochan
from dochan.office_binary.doc import DOCReader
from dochan.office_binary.xls import XLSReader
from dochan.output.markdown import to_markdown
from dochan.output.json_out import to_dict


CASES = (
    ("document", "password_tika_binaryrc4.doc", "tika", DOCReader,
     ("This is an encrypted Word 2007 File.",), "binary RC4"),
    ("document", "password_password_cryptoapi.doc", "password", DOCReader,
     ("This is a test",), "RC4 CryptoAPI"),
    ("spreadsheet", "password.xls", "password", XLSReader,
     ("A ZIP bomb is a variant of mail-bombing.",), "binary RC4"),
    ("spreadsheet", "35897-type4.xls", "freedom", XLSReader,
     ("hello there!",), "RC4 CryptoAPI"),
    ("spreadsheet", "xor-encryption-abc.xls", "abc", XLSReader,
     ("1", "2", "3"), "XOR method 1"),
    ("spreadsheet", "50833.xls", None, XLSReader,
     ("test cell value",), "binary RC4 default password"),
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    args = parser.parse_args()
    results = []
    for folder, filename, password, reader, expected, algorithm in CASES:
        path = args.corpus / folder / filename
        document = reader(password=password).read(str(path))
        api = Dochan(str(path), password=password)
        text = to_markdown(document)
        success = all(value in text for value in expected) and not document.errors
        if algorithm == "XOR method 1":
            cells = [cell.text for section in document.sections
                     for table in section.elements if hasattr(table, "rows")
                     for row in table.rows for cell in row]
            success = success and cells == ["1", "2", "3"]
        negative = []
        for candidate in (None, "incorrect-probe-password"):
            if candidate is None and password is None:
                negative.append(None)
                continue
            failed = reader(password=candidate).read(str(path))
            negative.append(not failed.sections and any(
                error.startswith("ERR:") and "암호" in error for error in failed.errors))
        results.append({"file": filename, "algorithm": algorithm,
                        "api_matches_reader": api.to_dict() == to_dict(document),
                        "expected": list(expected), "content_matches": success,
                        "missing_password_rejected": negative[0],
                        "wrong_password_rejected": negative[1],
                        "errors": document.errors})
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if all(row["content_matches"] and row["api_matches_reader"] and row["missing_password_rejected"] is not False
                    and row["wrong_password_rejected"] for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
