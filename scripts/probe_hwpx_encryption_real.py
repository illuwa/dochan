"""Check every encrypted part of one public HWPX without writing plaintext."""
import hashlib
import json
import sys
import zipfile
import zlib

from dochan.crypto.ooxml import _aes
from dochan.hwpx.crypto import decrypt_part, read_encryption_manifest
from dochan.hwpx.parser import HWPXParser


def main():
    path = sys.argv[1]
    password = sys.stdin.readline().rstrip('\r\n')
    parser = HWPXParser()
    with zipfile.ZipFile(path) as archive:
        metadata = read_encryption_manifest(
            archive.read('META-INF/manifest.xml'),
            set(archive.namelist()), parser._encrypted_limit)
        matches = 0
        padding_lengths = []
        for name, details in metadata.items():
            iv, salt, checksum, count, size = details
            ciphertext = archive.read(name)
            plain = decrypt_part(ciphertext, details, password,
                                 parser._encrypted_limit(name), [1000000])
            matches += len(plain) == size and hashlib.sha256(plain[:1024]).digest() == checksum
            key = hashlib.pbkdf2_hmac('sha1', hashlib.sha256(password.encode()).digest(),
                                      salt, count, 32)
            compressed = _aes(key, ciphertext, iv)
            stream = zlib.decompressobj(-15)
            stream.decompress(compressed)
            assert stream.eof
            tail = stream.unused_data
            assert tail == bytes(len(tail))
            padding_lengths.append(len(tail))
    print(json.dumps({'parts': len(metadata), 'matches': matches,
                      'zero_padding_lengths': padding_lengths}, sort_keys=True))


if __name__ == '__main__':
    main()
