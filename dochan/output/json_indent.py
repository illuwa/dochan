"""
output/json_indent.py — 들여쓰기 JSON 직렬화 (전 형식 공용 출력 경로)

계약: 어떤 입력에서도 `json.dumps(obj, ensure_ascii=False, indent=indent)` 와
결과가 같다. 문자열은 바이트 단위로 같고, 표준 라이브러리가 예외를 내는 입력은
같은 예외를 낸다.

CPython 3.12 이하는 `indent` 를 주면 C 인코더를 쓰지 않고 토큰마다 중첩 깊이만큼
제너레이터를 거치는 순수 Python 경로(`json.encoder._make_iterencode`)로 떨어진다.
표가 큰 문서에서는 이 직렬화가 파싱보다 오래 걸린다. 여기서는 같은 판별 순서를
재귀 함수 하나로 풀어 쓴다. C 인코더가 들여쓰기를 직접 내는 인터프리터(3.13+)에서는
표준 라이브러리가 더 빠르므로 그대로 위임한다.
"""

import json
from json.encoder import encode_basestring as _encode_str

_INF = float("inf")
_NONE_TYPE = type(None)
_CONTAINERS = (list, tuple, dict)
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


class _Unsupported(Exception):
    """자체 직렬화기가 다루지 않는 값 — 표준 라이브러리에 판단을 넘긴다."""


def stdlib_fallbacks() -> int:
    """자체 직렬화기가 표준 라이브러리로 물러난 횟수 (진단용)."""
    return _fallbacks


def dumps(payload, indent=2) -> str:
    """`json.dumps(payload, ensure_ascii=False, indent=indent)` 와 같은 결과를 낸다."""
    if indent is None or STDLIB_INDENT_IS_NATIVE:
        return json.dumps(payload, ensure_ascii=False, indent=indent)
    try:
        return dumps_indented(payload, indent)
    except Exception:
        # 지원하지 않는 값·키, 순환 참조, 잘못된 indent — 무엇이든 표준 라이브러리가
        # 같은 입력에서 내는 결과(또는 예외)를 그대로 돌려준다.
        global _fallbacks
        _fallbacks += 1
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
    raise _Unsupported


def dumps_indented(payload, indent) -> str:
    """들여쓰기 JSON 을 직접 조립한다. 다루지 않는 값은 `_Unsupported` 로 알린다.

    정확한 내장 타입은 바로 분기하고, 상속 타입(str·int·float 하위 클래스, tuple,
    dict 하위 클래스)은 표준 라이브러리와 같은 isinstance 순서로 처리한다.
    """
    unit = indent if isinstance(indent, str) else " " * indent
    pads = ["\n"]          # pads[깊이] = 줄바꿈 + 그 깊이의 들여쓰기
    out = []
    append = out.append
    prefixes = {}          # 키 문자열 → '"키": ' (같은 키가 수백만 번 반복된다)
    get_prefix = prefixes.get
    int_text = int.__repr__
    float_text = _float_text

    def walk(value, depth):
        depth += 1
        if depth >= len(pads):
            pads.append("\n" + unit * depth)
        pad = pads[depth]
        if isinstance(value, dict):
            if not value:
                append("{}")
                return
            lead = "{" + pad
            sep = "," + pad
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
                elif kind is dict or kind is list:
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
                        raise _Unsupported
                lead = sep
            append(pads[depth - 1] + "}")
        else:
            if not value:
                append("[]")
                return
            lead = "[" + pad
            sep = "," + pad
            for item in value:
                kind = type(item)
                if kind is dict or kind is list:
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
                        raise _Unsupported
                lead = sep
            append(pads[depth - 1] + "]")

    text = _scalar_text(payload)
    if text is not None:
        return text
    if not isinstance(payload, _CONTAINERS):
        raise _Unsupported
    walk(payload, 0)
    return "".join(out)
