"""구형 DOC 그림 마커 치환의 합성 입력 처리 시간과 출력 동등성을 비교한다."""
import argparse
import importlib.util
import json
from pathlib import Path
import statistics
import time

from dochan.model.document import Paragraph, TextRun
from dochan.model.image import Image
from dochan.office_binary.doc_images import replace_legacy_image_markers


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-source', type=Path, required=True)
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location(
        'dochan.office_binary._baseline_images',
        args.baseline_source / 'dochan/office_binary/doc_images.py')
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    marker = '\ue000doc-image-1\ue001'
    image = Image(image_format='wmf')
    rows = []
    for count in (1000, 2000, 4000):
        text = marker * count + 'T' * (count * 1000)
        paragraph = Paragraph(runs=[TextRun(text=text)])
        row = {'markers': count, 'characters': len(text)}
        for label, function in (
                ('before', baseline.replace_legacy_image_markers),
                ('after', replace_legacy_image_markers)):
            samples = []
            for _ in range(3):
                started = time.perf_counter()
                result = function([paragraph], {marker: image})
                samples.append(time.perf_counter() - started)
                assert len(result) == count + 1
                assert all(node is image for node in result[:-1])
                assert result[-1].text == 'T' * (count * 1000)
            row[label + '_median_seconds'] = statistics.median(samples)
        rows.append(row)
    print(json.dumps(rows, indent=2))


if __name__ == '__main__':
    main()
