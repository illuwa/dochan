"""
quality/cross_validator.py — 3중 교차 검증
소스 A: 우리 HWP/HWPX 파서
소스 B: pdfplumber (PDF → 텍스트)
소스 C: Open Dataloader (PDF → Markdown)

동일 문서의 HWP+PDF 세트를 입력받아 세 소스 간 텍스트를 비교.
"""

import math
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict

from .checker import check_quality
from ..utils.diagnostics import is_fatal_diagnostic


MAX_REFERENCE_TEXT_BYTES = 100 * 1024 * 1024
MAX_REFERENCE_PDF_BYTES = 100 * 1024 * 1024
MAX_REFERENCE_PDF_PAGES = 2_000
MAX_REFERENCE_PDF_TEXT_BYTES = 100 * 1024 * 1024
MAX_REFERENCE_PDF_TABLES = 10_000
MAX_REFERENCE_PDF_TABLE_ROWS = 200_000
MAX_REFERENCE_PDF_TABLE_CELLS = 200_000
MAX_REFERENCE_PDF_TABLE_TEXT_BYTES = 100 * 1024 * 1024
_UTF8_COUNT_CHUNK_CHARS = 64 * 1024


def _bounded_utf8_size(text: str, limit: int) -> Optional[int]:
    """Return the UTF-8 size, or None once *limit* is exceeded.

    Counting in chunks avoids allocating a second, potentially very large,
    encoded copy of untrusted extracted text just to enforce the budget.
    """
    if len(text) > limit:
        # Every Unicode code point occupies at least one byte in UTF-8.
        return None

    total = 0
    for start in range(0, len(text), _UTF8_COUNT_CHUNK_CHARS):
        chunk = text[start:start + _UTF8_COUNT_CHUNK_CHARS]
        total += len(chunk.encode('utf-8'))
        if total > limit:
            return None
    return total


@dataclass
class SourceResult:
    """단일 소스 추출 결과"""
    name: str = ""
    raw_text: str = ""
    clean_text: str = ""  # 정규화된 텍스트
    char_count: int = 0
    table_count: int = 0
    image_count: int = 0
    error: str = ""
    warnings: List[str] = field(default_factory=list)


@dataclass
class PairComparison:
    """두 소스 간 비교"""
    source_a: str = ""
    source_b: str = ""
    bigram_similarity: float = 0.0
    keyword_matches: int = 0
    keyword_total: int = 0
    sentence_coverage: float = 0.0  # B 문장 중 A에 있는 비율
    word_coverage: float = 0.0      # B 단어 중 A에 있는 비율
    length_ratio: float = 0.0       # A/B
    available_metrics: List[str] = field(default_factory=list)


@dataclass
class CrossValidationReport:
    """3중 교차 검증 리포트"""
    file_name: str = ""
    sources: Dict[str, SourceResult] = field(default_factory=dict)
    comparisons: List[PairComparison] = field(default_factory=list)
    missing_in_hwp: List[str] = field(default_factory=list)  # 다른 소스엔 있지만 HWP 파서에 없는 문장
    overall_score: float = 0.0
    verdict: str = ""
    # A report is unavailable until validate() records at least one valid
    # dochan/reference comparison.
    validation_available: bool = False

    def summary(self) -> str:
        lines = [
            f"═══ 교차 검증: {self.file_name} ═══",
            "",
            "── 소스별 추출 결과 ──",
        ]
        for name, src in self.sources.items():
            if src.error:
                lines.append(f"  {name}: 에러 - {src.error}")
            else:
                lines.append(f"  {name}: {src.char_count}자, 표 {src.table_count}개, 이미지 {src.image_count}개")
            for warning in src.warnings:
                lines.append(f"    경고 - {warning}")

        lines.append("")
        lines.append("── 쌍별 비교 ──")
        for comp in self.comparisons:
            available = set(comp.available_metrics)
            similarity = (
                f"{comp.bigram_similarity:.1f}%"
                if 'bigram_similarity' in available else "N/A"
            )
            keywords = (
                f"{comp.keyword_matches}/{comp.keyword_total}"
                if 'keywords' in available else "N/A"
            )
            sentence_coverage = (
                f"{comp.sentence_coverage:.1f}%"
                if 'sentence_coverage' in available else "N/A"
            )
            word_coverage = (
                f"{comp.word_coverage:.1f}%"
                if 'word_coverage' in available else "N/A"
            )
            length_ratio = (
                f"{comp.length_ratio:.0f}%"
                if 'length_ratio' in available else "N/A"
            )
            lines.append(
                f"  {comp.source_a} vs {comp.source_b}: "
                f"유사도 {similarity}, "
                f"키워드 {keywords}, "
                f"문장커버 {sentence_coverage}, "
                f"단어커버 {word_coverage}, "
                f"길이비 {length_ratio}"
            )

        if self.missing_in_hwp:
            lines.append("")
            lines.append(f"── HWP 파서 누락 의심 ({len(self.missing_in_hwp)}건) ──")
            for m in self.missing_in_hwp[:10]:
                lines.append(f"  ✗ {m[:80]}")
            if len(self.missing_in_hwp) > 10:
                lines.append(f"  ... 외 {len(self.missing_in_hwp) - 10}건")

        lines.append("")
        lines.append("── 종합 ──")
        if self.validation_available:
            lines.append(f"  점수: {self.overall_score:.1f}/100")
        else:
            lines.append("  점수: 검증 불가")
        lines.append(f"  판정: {self.verdict}")
        return '\n'.join(lines)


