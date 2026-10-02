"""Read public POI samples in place and verify native OOXML decryption.

Usage: /usr/bin/python3 -m scripts.probe_ooxml_crypto /path/to/poi-src/test-data
Passwords below are public POI fixture values, never user credentials.
"""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import zipfile

import olefile

from dochan import Dochan
from dochan.crypto.ooxml import decrypt_ooxml
from dochan.ooxml.docx import DOCXReader
from dochan.ooxml.xlsx import XLSXReader
from dochan.output.plain_text import to_plain_text
from dochan.output.json_out import to_dict


CASES = (
    ("document/bug53475-password-is-pass.docx", "pass", "The is a password protected document.", None),
    ("document/bug53475-password-is-solrcell.docx", "solrcell", "This is password protected Word document.", None),
    ("spreadsheet/protected_passtika.xlsx", "tika", "This is an Encrypted Excel spreadsheet.", None),
    ("spreadsheet/58616.xlsx", None, None, "L1vDQq2EuMSfU/FBfVQfM2zfOY5Jx9ZyVgIQhXPPVgs="),
)


LO_CASES = (
    ("Encrypted_MSO2007_abc.docx", "abc", "abc", None),
    ("Encrypted_MSO2010_abc.docx", "abc", "abc", None),
    ("Encrypted_MSO2013_abc.docx", "abc", "ABC", None),
    ("Encrypted_LO_Standard_abc.docx", "abc", "ABC", None),
)


def probe(root, cases=CASES):
    rows = []
    for name, password, expected, expected_digest in cases:
        path = root / name
        with olefile.OleFileIO(str(path)) as ole:
            payload = decrypt_ooxml(ole, password)
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                crc_ok = archive.testzip() is None
            wrong_rejected = False
            try:
                decrypt_ooxml(ole, "wrong-fixture-password")
            except ValueError as exc:
                wrong_rejected = str(exc).startswith("ERR: 암호화된 문서") and "wrong-fixture-password" not in str(exc)
            missing_rejected = None
            if password is not None:
                try:
                    decrypt_ooxml(ole)
                    missing_rejected = False
                except ValueError as exc:
                    missing_rejected = str(exc).startswith("ERR: 암호화된 문서")
        reader = DOCXReader() if path.suffix == ".docx" else XLSXReader()
        parsed = reader.read(io.BytesIO(payload))
        text = to_plain_text(parsed)
        digest = base64.b64encode(hashlib.sha256(payload).digest()).decode("ascii")
        actual = Dochan(str(path), password=password)
        row = dict(file=name, payload_bytes=len(payload), crc_ok=crc_ok,
                   expected_text=expected, text_match=expected is None or expected in text,
                   expected_sha256_base64=expected_digest, actual_sha256_base64=digest,
                   digest_match=expected_digest is None or expected_digest == digest,
                   wrong_password_rejected=wrong_rejected,
                   missing_password_rejected=missing_rejected,
                   api_matches_plain_reader=actual.to_dict() == to_dict(parsed),
                   api_errors=actual.doc.errors)
        row["passed"] = all((crc_ok, row["text_match"], row["digest_match"], wrong_rejected,
                               missing_rejected is not False, row["api_matches_plain_reader"]))
        rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--lo-corpus", type=Path,
                        help="LibreOffice sw/qa/extras/ooxmlexport/data directory")
    args = parser.parse_args()
    rows = probe(args.corpus)
    if args.lo_corpus:
        rows.extend(probe(args.lo_corpus, LO_CASES))
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0 if all(row["passed"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
