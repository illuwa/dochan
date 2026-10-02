"""Inventory public corpus CFB Word streams for fObfuscated, read-only."""
import argparse
import json
import struct
from pathlib import Path

from dochan import cfb
from dochan.cfb import OleFileError


def inventory(root):
    result = {"root": str(root), "cfb_files": 0, "word_streams": 0,
              "obfuscated_files": [], "unreadable_cfb": 0}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        try:
            with path.open("rb") as handle:
                if handle.read(8) != b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
                    continue
            result["cfb_files"] += 1
            with cfb.OleFileIO(str(path)) as ole:
                if not ole.exists("WordDocument"):
                    continue
                result["word_streams"] += 1
                with ole.openstream("WordDocument") as stream:
                    fib = stream.read(68)
                if len(fib) >= 18 and struct.unpack_from("<H", fib, 10)[0] & 0x8000:
                    result["obfuscated_files"].append(str(path.relative_to(root)))
        except (OSError, ValueError, OleFileError):
            result["unreadable_cfb"] += 1
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpora", nargs="+", type=Path,
                        help="Public POI/LibreOffice corpus directories only")
    args = parser.parse_args()
    for root in args.corpora:
        if not root.is_dir():
            parser.error("Corpus must be an existing directory")
    print(json.dumps([inventory(root) for root in args.corpora], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
