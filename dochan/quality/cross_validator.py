"""
quality/cross_validator.py — 3중 교차 검증
소스 A: 우리 HWP/HWPX 파서
소스 B: pdfplumber (PDF → 텍스트)
소스 C: Open Dataloader (PDF → Markdown)

동일 문서의 HWP+PDF 세트를 입력받아 세 소스 간 텍스트를 비교.
"""

import re
import os
from dataclasses import dataclass, field
from typing import List, Optional, Dict


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


@dataclass
class CrossValidationReport:
    """3중 교차 검증 리포트"""
    file_name: str = ""
    sources: Dict[str, SourceResult] = field(default_factory=dict)
    comparisons: List[PairComparison] = field(default_factory=list)
    missing_in_hwp: List[str] = field(default_factory=list)  # 다른 소스엔 있지만 HWP 파서에 없는 문장
    overall_score: float = 0.0
    verdict: str = ""

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

        lines.append("")
        lines.append("── 쌍별 비교 ──")
        for comp in self.comparisons:
            lines.append(
                f"  {comp.source_a} vs {comp.source_b}: "
                f"유사도 {comp.bigram_similarity:.1f}%, "
                f"키워드 {comp.keyword_matches}/{comp.keyword_total}, "
                f"문장커버 {comp.sentence_coverage:.1f}%, "
                f"길이비 {comp.length_ratio:.0f}%"
            )

        if self.missing_in_hwp:
            lines.append("")
            lines.append(f"── HWP 파서 누락 의심 ({len(self.missing_in_hwp)}건) ──")
            for m in self.missing_in_hwp[:10]:
                lines.append(f"  ✗ {m[:80]}")
            if len(self.missing_in_hwp) > 10:
                lines.append(f"  ... 외 {len(self.missing_in_hwp) - 10}건")

        lines.append("")
        lines.append(f"── 종합 ──")
        lines.append(f"  점수: {self.overall_score:.1f}/100")
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

        # 자동 키워드 추출 (키워드가 비어있으면)
        if not self.keywords:
            self.keywords = self._auto_extract_keywords(report.sources)

        # 쌍별 비교
        source_names = list(report.sources.keys())
        for i in range(len(source_names)):
            for j in range(i + 1, len(source_names)):
                a_name, b_name = source_names[i], source_names[j]
                comp = self._compare_pair(
                    report.sources[a_name], report.sources[b_name],
                    a_name, b_name,
                )
                report.comparisons.append(comp)

        # HWP 파서 누락 분석
        if 'dochan' in report.sources:
            report.missing_in_hwp = self._find_missing_in_hwp(report.sources)

        # 종합 점수
        report.overall_score = self._calc_overall_score(report)
        report.verdict = self._judge(report.overall_score)

        return report

    # ── 소스 추출 ──

    def _extract_hwp(self, path: str) -> SourceResult:
        result = SourceResult(name='dochan')
        try:
            from ..reader import Dochan
            from ..model.table import Table
            from ..model.image import Image

            reader = Dochan(path, ocr=True)
            result.raw_text = reader.to_markdown()
            result.clean_text = self._normalize(result.raw_text)
            result.char_count = len(result.clean_text)

            for s in reader.doc.sections:
                for e in s.elements:
                    if isinstance(e, Table):
                        result.table_count += 1
                    elif isinstance(e, Image):
                        result.image_count += 1
        except Exception as e:
            result.error = str(e)
        return result

    def _extract_pdfplumber(self, path: str) -> SourceResult:
        result = SourceResult(name='pdfplumber')
        try:
            import pdfplumber
            pdf = pdfplumber.open(path)
            page_texts = []
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    page_texts.append(t)
                result.table_count += len(page.extract_tables())
                result.image_count += len(page.images)

            # ★ PDF 머리글/바닥글 반복 제거
            # 3페이지 이상에서 동일한 첫/끝 줄은 머리글/바닥글로 간주
            if len(page_texts) >= 3:
                from collections import Counter
                first_lines = Counter()
                last_lines = Counter()
                for t in page_texts:
                    lines = t.strip().split('\n')
                    if lines:
                        first_lines[lines[0].strip()] += 1
                    if len(lines) > 1:
                        last_lines[lines[-1].strip()] += 1

                header_lines = {line for line, cnt in first_lines.items()
                               if cnt >= len(page_texts) * 0.3 and len(line) > 2}
                footer_lines = {line for line, cnt in last_lines.items()
                               if cnt >= len(page_texts) * 0.3 and len(line) > 2}
                # Also remove standalone page numbers
                footer_lines.update(line for line, cnt in last_lines.items()
                                    if re.match(r'^\d{1,3}$', line.strip()))

                cleaned = []
                for t in page_texts:
                    lines = t.strip().split('\n')
                    lines = [l for l in lines
                            if l.strip() not in header_lines
                            and l.strip() not in footer_lines]
                    cleaned.append('\n'.join(lines))
                page_texts = cleaned

            result.raw_text = '\n\n'.join(page_texts)
            result.clean_text = self._normalize(result.raw_text)
            result.char_count = len(result.clean_text)
            pdf.close()
        except Exception as e:
            result.error = str(e)
        return result

    def _extract_odl(self, path: str) -> SourceResult:
        result = SourceResult(name='open_dataloader')
        try:
            with open(path, 'r', encoding='utf-8') as f:
                result.raw_text = f.read()
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
                      a_name: str, b_name: str) -> PairComparison:
        comp = PairComparison(source_a=a_name, source_b=b_name)

        if a.error or b.error:
            return comp

        a_stripped = a.clean_text.replace(' ', '')
        b_stripped = b.clean_text.replace(' ', '')

        # bigram 유사도
        comp.bigram_similarity = self._bigram_sim(a_stripped, b_stripped) * 100

        # ★ 단어 수준 커버리지 (표 텍스트 대응)
        a_words = set(re.findall(r'[가-힣]{2,}', a.clean_text))
        b_words = set(re.findall(r'[가-힣]{2,}', b.clean_text))
        if b_words:
            comp.word_coverage = len(a_words & b_words) / len(b_words) * 100
        else:
            comp.word_coverage = 100.0

        # 키워드 매칭
        comp.keyword_total = len(self.keywords)
        comp.keyword_matches = sum(
            1 for kw in self.keywords
            if (kw in a.raw_text) == (kw in b.raw_text)
        )

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

        # 길이 비율
        if b.char_count > 0:
            comp.length_ratio = a.char_count / b.char_count * 100

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
        avg_sim = sum(c.bigram_similarity for c in hwp_comps) / len(hwp_comps)
        avg_sent_cov = sum(c.sentence_coverage for c in hwp_comps) / len(hwp_comps)
        avg_word_cov = sum(c.word_coverage for c in hwp_comps) / len(hwp_comps)
        avg_kw = sum(
            c.keyword_matches / max(c.keyword_total, 1) * 100
            for c in hwp_comps
        ) / len(hwp_comps)

        # 길이비 적정성: 75~200%면 100점 (OCR로 길이 증가 허용)
        avg_len_ratio = sum(c.length_ratio for c in hwp_comps) / len(hwp_comps)
        if 75 <= avg_len_ratio <= 200:
            len_score = 100.0
        elif avg_len_ratio > 200:
            len_score = max(0, 100 - (avg_len_ratio - 200) * 0.5)
        else:
            len_score = max(0, 100 - (75 - avg_len_ratio) * 1.5)

        return (avg_word_cov * 0.30 + avg_sim * 0.25 + avg_sent_cov * 0.15 +
                avg_kw * 0.15 + len_score * 0.15)

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

        # 한글 2글자 이상 단어 빈도
        words = re.findall(r'[가-힣]{2,}', best.raw_text)
        freq = {}
        for w in words:
            if len(w) >= 3:
                freq[w] = freq.get(w, 0) + 1

        # 상위 20개
        top = sorted(freq.items(), key=lambda x: -x[1])[:20]
        return [w for w, _ in top]
