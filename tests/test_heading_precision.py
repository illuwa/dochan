"""강조 제목의 이름 줄과 진술 줄을 합성 HWP/HWPX로 구분한다."""

import pytest

from test_heading_recall import _documents


@pytest.mark.parametrize('text', [
    '□ (배경) 청년의 취업 준비를 위한 신규 상품 출시',
    '□ (공급목표) 연 2조원씩 5년 간 공급 목표',
    '□ (주요 개편사항) 모양 중심에서 의미 구조 중심으로 전환',
    '■ (추진 방안) 단계별 지원 체계 구축',
    '□ (임의의 새 태그) 분야별 지원 체계 구축',
    '□ 연내 설립 완료 → 내년 첫 사업 추진 목표',
    '□ 공동 추진단을 구성하여 본격 사업 추진',
    '□ 관계기관과 협력하며 신규 서비스 구축',
    '□ 운영 기준을 정비하고 지원 범위 확대',
    '□ 현장 부담을 개선하되 사업 대상 확대',
    '□ ' + '긴 이름 ' * 13,
    '□ ' + '가' * 61,
])
@pytest.mark.parametrize('shape', [2, 1, 3])
def test_square_statement_stays_body_in_both_readers(tmp_path, text, shape):
    # 같은 크기 굵기와 1.1배 미만 크기 강조 모두에서 진술을 제외한다.
    for doc in _documents(tmp_path, [[(text, shape)]]):
        assert doc.sections[0].elements[-1].heading_level == 0
        assert doc.errors == []


@pytest.mark.parametrize('text', [
    '□ 추진배경',
    '□ 세부 프로그램(안)',
    '□ (지정혜택)',
    '□ (주요 개편사항)',
    '□ 은행(첫 5영업일간 온라인 판매 비중 40%, 그 이후는 제한없음)',
    '□ 고소애 가수분해물의 근력 유지 기능성 확인',
    '□ ' + '가' * 60,
    '□ ' + '가' * 29 + ' ' * 10 + '나' * 30,
    '< 주요 내용 >',
    '【 ➊ 현장대기 프로젝트 신속 가동 】',
    'Q.1 제도를 개편하고 다음 절차로 넘어가는지?',
])
def test_section_names_keep_heading_in_both_readers(tmp_path, text):
    for doc in _documents(tmp_path, [[(text, 2)]]):
        assert doc.sections[0].elements[-1].heading_level == 3


def test_statement_filter_preserves_clear_font_hierarchy(tmp_path):
    for doc in _documents(tmp_path, [[('□ (배경) 새로운 사업의 추진 방향', 5)]]):
        assert doc.sections[0].elements[-1].heading_level == 1


def test_single_noun_after_tag_remains_ambiguous(tmp_path):
    # 단일 명사 값과 절 이름은 텍스트만으로 확정하지 않고 기존 계약을 보존한다.
    for doc in _documents(tmp_path, [[('□ (기관) 본부', 1)]]):
        assert doc.sections[0].elements[-1].heading_level == 3
