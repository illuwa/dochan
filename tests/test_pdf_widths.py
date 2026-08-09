"""PDF 폰트 글리프 폭 맵 테스트."""
from dochan.pdf.widths import WidthMap


def test_simple_font_widths_from_array():
    # FirstChar 65 (A), Widths [500, 600, 700] → A=500, B=600, C=700
    wm = WidthMap.simple(first_char=65, widths=[500, 600, 700], default=250)
    assert wm.advance(ord("A")) == 500
    assert wm.advance(ord("C")) == 700
    assert wm.advance(ord("Z")) == 250  # 배열 밖 → 기본폭


def test_cid_font_widths_from_w_array():
    # /W [ 1 [300 400] 10 20 500 ] → CID1=300, CID2=400, CID10..20=500
    wm = WidthMap.cid(w_array=[1, [300, 400], 10, 20, 500], default_width=1000)
    assert wm.advance(1) == 300
    assert wm.advance(2) == 400
    assert wm.advance(10) == 500
    assert wm.advance(20) == 500
    assert wm.advance(5) == 1000  # 정의 안 됨 → DW


def test_empty_width_map_uses_default():
    wm = WidthMap.simple(first_char=0, widths=[], default=500)
    assert wm.advance(65) == 500
