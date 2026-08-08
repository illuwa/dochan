"""PDF 파일 구조 — startxref, 고전 xref 테이블, trailer, 페이지 트리.

xref 스트림(PDF 1.5+)과 객체 스트림은 이번 마일스톤에서 지원하지 않는다.
발견하면 경고를 남기고 `N G obj` 패턴 스캔으로 대체 복구를 시도한다.
"""
import re
from typing import Any, Dict, List, Optional, Tuple

from .filters import decode_stream
from .objects import PDFLexer, PDFRef, PDFStream, PDFSyntaxError, parse_indirect_object

MAX_XREF_SECTIONS = 32
MAX_OBJECTS = 500_000
MAX_PAGES = 10_000
MAX_RESOLVE_DEPTH = 32
MAX_TREE_DEPTH = 64
_SCAN_ROOT_LIMIT = 10_000
# 문서 단위 누적 해제 예산 — 스트림 1개당 한도만으로는 같은 폭탄 스트림을
# 반복 참조하는 40KB PDF 가 수 GB 를 강제할 수 있다 (감수 2차 C2)
MAX_TOTAL_DECODED = 200 * 1024 * 1024

_OBJ_RE = re.compile(rb"(?<!\d)(\d{1,10})\s+(\d{1,5})\s+obj\b")
_ENCRYPT_RE = re.compile(rb"/Encrypt\s+\d+\s+\d+\s+R")


class PDFFile:
    """파싱된 PDF 파일 — 객체 접근과 페이지 트리 순회."""

    def __init__(self, data: bytes):
        self.data = data
        self.warnings: List[str] = []
        self.trailer: Dict[str, Any] = {}
        self.xref: Dict[int, Optional[int]] = {}  # 객체 번호 → 오프셋 (None=삭제됨)
        self.encrypted = False
        self._cache: Dict[int, Any] = {}
        self._rescanned = False
        self._decoded_cache: Dict[int, bytes] = {}
        self._decode_budget = MAX_TOTAL_DECODED
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
        if current is not None and current not in seen:
            self.warnings.append(
                f"WARN: xref 섹션 수가 한도({MAX_XREF_SECTIONS})를 초과 — 오래된 리비전은 무시됨"
            )
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
                if obj_num not in self.xref:
                    # free(f) 엔트리도 tombstone 으로 기록 — 안 하면 증분 갱신에서
                    # 삭제 표시된 객체가 이전 리비전 내용으로 부활한다
                    self.xref[obj_num] = int(off_tok) if kind == b"n" else None

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
        self._recover_trailers()
        objstm_warning = "WARN: 객체 스트림(/ObjStm, PDF 1.5+)은 아직 지원하지 않음 — 일부 객체가 누락될 수 있음"
        if b"/ObjStm" in self.data and objstm_warning not in self.warnings:
            self.warnings.append(objstm_warning)
        if "Root" not in self.trailer:
            self._find_root_by_scan()

    def _recover_trailers(self) -> None:
        """스캔 폴백에서 trailer 사전을 복구한다.

        xref 재구성만 하고 trailer 를 버리면 /Encrypt 를 영영 보지 못해
        암호화 PDF 를 평문처럼 파싱하는 구멍이 생긴다 (감수 M3).
        파일 뒤쪽(최신)부터 복구하고, trailer 키워드가 없는 xref 스트림
        PDF 는 /Encrypt 참조 패턴으로 보수적으로 감지한다.
        """
        pos = len(self.data)
        count = 0
        while count < MAX_XREF_SECTIONS:
            pos = self.data.rfind(b"trailer", 0, pos)
            if pos < 0:
                break
            count += 1
            lexer = PDFLexer(self.data, pos + len(b"trailer"))
            try:
                lexer.skip_whitespace()
                obj = lexer.parse_object()
            except PDFSyntaxError:
                continue
            if isinstance(obj, dict):
                for key, value in obj.items():
                    self.trailer.setdefault(key, value)
        if "Encrypt" not in self.trailer and _ENCRYPT_RE.search(self.data):
            self.trailer["Encrypt"] = True

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

    def decode_stream_bytes(self, stream: PDFStream) -> bytes:
        """스트림을 해제하되 문서 단위 누적 예산과 결과 캐시를 적용한다.

        같은 스트림 객체는 한 번만 해제하고(반복 참조 증폭 방지),
        문서 전체 해제 총량이 MAX_TOTAL_DECODED 를 넘으면 중단한다.
        """
        key = id(stream)
        if key in self._decoded_cache:
            return self._decoded_cache[key]
        if self._decode_budget <= 0:
            msg = "WARN: 문서 스트림 해제 총량 한도 초과 — 이후 스트림은 건너뜀"
            if msg not in self.warnings:
                self.warnings.append(msg)
            return b""
        out = decode_stream(stream.dictionary, stream.raw, self.warnings)
        if len(out) > self._decode_budget:
            out = out[:self._decode_budget]
            self.warnings.append("WARN: 스트림이 문서 해제 총량 한도에 걸려 잘림")
        self._decode_budget -= len(out)
        self._decoded_cache[key] = out
        return out

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
        elif len(result) >= MAX_PAGES:
            self.warnings.append(f"WARN: 페이지 수가 한도({MAX_PAGES})를 초과 — 일부만 파싱")
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
