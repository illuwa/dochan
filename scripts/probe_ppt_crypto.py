"""Read-only POI PPT encryption checks. Pass the test-data directory."""
import argparse
import base64
import hashlib
import json
import struct
from pathlib import Path

import olefile

from dochan import Dochan
from dochan.crypto.ppt import decrypt_presentation
from dochan.office_binary.ppt import PPTReader
from dochan.output.markdown import to_markdown
from dochan.output.json_out import to_dict


CASES = [
    ('Password_Protected-56-hello.ppt', 'hello', 'This is a protected document'),
    ('Password_Protected-hello.ppt', 'hello', 'This is a protected document'),
    ('Password_Protected-np-hello.ppt', 'hello', 'This is a protected document'),
    ('cryptoapi-proc2356.ppt', 'crypto', 'Dominic Salemno'),
    ('ppt_with_png_encrypted.ppt', 'password', 'Here is a PNG image:'),
]

# POI TestDocumentEncryption.java:159-176 asserts these payload hashes.
PICTURE_HASHES = [
    'nKsDTKqxTCR8LFkVVWlP9GSTvZ0=', 'SuNOR+9V1UVYZIoeD65l3VTaLoc=',
    'Ql3IGrr4bNq07ZTp5iPg7b+pva8=', '8pdst9NjBGSfWezSZE8+aVhIRe0=',
    'go6xqW7lvkCtlOO5tYLiMfb4oxw=', 'gZUM8YqRNL5kGNfyyYvEEernvCc=',
    'CNU2iiqUFAnk3TDXsXV1ihH9eRM=',
]


def decrypted_pictures(path, password):
    with olefile.OleFileIO(str(path)) as ole:
        _, pictures = decrypt_presentation(
            ole.openstream('PowerPoint Document').read(),
            ole.openstream('Current User').read(),
            ole.openstream('Pictures').read(), password,
        )
    return pictures


def probe(base):
    results = []
    for name, password, expected in CASES:
        path = base / 'slideshow' / name
        doc = PPTReader(password=password).read(str(path))
        api = Dochan(str(path), password=password)
        negative = []
        for bad_password in (None, 'incorrect-input'):
            bad = PPTReader(password=bad_password).read(str(path))
            negative.append(not bad.sections and any(e.startswith('ERR: 암호화된 문서') for e in bad.errors))
        result = {
            'file': name, 'slides': len(doc.sections),
            'api_matches_reader': api.to_dict() == to_dict(doc),
            'expected_text_found': expected in to_markdown(doc),
            'negative_cases_passed': sum(negative),
            'warnings': doc.errors,
        }
        if name == 'cryptoapi-proc2356.ppt':
            pictures = decrypted_pictures(path, password)
            hashes = []
            offset = 0
            while offset < len(pictures):
                _, _, size = struct.unpack_from('<HHI', pictures, offset)
                payload = pictures[offset + 25:offset + size + 8]
                hashes.append(base64.b64encode(hashlib.sha1(payload).digest()).decode('ascii'))
                offset += size + 8
            result['picture_hashes_match'] = hashes == PICTURE_HASHES
            result['picture_count'] = len(hashes)
        if name == 'ppt_with_png_encrypted.ppt':
            pictures = decrypted_pictures(path, password)
            plain_path = base / 'slideshow' / 'ppt_with_png.ppt'
            with olefile.OleFileIO(str(plain_path)) as ole:
                reference = ole.openstream('Pictures').read()
            result['png_pixels_match_plain_pair'] = pictures[15203 + 25:] == reference[25:]
            plain = PPTReader().read(str(plain_path))
            actual_images = [(image.image_format, image.image_data) for image in doc.find_all('image')]
            expected_images = [(image.image_format, image.image_data) for image in plain.find_all('image')]
            result['model_image_count'] = len(actual_images)
            result['model_images_match_plain_pair'] = bool(expected_images) and actual_images == expected_images
        results.append(result)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('corpus', type=Path)
    args = parser.parse_args()
    results = probe(args.corpus)
    print(json.dumps(results, indent=2, ensure_ascii=False))
    return 0 if all(r['slides'] and r['api_matches_reader'] and r['expected_text_found'] and r['negative_cases_passed'] == 2
                    and r.get('picture_hashes_match', True) and r.get('png_pixels_match_plain_pair', True)
                    and r.get('model_images_match_plain_pair', True)
                    for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
