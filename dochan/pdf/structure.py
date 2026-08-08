"""PDF 파일 구조 — startxref, 고전 xref 테이블, trailer, 페이지 트리.

xref 스트림(PDF 1.5+)과 객체 스트림은 이번 마일스톤에서 지원하지 않는다.
발견하면 경고를 남기고 `N G obj` 패턴 스캔으로 대체 복구를 시도한다.
"""
import re
from typing import Any, Dict, List, Optional, Tuple

from .objects import PDFLexer, PDFRef, PDFSyntaxError, parse_indirect_object

MAX_XREF_SECTIONS = 32
MAX_OBJECTS = 500_000
MAX_PAGES = 10_000
MAX_RESOLVE_DEPTH = 32
MAX_TREE_DEPTH = 64
_SCAN_ROOT_LIMIT = 10_000

_OBJ_RE = re.compile(rb"(?<!\d)(\d{1,10})\s+(\d{1,5})\s+obj\b")


class PDFFile:
    """파싱된 PDF 파일 — 객체 접근과 페이지 트리 순회."""

    def __init__(self, data: bytes):
        self.data = data
        self.warnings: List[str] = []
        self.trailer: Dict[str, Any] = {}
        self.xref: Dict[int, int] = {}  # 객체 번호 → 파일 오프셋
        self.encrypted = False
        self._cache: Dict[int, Any] = {}
        self._rescanned = False
        self._parse_structure()

    # ── 구조 파싱 ──

    def _parse_structure(self) -> None:
        start = self._find_startxref()
        ok = start is not None and self._parse_xref_chain(start)
        if not ok or "Root" not in self.trailer:
            self._scan_objects()
        if self.trailer.get("Encrypt") is not None:
            self.encrypted = True
            self.warnings.append("WARN: 암호화된 PDF — 텍스트 추출을 지원하지 않음")

    def _find_startxref(self) -> Optional[int]:
        tail = self.data[-2048:]
        idx = tail.rfind(b"startxref")
        if idx < 0:
            self.warnings.append("WARN: startxref 를 찾지 못함 — 객체 스캔으로 대체")
            return None
        base = len(self.data) - len(tail)
        lexer = PDFLexer(self.data, base + idx + len(b"startxref"))
        lexer.skip_whitespace()
        token = lexer.read_token()
        if not token.isdigit():
            self.warnings.append("WARN: startxref 오프셋 손상 — 객체 스캔으로 대체")
            return None
        offset = int(token)
        if offset >= len(self.data):
            self.warnings.append("WARN: startxref 오프셋이 파일 범위 밖 — 객체 스캔으로 대체")
            return None
        return offset

    def _parse_xref_chain(self, offset: int) -> bool:
        seen = set()
        current: Optional[int] = offset
        while current is not None and current not in seen and len(seen) < MAX_XREF_SECTIONS:
            seen.add(current)
            lexer = PDFLexer(self.data, current)
            lexer.skip_whitespace()
            if lexer.read_token() != b"xref":
                self.warnings.append(
                    "WARN: xref 스트림(PDF 1.5+)은 아직 지원하지 않음 — 객체 스캔으로 대체"
                )
                return False
            trailer = self._parse_xref_table(lexer)
            if trailer is None:
                return False
            for key, value in trailer.items():
                self.trailer.setdefault(key, value)  # 최신 trailer 우선
            prev = trailer.get("Prev")
            current = prev if isinstance(prev, int) else None
        return True

    def _parse_xref_table(self, lexer: PDFLexer) -> Optional[dict]:
        while True:
            lexer.skip_whitespace()
            token = lexer.read_token()
            if token == b"trailer":
                lexer.skip_whitespace()
                try:
                    obj = lexer.parse_object()
                except PDFSyntaxError:
                    self.warnings.append("WARN: trailer 손상 — 객체 스캔으로 대체")
                    return None
                return obj if isinstance(obj, dict) else None
            if not token.isdigit():
                self.warnings.append("WARN: xref 테이블 손상 — 객체 스캔으로 대체")
                return None
            start_num = int(token)
            lexer.skip_whitespace()
            count_tok = lexer.read_token()
            if not count_tok.isdigit() or int(count_tok) > MAX_OBJECTS:
                self.warnings.append("WARN: xref 테이블 손상 — 객체 스캔으로 대체")
                return None
            for i in range(int(count_tok)):
                lexer.skip_whitespace()
                off_tok = lexer.read_token()
                lexer.skip_whitespace()
                gen_tok = lexer.read_token()
                lexer.skip_whitespace()
                kind = lexer.read_token()
                if not off_tok.isdigit() or not gen_tok.isdigit() or kind not in (b"n", b"f"):
                    self.warnings.append("WARN: xref 항목 손상 — 객체 스캔으로 대체")
                    return None
                obj_num = start_num + i
                if kind == b"n" and obj_num not in self.xref:
                    self.xref[obj_num] = int(off_tok)

    def _scan_objects(self) -> None:
        self.xref = {}
        self._cache = {}
        count = 0
        for match in _OBJ_RE.finditer(self.data):
            # 파일 뒤쪽 정의가 최신(증분 갱신)이므로 덮어쓴다
            self.xref[int(match.group(1))] = match.start()
            count += 1
            if count > MAX_OBJECTS:
                self.warnings.append("WARN: 객체 수가 한도를 초과 — 일부만 파싱")
                break
        if "Root" not in self.trailer:
            self._find_root_by_scan()

    def _find_root_by_scan(self) -> None:
        for num in sorted(self.xref)[:_SCAN_ROOT_LIMIT]:
            try:
                obj = self.get_object(PDFRef(num, 0))
            except Exception:
                continue
            if isinstance(obj, dict) and str(obj.get("Type", "")) == "Catalog":
                self.trailer["Root"] = PDFRef(num, 0)
                return

    # ── 객체 접근 ──

    def get_object(self, ref: PDFRef) -> Any:
        if ref.num in self._cache:
            return self._cache[ref.num]
        offset = self.xref.get(ref.num)
        if offset is None or offset >= len(self.data):
            return None
        self._cache[ref.num] = None  # 순환 참조 가드
        try:
            num, _gen, obj = parse_indirect_object(self.data, offset, resolve=self.resolve)
        except PDFSyntaxError as e:
            self.warnings.append(f"WARN: 객체 {ref.num} 파싱 실패: {e}")
            return None
        if num != ref.num:
            if not self._rescanned:
                self._rescanned = True
                self.warnings.append("WARN: xref 오프셋 불일치 — 객체 스캔으로 재구성")
                self._scan_objects()
                return self.get_object(ref)
            self.warnings.append(f"WARN: 객체 {ref.num} 오프셋이 {num} 을 가리킴")
            return None
        self._cache[ref.num] = obj
        return obj

    def resolve(self, obj: Any, depth: int = 0) -> Any:
        while isinstance(obj, PDFRef):
            if depth > MAX_RESOLVE_DEPTH:
                return None
            obj = self.get_object(obj)
            depth += 1
        return obj

    # ── 페이지 트리 ──

    def pages(self) -> List[Tuple[dict, dict]]:
        """(페이지 사전, 유효 Resources) 목록을 문서 순서대로 반환."""
        root = self.resolve(self.trailer.get("Root"))
        if not isinstance(root, dict):
            self.warnings.append("WARN: PDF 카탈로그(Root)를 찾지 못함")
            return []
        pages_root = self.resolve(root.get("Pages"))
        if not isinstance(pages_root, dict):
            self.warnings.append("WARN: 페이지 트리를 찾지 못함")
            return []
        result: List[Tuple[dict, dict]] = []
        self._walk_pages(pages_root, {}, result, set(), 0)
        if not result:
            self.warnings.append("WARN: 페이지를 찾지 못함")
        return result

    def _walk_pages(self, node: dict, inherited: dict, result, visited, depth) -> None:
        if depth > MAX_TREE_DEPTH or len(result) >= MAX_PAGES:
            return
        node_id = id(node)
        if node_id in visited:
            return
        visited.add(node_id)
        resources = self.resolve(node.get("Resources"))
        effective = resources if isinstance(resources, dict) else inherited
        node_type = str(node.get("Type", ""))
        kids = node.get("Kids")
        if kids is not None and node_type != "Page":
            kids = self.resolve(kids)
            if not isinstance(kids, list):
                return
            for kid_ref in kids:
                kid = self.resolve(kid_ref)
                if isinstance(kid, dict):
                    self._walk_pages(kid, effective, result, visited, depth + 1)
            return
        result.append((node, effective))
