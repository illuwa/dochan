"""HWP/HWPX의 개요 정보 없는 문단에 쓰는 공통 글꼴 제목 규칙."""

import re
import unicodedata
from collections import Counter


MAX_FONT_HEADING_PARAGRAPHS = 200_000
MAX_FONT_HEADING_LENGTH = 120
# 네모 표지는 이름뿐 아니라 길게 축약한 본문에도 쓰인다. 약한 글꼴
# 강조로 승격할 이름 줄은 별도 상한을 둔다(문답·괄호 제목에는 적용하지 않음).
MAX_SQUARE_HEADING_LENGTH = 60
_BODY_EXCLUDED_PREFIXES = ('※', '*', '주:', '(단위')
# 표·그림 캡션과 차례 항목 스타일은 이름에 '제목'이 있어도 제목이 아니다.
# 표지(표지 제목)·별표(별표제목)·양식(양식제목)·차례 쪽 제목(차례 제목)은 실제 제목이라 남긴다.
_NONHEADING_STYLE = re.compile(
    r'(?<![별대])표\s*제목|통계표|도표|표안|그림|캡션|(?:차례|목차)\D{0,6}\d|(?:차례|목차)\s*(?:개요|\()')
_OUTLINE_STYLE = re.compile(r'(?:개요|outline|heading)\s*(\d+)')
# 표지 뒤에는 공백이나 여는 괄호가 와야 한다. 소수·백분율의 점은 번호가 아니다.
# 한글 표지는 실제 순번에 쓰는 14음절만 허용한다.
_NUMBER_MARKER = re.compile(r'(?:\d+(?:-\d+)?|[가나다라마바사아자차카타파하]|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+|[IVX]+)[.)](?=\s|[<〈\[【])')
_QUESTION_MARKER = re.compile(r'Q(?:\.\d+|\s+\d+\.)(?=\s)')
_KEY_VALUE_MARKER = re.compile(r'^□\s*\(([^()]{1,15})\)(?=\s|$)')
_SQUARE_TAG_CONTENT = re.compile(r'^\([^()]+\)\s*(\S.*)$')
# 어휘별 예외 대신 절을 이어 주는 연결 어미를 확인한다.
_SQUARE_CLAUSE = re.compile(r'\S+(?:하여|하며|하고|하되)(?=\s)')
_BRACKET_END = {'<': '>', '〈': '〉', '[': ']', '【': '】'}
# 종결형·날짜·표 캡션은 표지와 강조가 있어도 절 제목으로 보지 않는다.
_SENTENCE_END = re.compile(r'(?:다\.|음\.?|함\.?)$')
_TABLE_LABEL = re.compile(r'(?:표|그림)\s*\d+[.)]')
_DATE_LINE = re.compile(r'\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.\s*$')
# 두 리더가 별도 런으로 붙이는 모델 출력 표지만 판정에서 제거한다.
_BOOKMARK_RUN = re.compile(r'\[bookmark: [^\]\r\n]+\] ')


def _content_runs(runs):
    """리더가 붙인 참조·책갈피 표지를 제목 서식 판정에서 제외한다."""
    return [run for run in runs if run.equation is None and not run.note_ref
            and not run.note_reference_type
            and not _BOOKMARK_RUN.fullmatch(run.text)]


def is_nonheading_style_name(name):
    """캡션·차례 항목 스타일 이름인지 확인한다."""
    return bool(_NONHEADING_STYLE.search(name or ''))


def heading_level_from_style_name(name):
    """두 한글 형식에 공통인 개요·제목 스타일 이름 규칙."""
    name = (name or '').lower()
    # 캡션·차례·양식의 이름에 '제목'이 포함되어도 문서 제목은 아니다.
    # 명시적 개요와 글꼴 폴백은 호출자가 별도로 판정한다.
    if is_nonheading_style_name(name):
        return 0
    outline = _OUTLINE_STYLE.search(name)
    if outline:
        # 번호 그대로 돌려준다 — 호출자가 4 이상을 '명시된 본문'으로 처리한다(글꼴 폴백 없음).
        # '사업개요' 처럼 번호 없는 이름은 개요 스타일이 아니다.
        level = int(outline.group(1))
        return level if level >= 1 else 0
    if name.startswith(('부제목', 'subtitle')):
        return 2
    if '제목' in name or 'title' in name:
        return 1
    return 0


