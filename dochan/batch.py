"""
batch.py — 배치 처리
다수 HWP 파일의 병렬 변환
"""

import os
import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

logger = logging.getLogger('dochan')


@dataclass
class BatchResult:
    """단일 파일 처리 결과"""
    file_path: str = ""
    success: bool = False
    output_path: str = ""
    error_count: int = 0
    errors: List[str] = field(default_factory=list)


@dataclass
class BatchSummary:
    """배치 처리 전체 요약"""
    total: int = 0
    success: int = 0
    failed: int = 0
    results: List[BatchResult] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        return self.success / max(self.total, 1) * 100


def _process_single(file_path: str, output_dir: str, output_format: str) -> BatchResult:
    """단일 파일 처리 (별도 프로세스에서 실행)"""
    from .reader import Dochan

    result = BatchResult(file_path=file_path)

    try:
        reader = Dochan(file_path)

        # 출력 파일명 생성
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        ext_map = {'markdown': '.md', 'json': '.json', 'text': '.txt'}
        ext = ext_map.get(output_format, '.md')
        output_path = os.path.join(output_dir, base_name + ext)

        # 변환
        if output_format == 'json':
            content = reader.to_json()
        elif output_format == 'text':
            content = reader.to_plain_text()
        else:
            content = reader.to_markdown()

        # 저장
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)

        result.success = True
        result.output_path = output_path
        result.errors = reader.errors
        result.error_count = len(reader.errors)

    except Exception as e:
        result.success = False
        result.errors = [str(e)]
        result.error_count = 1

    return result


def batch_convert(
    input_dir: str,
    output_dir: str,
    output_format: str = 'markdown',
    max_workers: int = 4,
    extensions: tuple = ('.hwp', '.hwpx', '.doc', '.ppt', '.xls', '.docx', '.pptx', '.xlsx'),
) -> BatchSummary:
    """
    디렉토리 내 HWP 파일 일괄 변환

    Args:
        input_dir: 입력 디렉토리
        output_dir: 출력 디렉토리
        output_format: 'markdown', 'json', 'text'
        max_workers: 병렬 워커 수
        extensions: 처리할 확장자

    Returns:
        BatchSummary
    """
    # output_dir 경로 검증
    try:
        Path(output_dir).resolve().relative_to(Path(os.getcwd()).resolve())
    except ValueError:
        pass  # output_dir가 cwd 밖이어도 허용하되, 아래에서 symlink 공격 방지

    os.makedirs(output_dir, exist_ok=True)

    # 파일 수집
    files = []
    resolved_input = Path(input_dir).resolve()
    for root, _, filenames in os.walk(input_dir):
        for fn in filenames:
            if any(fn.lower().endswith(ext) for ext in extensions):
                full_path = os.path.join(root, fn)
                # Path traversal 방지: 실제 경로가 input_dir 내부인지 검증
                try:
                    Path(full_path).resolve().relative_to(resolved_input)
                except ValueError:
                    logger.warning(f"경로 이탈 감지, 건너뜀: {full_path}")
                    continue
                files.append(full_path)

    summary = BatchSummary(total=len(files))
    logger.info(f"배치 시작: {len(files)}개 파일, {max_workers} 워커")

    if max_workers <= 1:
        for file_path in files:
            result = _process_single(file_path, output_dir, output_format)
            summary.results.append(result)
            if result.success:
                summary.success += 1
                logger.info(f"✓ {os.path.basename(file_path)}")
            else:
                summary.failed += 1
                logger.error(f"✗ {os.path.basename(file_path)}: {result.errors}")

        logger.info(f"배치 완료: {summary.success}/{summary.total} 성공 ({summary.success_rate:.1f}%)")
        return summary

    # 병렬 처리
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_process_single, f, output_dir, output_format): f
            for f in files
        }

        for future in as_completed(futures):
            file_path = futures[future]
            try:
                result = future.result()
                summary.results.append(result)
                if result.success:
                    summary.success += 1
                    logger.info(f"✓ {os.path.basename(file_path)}")
                else:
                    summary.failed += 1
                    logger.error(f"✗ {os.path.basename(file_path)}: {result.errors}")
            except Exception as e:
                summary.failed += 1
                summary.results.append(BatchResult(
                    file_path=file_path,
                    success=False,
                    errors=[str(e)],
                    error_count=1,
                ))
                logger.error(f"✗ {os.path.basename(file_path)}: {e}")

    logger.info(f"배치 완료: {summary.success}/{summary.total} 성공 ({summary.success_rate:.1f}%)")
    return summary
