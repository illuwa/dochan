"""
tests/test_hwpx_zip_bomb_guard.py — HWPX zip 항목 압축률 가드 테스트

docs/benchmarks/2026-07-27-hwp-corpus-collection-and-quality-scan.md finding #2:
실제 기상청 보도자료 HWPX에 들어있는 7.85MB BMP 차트가 77,670바이트로 압축되어
(101.1배) MAX_COMPRESSION_RATIO=100 가드에 걸려 조용히 누락됐다. BMP 는
비압축 픽셀 데이터라 단색 영역이 넓은 실사용 이미지도 흔히 100배를 넘기며,
절대 크기 상한(MAX_FILE_SIZE=100MB)이 이미 진짜 zip bomb를 막아주므로
비율 단독 가드는 과도하게 보수적이다.
"""
from dochan.hwpx.parser import _compression_ratio_exceeded


def test_real_world_bmp_chart_ratio_is_not_flagged():
    # corpus/hwp-public/hwpx/20260723_보도자료_..._교류·협력의_장_마련.hwpx 실측값
    assert _compression_ratio_exceeded(file_size=7_849_954, compress_size=77_670) is False


def test_extreme_ratio_is_still_flagged():
    # 압축 1KB → 해제 100MB (10만 배) 같은 명백한 이상치는 여전히 걸러야 한다
    assert _compression_ratio_exceeded(file_size=100 * 1024 * 1024, compress_size=1024) is True


def test_zero_compress_size_does_not_divide_by_zero():
    assert _compression_ratio_exceeded(file_size=1000, compress_size=0) is False