def first_visible_font_size(runs):
    """공백뿐인 선행 런을 건너뛴 첫 글자 런의 포인트 크기."""
    for run in _content_runs(runs):
        if run.text.strip():
            return run.font_size_pt
    return 0


def _sample_exclusions(doc):
    """본문 추정에서만 제외할 중첩 문단 ID를 모은다."""
    if doc is None:
        return None, set()
    reachable = {id(para) for para in doc.find_all('paragraph')}
    excluded = set()
    for kind in ('header_footer', 'note'):
        for container in doc.find_all(kind):
            excluded.update(id(para) for para in container.paragraphs)
    for kind in ('table', 'image'):
        for container in doc.find_all(kind):
            excluded.update(id(para) for para in container.caption)
    return reachable, excluded


def body_font_size(paragraphs, doc=None):
    """문단 길이 가중 최빈 글꼴 크기. 빈약한 표본에는 0을 반환한다."""
    weights = Counter()
    count = 0
    reachable, excluded = _sample_exclusions(doc)
    for para in paragraphs:
        if para is None or id(para) in excluded or getattr(para, '_heading_caption', False):
            continue
        if reachable is not None and id(para) not in reachable:
            continue
        content_runs = _content_runs(para.runs)
        text = ''.join(run.text for run in content_runs).strip()
        if not text:
            continue
        if text.startswith(_BODY_EXCLUDED_PREFIXES):
            continue
        size = first_visible_font_size(content_runs)
        if size <= 0:
            continue
        count += 1
        weights[round(size, 1)] += min(len(text), 200)
    if count < 3 or sum(weights.values()) < 40:
        return 0
    return min(weights, key=lambda size: (-weights[size], size))


def relative_heading_level(runs, body_size):
    """본문 크기보다 뚜렷이 큰 첫 글자 런만 H1~H3로 판정한다."""
    content_runs = _content_runs(runs)
    size = first_visible_font_size(content_runs)
    text = ''.join(run.text for run in content_runs).strip()
    if len(text) > MAX_FONT_HEADING_LENGTH or text.startswith(_BODY_EXCLUDED_PREFIXES):
        # 주석(※·*·주:)·단위 줄은 글꼴이 커도 제목이 아니다.
        return 0
    if body_size <= 0 or size <= 0:
        return 0
    ratio = size / body_size
    if ratio >= 1.5:
        return 1
    if ratio >= 1.25:
        return 2
    if ratio >= 1.1:
        return 3
    return 0


def _section_marker(text):
    """절 표지의 길이와 종류. 괄호형은 줄 전체를 감싸야 한다."""
    if text.startswith(('□', '■')):
        return 1, 'square'
    if text.startswith(('▶ ', '▷ ', '◆ ', '◇ ')):
        return 1, 'symbol'
    if text.startswith('>> '):
        return 2, 'symbol'
    question = _QUESTION_MARKER.match(text)
    if question:
        return question.end(), 'question'
    match = _NUMBER_MARKER.match(text)
    if match:
        return match.end(), 'number'
    closing = _BRACKET_END.get(text[:1])
    if closing and text.endswith(closing) and len(text) > 2:
        return 1, 'bracket'
    # 한컴 도형 글머리는 Unicode Private Use 영역의 한 글자로 시작한다.
    if text and unicodedata.category(text[0]) == 'Co':
        return 1, 'pua'
    return 0, ''


def _context_exclusions(doc):
    """표 직전 캡션과 같은 문단 모양의 연속된 괄호 키 목록을 찾는다."""
    captions = set()
    key_values = set()
    if doc is None:
        return captions, key_values

    def finish_keys(group):
        if len(group) >= 2 and any(key in ('일시', '장소') for _, key in group):
            key_values.update(id(para) for para, _ in group)

    for section in doc.sections:
        elements = section.elements
        group = []
        group_shape = -1
        for index, element in enumerate(elements):
            paragraph = hasattr(element, 'heading_level')
            text = ''.join(run.text for run in _content_runs(element.runs)).strip() if paragraph else ''
            if paragraph:
                shapes = doc.para_shapes
                shape_id = element.para_shape_id
                centered = (0 <= shape_id < len(shapes) and shapes[shape_id].align == 3)
                if (text[:1] in _BRACKET_END and len(text) <= MAX_FONT_HEADING_LENGTH
                        and text.endswith(_BRACKET_END[text[0]])
                        and centered
                        and index + 1 < len(elements)
                        and hasattr(elements[index + 1], 'rows')):
                    captions.add(id(element))
            match = _KEY_VALUE_MARKER.match(text) if paragraph else None
            if match:
                if group and element.para_shape_id != group_shape:
                    finish_keys(group)
                    group = []
                if not group:
                    group_shape = element.para_shape_id
                group.append((element, match.group(1)))
            elif group and (hasattr(element, 'rows')
                            or text.startswith(('ㅇ ', '○ ', '◦ '))):
                continue
            else:
                finish_keys(group)
                group = []
        # 날짜·장소 값을 가진 묶음만 값 목록으로 본다. 중간의 ㅇ 하위 값과
        # 표는 허용하되, 다른 본문 문단이나 네모 절은 묶음을 끊는다.
        finish_keys(group)
    return captions, key_values