class CrossValidator:
    """3중 교차 검증기"""

    def __init__(self, keywords: Optional[List[str]] = None):
        self.keywords = keywords or []

    def validate(
        self,
        hwpx_path: Optional[str] = None,
        pdf_path: Optional[str] = None,
        odl_output_path: Optional[str] = None,
    ) -> CrossValidationReport:
        """교차 검증 실행"""
        report = CrossValidationReport()
        report.file_name = os.path.basename(hwpx_path or pdf_path or "unknown")

        # 소스 A: 우리 파서
        if hwpx_path:
            report.sources['dochan'] = self._extract_hwp(hwpx_path)

        # 소스 B: pdfplumber
        if pdf_path:
            report.sources['pdfplumber'] = self._extract_pdfplumber(pdf_path)

        # 소스 C: Open Dataloader
        if odl_output_path:
            report.sources['open_dataloader'] = self._extract_odl(odl_output_path)

        # 자동 키워드는 현재 검증에만 사용해 다음 호출로 상태를 누출하지 않는다.
        validation_keywords = list(self.keywords)
        if not validation_keywords:
            validation_keywords = self._auto_extract_keywords({
                name: source
                for name, source in report.sources.items()
                if not source.error and source.clean_text.strip()
            })

        # 쌍별 비교
        source_names = list(report.sources.keys())
        for i in range(len(source_names)):
            for j in range(i + 1, len(source_names)):
                a_name, b_name = source_names[i], source_names[j]
                a_source = report.sources[a_name]
                b_source = report.sources[b_name]
                if a_source.error or b_source.error:
                    continue
                # An empty reference contains no evidence and must not make a
                # validation look available.  An empty dochan result remains
                # comparable so a valid reference produces a fail-closed zero.
                if (
                    (a_name != 'dochan' and not a_source.clean_text.strip())
                    or (b_name != 'dochan' and not b_source.clean_text.strip())
                ):
                    continue
                comp = self._compare_pair(
                    a_source, b_source,
                    a_name, b_name, validation_keywords,
                )
                report.comparisons.append(comp)

        # HWP 파서 누락 분석
        if 'dochan' in report.sources:
            report.missing_in_hwp = self._find_missing_in_hwp(report.sources)

        # 종합 점수
        hwp_comparisons = [
            comparison
            for comparison in report.comparisons
            if 'dochan' in (comparison.source_a, comparison.source_b)
        ]
        report.validation_available = bool(hwp_comparisons)
        if report.validation_available:
            report.overall_score = self._calc_overall_score(report)
            report.verdict = self._judge(report.overall_score)
        else:
            report.overall_score = 0.0
            report.verdict = "검증 불가 — 유효한 dochan 대조 소스 없음"

        return report

    # ── 소스 추출 ──

    def _extract_hwp(self, path: str) -> SourceResult:
        result = SourceResult(name='dochan')
        try:
            from ..reader import Dochan

            reader = Dochan(path, ocr=True)
            result.raw_text = reader.to_markdown()
            result.clean_text = self._normalize(result.raw_text)
            result.char_count = len(result.clean_text)

            quality = check_quality(reader.doc)
            result.table_count = quality.total_tables
            result.image_count = quality.total_images

            fatal_errors = []
            for issue in getattr(reader, 'errors', []) or []:
                issue_text = str(issue)
                if is_fatal_diagnostic(issue_text):
                    fatal_errors.append(issue_text)
                else:
                    result.warnings.append(issue_text)
            if fatal_errors:
                result.error = '; '.join(fatal_errors)
        except Exception as e:
            result.error = str(e)
        return result

    def _extract_pdfplumber(self, path: str) -> SourceResult:
        result = SourceResult(name='pdfplumber')
        try:
            input_size = os.path.getsize(path)
            if input_size > MAX_REFERENCE_PDF_BYTES:
                raise ValueError(
                    "PDF input exceeds the "
                    f"{MAX_REFERENCE_PDF_BYTES}-byte limit"
                )

            import pdfplumber
            page_texts = []
            text_bytes = 0
            table_count = 0
            table_rows = 0
            table_cells = 0
            table_text_bytes = 0
            with pdfplumber.open(path) as pdf:
                page_count = len(pdf.pages)
                if page_count > MAX_REFERENCE_PDF_PAGES:
                    raise ValueError(
                        "PDF page count exceeds the "
                        f"{MAX_REFERENCE_PDF_PAGES}-page limit"
                    )

                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        separator_bytes = 2 if page_texts else 0
                        remaining = (
                            MAX_REFERENCE_PDF_TEXT_BYTES
                            - text_bytes
                            - separator_bytes
                        )
                        extracted_bytes = _bounded_utf8_size(t, remaining)
                        if extracted_bytes is None:
                            raise ValueError(
                                "PDF extracted text exceeds the "
                                f"{MAX_REFERENCE_PDF_TEXT_BYTES}-byte limit"
                            )
                        text_bytes += separator_bytes + extracted_bytes
                        page_texts.append(t)

                    tables = page.extract_tables() or []
                    table_count += len(tables)
                    if table_count > MAX_REFERENCE_PDF_TABLES:
                        raise ValueError(
                            "PDF extracted table count exceeds the "
                            f"{MAX_REFERENCE_PDF_TABLES}-table limit"
                        )
                    for table in tables:
                        rows = table or []
                        table_rows += len(rows)
                        if table_rows > MAX_REFERENCE_PDF_TABLE_ROWS:
                            raise ValueError(
                                "PDF extracted table rows exceed the "
                                f"{MAX_REFERENCE_PDF_TABLE_ROWS}-row limit"
                            )
                        for row in rows:
                            cells = row or []
                            table_cells += len(cells)
                            if table_cells > MAX_REFERENCE_PDF_TABLE_CELLS:
                                raise ValueError(
                                    "PDF extracted table cells exceed the "
                                    f"{MAX_REFERENCE_PDF_TABLE_CELLS}-cell limit"
                                )
                            for cell in cells:
                                if cell is None:
                                    continue
                                cell_text = (
                                    cell if isinstance(cell, str) else str(cell)
                                )
                                remaining = (
                                    MAX_REFERENCE_PDF_TABLE_TEXT_BYTES
                                    - table_text_bytes
                                )
                                cell_bytes = _bounded_utf8_size(
                                    cell_text,
                                    remaining,
                                )
                                if cell_bytes is None:
                                    raise ValueError(
                                        "PDF extracted table text exceeds the "
                                        f"{MAX_REFERENCE_PDF_TABLE_TEXT_BYTES}"
                                        "-byte limit"
                                    )
                                table_text_bytes += cell_bytes

                    result.image_count += len(page.images)

            result.table_count = table_count

            # ★ PDF 머리글/바닥글 반복 제거
            # 3페이지 이상에서 동일한 첫/끝 줄은 머리글/바닥글로 간주
            if len(page_texts) >= 3:
                from collections import Counter
                repeat_threshold = max(2, math.ceil(len(page_texts) * 0.3))
                first_lines = Counter()
                last_lines = Counter()
                for t in page_texts:
                    lines = t.strip().split('\n')
                    if lines:
                        first_lines[lines[0].strip()] += 1
                    if len(lines) > 1:
                        last_lines[lines[-1].strip()] += 1

                header_lines = {line for line, cnt in first_lines.items()
                               if cnt >= repeat_threshold and len(line) > 2}
                footer_lines = {line for line, cnt in last_lines.items()
                               if cnt >= repeat_threshold and len(line) > 2}

                cleaned = []
                for t in page_texts:
                    lines = t.strip().split('\n')
                    if lines and lines[0].strip() in header_lines:
                        lines.pop(0)
                    if lines and lines[-1].strip() in footer_lines:
                        lines.pop()
                    cleaned.append('\n'.join(lines))
                page_texts = cleaned

            result.raw_text = '\n\n'.join(page_texts)
            result.clean_text = self._normalize(result.raw_text)
            result.char_count = len(result.clean_text)
        except Exception as e:
            # Never expose partially extracted data as a successful reference.
            return SourceResult(name='pdfplumber', error=str(e))
        return result

    def _extract_odl(self, path: str) -> SourceResult:
        result = SourceResult(name='open_dataloader')
        try:
            with open(path, 'rb') as f:
                payload = f.read(MAX_REFERENCE_TEXT_BYTES + 1)
            if len(payload) > MAX_REFERENCE_TEXT_BYTES:
                raise ValueError(
                    "Open Dataloader output exceeds the "
                    f"{MAX_REFERENCE_TEXT_BYTES}-byte limit"
                )
            result.raw_text = payload.decode('utf-8')
            result.clean_text = self._normalize(result.raw_text)
            result.char_count = len(result.clean_text)
            # 마크다운에서 표/이미지 수 추출
            result.table_count = result.raw_text.count('\n|') // 3  # 대략
            result.image_count = result.raw_text.count('![')
        except Exception as e:
            result.error = str(e)
        return result

    # ── 비교 ──

    def _compare_pair(self, a: SourceResult, b: SourceResult,
                      a_name: str, b_name: str,
                      keywords: Optional[List[str]] = None) -> PairComparison:
        comp = PairComparison(source_a=a_name, source_b=b_name)

        if a.error or b.error:
            return comp

        active_keywords = self.keywords if keywords is None else keywords
        comp.keyword_total = len(active_keywords)

        if (
            (a_name == 'dochan' and not a.clean_text.strip())
            or (b_name == 'dochan' and not b.clean_text.strip())
        ):
            return comp

        a_stripped = a.clean_text.replace(' ', '')
        b_stripped = b.clean_text.replace(' ', '')

        # bigram 유사도
        comp.bigram_similarity = self._bigram_sim(a_stripped, b_stripped) * 100
        comp.available_metrics.append('bigram_similarity')

        # ★ 단어 수준 커버리지 (표 텍스트 대응)
        a_words = set(re.findall(r'[^\W_]+', a.clean_text, flags=re.UNICODE))
        b_words = set(re.findall(r'[^\W_]+', b.clean_text, flags=re.UNICODE))
        if b_words:
            comp.word_coverage = len(a_words & b_words) / len(b_words) * 100
            comp.available_metrics.append('word_coverage')

        # 키워드 매칭
        comp.keyword_matches = sum(
            1 for kw in active_keywords
            if kw in a.raw_text and kw in b.raw_text
        )
        if active_keywords:
            comp.available_metrics.append('keywords')

        # 문장 커버리지 (B 기준으로 A에 있는지)
        # ★ 유연한 매칭: 15자 키워드 + 페이지번호 제거 + 다중 위치 검색
        b_sents = self._extract_sentences(b.clean_text)
        if b_sents:
            found = 0
            for s in b_sents:
                stripped = s.replace(' ', '')
                # 앞쪽 숫자(페이지번호) 제거
                stripped_no_num = re.sub(r'^\d+', '', stripped)
                # 여러 키 길이로 시도
                matched = False
                for key_src in [stripped, stripped_no_num]:
                    for klen in [20, 15, 12]:
                        key = key_src[:klen]
                        if len(key) >= 8 and key in a_stripped:
                            matched = True
                            break
                    if matched:
                        break
                if matched:
                    found += 1
            comp.sentence_coverage = found / len(b_sents) * 100
            comp.available_metrics.append('sentence_coverage')

        # 길이 비율
        if b.char_count > 0:
            comp.length_ratio = a.char_count / b.char_count * 100
            comp.available_metrics.append('length_ratio')

        return comp

    def _find_missing_in_hwp(self, sources: Dict[str, SourceResult]) -> List[str]:
        """다른 소스에는 있지만 HWP 파서에 없는 문장 찾기"""
        hwp = sources.get('dochan')
        if not hwp or hwp.error:
            return []

        hwp_stripped = hwp.clean_text.replace(' ', '')
        missing = set()

        for name, src in sources.items():
            if name == 'dochan' or src.error:
                continue
            for sent in self._extract_sentences(src.clean_text):
                key = sent.replace(' ', '')[:25]
                if len(key) > 10 and key not in hwp_stripped:
                    missing.add(sent[:100])

        return sorted(missing)

    # ── 점수 ──

    def _calc_overall_score(self, report: CrossValidationReport) -> float:
        if not report.comparisons:
            return 0.0

        # HWP 파서가 포함된 비교만 추출
        hwp_comps = [c for c in report.comparisons if 'dochan' in (c.source_a, c.source_b)]
        if not hwp_comps:
            return 0.0

        # 가중치: 단어커버 30% + bigram 25% + 문장커버 15% + 키워드 15% + 길이비 15%
        scores = []
        metric_weights = {
            'word_coverage': 0.30,
            'bigram_similarity': 0.25,
            'sentence_coverage': 0.15,
            'keywords': 0.15,
            'length_ratio': 0.15,
        }
        for comparison in hwp_comps:
            available = set(comparison.available_metrics)
            # Hand-constructed legacy comparisons predate availability flags;
            # keep their historical all-metrics interpretation.
            if not available:
                available = set(metric_weights)
            values = {
                'word_coverage': comparison.word_coverage,
                'bigram_similarity': comparison.bigram_similarity,
                'sentence_coverage': comparison.sentence_coverage,
                'keywords': (
                    comparison.keyword_matches / comparison.keyword_total * 100
                    if comparison.keyword_total
                    else 0.0
                ),
                'length_ratio': self._length_score(comparison.length_ratio),
            }
            evidence_metrics = available - {'length_ratio'}
            if evidence_metrics and all(values[name] == 0 for name in evidence_metrics):
                # Equal length alone is not evidence that unrelated texts
                # match, so it cannot produce a positive validation score.
                scores.append(0.0)
                continue
            weight = sum(metric_weights[name] for name in available)
            scores.append(
                sum(values[name] * metric_weights[name] for name in available)
                / weight
            )
        return sum(scores) / len(scores)

    @staticmethod
    def _length_score(length_ratio: float) -> float:
        if 75 <= length_ratio <= 200:
            return 100.0
        if length_ratio > 200:
            return max(0.0, 100 - (length_ratio - 200) * 0.5)
        return max(0.0, 100 - (75 - length_ratio) * 1.5)

    def _judge(self, score: float) -> str:
        if score >= 90:
            return "우수 — 프로덕션 사용 가능"
        elif score >= 75:
            return "양호 — 대부분 정확, 일부 개선 필요"
        elif score >= 60:
            return "보통 — 기본 추출 가능, 표/특수요소 개선 필요"
        elif score >= 40:
            return "미흡 — 상당한 누락, 구조 파싱 개선 필요"
        else:
            return "불량 — 근본적 수정 필요"

    # ── 유틸리티 ──

    @staticmethod
    def _normalize(text: str) -> str:
        # Remove markdown formatting completely
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)  # heading markers
        text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', text)  # bold/italic markers
        text = re.sub(r'~~([^~]+)~~', r'\1', text)  # strikethrough
        text = re.sub(r'</?(?:sup|sub|br)>', '', text)  # HTML tags
        text = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', text)  # image refs
        text = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', text)  # links
        text = re.sub(r'[|#*~\-_`\[\]()!<>$^:{}]', '', text)
        text = re.sub(r'image\s*\d+', '', text)  # 이미지 참조 제거
        text = re.sub(r'---+', '', text)  # 마크다운 구분선 제거
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    @staticmethod
    def _bigram_sim(a: str, b: str) -> float:
        if not a or not b:
            return 0.0
        if a == b:
            return 1.0
        a_bg = set(a[i:i+2] for i in range(len(a)-1))
        b_bg = set(b[i:i+2] for i in range(len(b)-1))
        inter = len(a_bg & b_bg)
        union = len(a_bg | b_bg)
        return inter / union if union else 0.0

    @staticmethod
    def _extract_sentences(text: str) -> List[str]:
        # 중복 제거 (PDF 머리글/바닥글 반복 대응)
        seen = set()
        result = []
        for s in re.split(r'[.\n]', text):
            s = s.strip()
            if len(s) > 10:
                key = s.replace(' ', '')[:30]
                if key not in seen:
                    seen.add(key)
                    result.append(s)
        return result

    @staticmethod
    def _auto_extract_keywords(sources: Dict[str, SourceResult]) -> List[str]:
        """가장 긴 소스에서 자동으로 핵심 키워드 추출"""
        best = max(sources.values(), key=lambda s: s.char_count, default=None)
        if not best or not best.raw_text:
            return []

        # Unicode letter/number words keep the metric language-independent.
        words = re.findall(r'[^\W_]+', best.raw_text, flags=re.UNICODE)
        freq = {}
        for w in words:
            if len(w) >= 3:
                freq[w] = freq.get(w, 0) + 1

        # 상위 20개
        top = sorted(freq.items(), key=lambda x: -x[1])[:20]
        return [w for w, _ in top]
