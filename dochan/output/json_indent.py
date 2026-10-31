"""
output/json_indent.py — 들여쓰기 JSON 직렬화 (전 형식 공용 출력 경로)

계약: 어떤 입력에서도 `json.dumps(obj, ensure_ascii=False, indent=indent)` 와
결과가 같다. 문자열은 바이트 단위로 같고, 표준 라이브러리가 예외를 내는 입력은
같은 예외를 낸다.

CPython 3.12 이하는 `indent` 를 주면 C 인코더를 쓰지 않고 토큰마다 중첩 깊이만큼
제너레이터를 거치는 순수 Python 경로(`json.encoder._make_iterencode`)로 떨어진다.
표가 큰 문서에서는 이 직렬화가 파싱보다 오래 걸린다. 여기서는 같은 판별 순서를
재귀 함수 하나로 풀어 쓴다. C 인코더가 들여쓰기를 직접 내는 인터프리터(3.13+)에서는
문자열 반환은 표준 라이브러리에 위임한다. 파일 출력은 버전과 관계없이 지연 목록을
직접 순회하여 전체 결과 문자열을 만들지 않는다.
"""

import json
from json.encoder import encode_basestring as _encode_str

_INF = float("inf")
_NONE_TYPE = type(None)
_CONTAINERS = (list, tuple, dict)
# 지연 목록의 항목을 하나 쓴 뒤 쌓인 조각이 이보다 많으면 한 문자열로 합친다.
# 조각마다 붙는 str 객체 머리(약 50바이트)가 큰 표에서 본문만큼 메모리를 쓴다.
_COMPACT_AFTER = 4096
_fallbacks = 0


def _probe_native_indent() -> bool:
    """표준 라이브러리의 C 인코더가 들여쓰기를 직접 내는지 동작으로 확인한다."""
    make = getattr(json.encoder, "c_make_encoder", None)
    if make is None:
        return False
    try:
        chunks = make(None, None, _encode_str, " ", ": ", ",", False, False, True)([0], 0)
        return "\n" in "".join(chunks)
    except Exception:
        return False


STDLIB_INDENT_IS_NATIVE = _probe_native_indent()


class Stream:
    """길이를 아는 지연 목록 — 직렬화기가 항목을 하나씩 받아 쓰고 버린다.

    문서 전체를 dict 트리로 한꺼번에 만들지 않고도 목록과 같은 JSON 을 낸다.
    `count` 는 `items` 가 낼 항목 수와 같아야 한다(빈 목록은 `[]` 로 적어야 하므로
    첫 항목을 받기 전에 알아야 한다). 표준 라이브러리는 이 타입을 모르므로
    `dumps_indented` 또는 `dump` 에 넘긴다.
    """

    __slots__ = ("items", "count")

    def __init__(self, items, count):
        self.items = items
        self.count = count


def stdlib_fallbacks() -> int:
    """자체 직렬화기가 표준 라이브러리로 물러난 횟수 (진단용)."""
    return _fallbacks


def count_fallback() -> None:
    """호출 쪽이 지연 직렬화를 포기하고 전체 dict 경로로 물러났음을 기록한다."""
    global _fallbacks
    _fallbacks += 1


def dumps(payload, indent=2) -> str:
    """`json.dumps(payload, ensure_ascii=False, indent=indent)` 와 같은 결과를 낸다."""
    if indent is None or STDLIB_INDENT_IS_NATIVE:
        return json.dumps(payload, ensure_ascii=False, indent=indent)
    try:
        return dumps_indented(payload, indent)
    except Exception:
        # 지원하지 않는 값·키, 순환 참조, 잘못된 indent — 무엇이든 표준 라이브러리가
        # 같은 입력에서 내는 결과(또는 예외)를 그대로 돌려준다.
        count_fallback()
        return json.dumps(payload, ensure_ascii=False, indent=indent)


def _float_text(value) -> str:
    if value != value:
        return "NaN"
    if value == _INF:
        return "Infinity"
    if value == -_INF:
        return "-Infinity"
    return float.__repr__(value)


def _scalar_text(value):
    """표준 라이브러리와 같은 순서로 스칼라를 판별한다. 스칼라가 아니면 None."""
    if isinstance(value, str):
        return _encode_str(value)
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return int.__repr__(value)
    if isinstance(value, float):
        return _float_text(value)
    return None


def _key_text(key) -> str:
    if isinstance(key, str):
        return _encode_str(key)
    if isinstance(key, float):
        return _encode_str(_float_text(key))
    if key is True:
        return '"true"'
    if key is False:
        return '"false"'
    if key is None:
        return '"null"'
    if isinstance(key, int):
        return _encode_str(int.__repr__(key))
    raise TypeError(
        f'keys must be str, int, float, bool or None, not {key.__class__.__name__}'
    )