def emphasized_heading_level(runs, body_size):
    """본문 크기와 비슷한, 절 표지와 시각 강조가 함께 있는 줄만 H3으로 올린다."""
    runs = _content_runs(runs)
    raw_text = ''.join(run.text for run in runs)
    text = raw_text.strip()
    if (not text or len(text) > MAX_FONT_HEADING_LENGTH
            or text.startswith(('※', '*', '(단위'))
            or '\n' in text or '\r' in text or ':' in text or '：' in text
            or _SENTENCE_END.search(text) or _DATE_LINE.fullmatch(text)):
        return 0
    marker_end, kind = _section_marker(text)
    if not marker_end or (kind == 'square' and _TABLE_LABEL.match(text[marker_end:].strip())):
        return 0
    if kind == 'square':
        name = ' '.join(text[marker_end:].split())
        tag = _SQUARE_TAG_CONTENT.match(name)
        # 태그만 있는 이름과 뒤에 단일 명사가 오는 애매한 줄은 보존한다.
        # 두 어절 이상 값·설명이 붙으면 태그는 절 이름이 아니라 본문 분류다.
        if (len(name) > MAX_SQUARE_HEADING_LENGTH
                or (tag and len(tag.group(1).split()) >= 2)
                or '→' in name or _SQUARE_CLAUSE.search(name)):
            return 0
    # 앞 공백과 표지는 글자 크기·굵기 판정에서 뺀다. 특히 HWP의 PUA
    # 글머리 글자만 작고 뒤의 실제 제목은 큰 경우가 있다.
    leading = len(raw_text) - len(raw_text.lstrip())
    start = leading + marker_end
    first_size = 0
    all_bold = True
    content = 0
    position = 0
    for run in runs:
        for char in run.text:
            if position >= start and not char.isspace() and char not in _BRACKET_END.values():
                if not first_size:
                    first_size = run.font_size_pt
                all_bold = all_bold and run.bold
                content += 1
            position += 1
    if not content or body_size <= 0:
        return 0
    # 본문 최빈 크기는 0.1pt 단위로 집계하므로 후보도 같은 단위로 비교한다.
    first_size = round(first_size, 1)
    if first_size > body_size:
        return 3
    # 번호·PUA 표지는 독립적인 굵기 강조가 아니라 목록 기호로도 쓰인다.
    # 따라서 두 종류는 크기가 커진 경우에만 올린다.
    if kind not in ('pua', 'number') and first_size >= body_size and all_bold:
        return 3
    return 0


def finalize_font_headings(paragraphs, doc=None):
    """본문 크기를 추정할 수 있는 문서만 글꼴 폴백을 다시 계산한다."""
    paragraphs = tuple(paragraphs)
    if any(para is None for para in paragraphs):
        # 한도 뒤 문단은 고정 기준으로 읽었다. 앞부분도 그대로 두어
        # 하나의 문서 안에서 서로 다른 제목 기준을 쓰지 않는다.
        return 0
    body_size = body_font_size(paragraphs, doc=doc)
    if body_size:
        caption_exclusions, key_value_exclusions = _context_exclusions(doc)
        top_level = ({id(para) for section in doc.sections for para in section.elements
                      if hasattr(para, 'heading_level')} if doc is not None else set())
        for para in paragraphs:
            if getattr(para, '_heading_caption', False) or id(para) in key_value_exclusions:
                para.heading_level = 0
                continue
            level = relative_heading_level(para.runs, body_size)
            if id(para) in caption_exclusions and level not in (1, 2):
                level = 0
            elif not level and id(para) in top_level:
                level = emphasized_heading_level(para.runs, body_size)
            para.heading_level = level
    return body_size