def dump(payload, fp, indent=2) -> None:
    """Write JSON incrementally. A failed write may leave partial output in fp.

    Stream payloads use the same walker on every Python version;
    unlike dumps, this path never accumulates the final result string.
    """
    dumps_indented(payload, indent, _fp=fp)


def dumps_indented(payload, indent, _fp=None) -> str:
    """들여쓰기 JSON 을 조립하거나 파일에 쓴다. 잘못된 값은 표준 JSON 예외로 알린다.

    정확한 내장 타입은 바로 분기하고, 상속 타입(str·int·float 하위 클래스, tuple,
    dict 하위 클래스)은 표준 라이브러리와 같은 isinstance 순서로 처리한다.
    `Stream` 은 목록과 똑같이 적되 항목을 하나씩 받아 쓴다.
    """
    unit = "" if indent is None else (indent if isinstance(indent, str) else " " * indent)
    newline = "" if indent is None else "\n"
    pads = [newline]          # pads[깊이] = 줄바꿈 + 그 깊이의 들여쓰기
    out = []
    if _fp is None:
        append = out.append
    else:
        size = 0

        def append(chunk):
            nonlocal size
            out.append(chunk)
            size += len(chunk)
            if size >= 65536:
                _fp.write("".join(out))
                out.clear()
                size = 0
    prefixes = {}          # 키 문자열 → '"키": ' (같은 키가 수백만 번 반복된다)
    get_prefix = prefixes.get
    int_text = int.__repr__
    float_text = _float_text
    tail = 0               # out[tail:] 이 아직 합치지 않은 조각들

    active = set()

    def walk(value, depth):
        identity = id(value)
        if identity in active:
            raise ValueError("Circular reference detected")
        active.add(identity)
        try:
            return walk_container(value, depth)
        finally:
            active.remove(identity)

    def walk_container(value, depth):
        nonlocal tail
        depth += 1
        if depth >= len(pads):
            pads.append(newline + unit * depth)
        pad = pads[depth]
        if isinstance(value, dict):
            if not value:
                append("{}")
                return
            lead = "{" + pad
            sep = ", " if indent is None else "," + pad
            for key, item in value.items():
                prefix = get_prefix(key)
                if prefix is None or type(key) is not str:
                    # 1 과 True 처럼 값이 같은 키가 섞이지 않게 정확한 str 만 캐시한다
                    prefix = _key_text(key) + ": "
                    if type(key) is str:
                        prefixes[key] = prefix
                kind = type(item)
                if kind is str:
                    append(lead + prefix + _encode_str(item))
                elif kind is bool:
                    append(lead + prefix + ("true" if item else "false"))
                elif kind is int:
                    append(lead + prefix + int_text(item))
                elif kind is dict or kind is list or kind is Stream:
                    append(lead + prefix)
                    walk(item, depth)
                elif kind is float:
                    append(lead + prefix + float_text(item))
                elif kind is _NONE_TYPE:
                    append(lead + prefix + "null")
                else:
                    text = _scalar_text(item)
                    if text is not None:
                        append(lead + prefix + text)
                    elif isinstance(item, _CONTAINERS):
                        append(lead + prefix)
                        walk(item, depth)
                    else:
                        json.dumps(item, ensure_ascii=False)
                lead = sep
            append(pads[depth - 1] + "}")
        else:
            lazy = type(value) is Stream
            if lazy:
                if not value.count:
                    append("[]")
                    return
                value = value.items
            elif not value:
                append("[]")
                return
            lead = "[" + pad
            sep = ", " if indent is None else "," + pad
            for item in value:
                kind = type(item)
                if kind is dict or kind is list or kind is Stream:
                    append(lead)
                    walk(item, depth)
                elif kind is str:
                    append(lead + _encode_str(item))
                elif kind is bool:
                    append(lead + ("true" if item else "false"))
                elif kind is int:
                    append(lead + int_text(item))
                elif kind is float:
                    append(lead + float_text(item))
                elif kind is _NONE_TYPE:
                    append(lead + "null")
                else:
                    text = _scalar_text(item)
                    if text is not None:
                        append(lead + text)
                    elif isinstance(item, _CONTAINERS):
                        append(lead)
                        walk(item, depth)
                    else:
                        json.dumps(item, ensure_ascii=False)
                lead = sep
                if _fp is None and lazy and len(out) - tail > _COMPACT_AFTER:
                    merged = "".join(out[tail:])
                    del out[tail:]
                    append(merged)
                    tail = len(out)
            append(pads[depth - 1] + "]")

    if _fp is None:
        walk = walk_container

    text = _scalar_text(payload)
    if text is not None:
        if _fp is not None:
            _fp.write(text)
            return
        return text
    if not isinstance(payload, _CONTAINERS) and type(payload) is not Stream:
        json.dumps(payload, ensure_ascii=False)
    walk(payload, 0)
    if _fp is not None:
        if out:
            _fp.write("".join(out))
        return
    return "".join(out)
