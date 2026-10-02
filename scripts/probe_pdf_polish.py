"""PDF 암호·무선 표 회귀를 두 독립 Python 프로세스에서 비교한다.

/usr/bin/python3 -m scripts.probe_pdf_polish CORPUS --baseline-repo REPO \
    --table-manifest FILE --output .codex-work/pdf-polish-probe.json

manifest는 공개 PDF 파일명 한 개씩 적는다. 암호 검사는 corpus의 모든 PDF를
분모에 유지하며 실패·시간 초과를 미검증으로 기록한다. 표 문자는 모델의 실제
텍스트에서 비공백 문자 Counter로 비교하여 Markdown 기호·링크 URL을 제외한다.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys


def missing_characters(expected, actual):
    return dict(Counter(c for c in expected if not c.isspace())
                - Counter(c for c in actual if not c.isspace()))


def compare_encryption(baseline, candidate):
    regressions = []
    if baseline.get("error") or candidate.get("error"):
        if (not baseline.get("error") and baseline.get("encrypted")
                and baseline.get("decrypt_ok") and candidate.get("error")):
            regressions.append("candidate_unreadable")
        return {"status": "unverified", "regressions": regressions}
    if baseline.get("encrypted"):
        if baseline.get("decrypt_ok") and not candidate.get("decrypt_ok"):
            regressions.append("decrypt_failed")
        if baseline.get("text", "").strip() and not candidate.get("text", "").strip():
            regressions.append("text_became_empty")
    return {"status": "regression" if regressions else "pass", "regressions": regressions}


def compare_tables(baseline, candidate, mode_off):
    if any(record.get("error") for record in (baseline, candidate, mode_off)):
        return {"status": "unverified", "baseline_missing": {}, "mode_off_missing": {}}
    before = missing_characters(baseline["text"], candidate["text"])
    disabled = missing_characters(mode_off["text"], candidate["text"])
    return {"status": "regression" if before or disabled else "pass",
            "baseline_missing": before, "mode_off_missing": disabled}


def _model_text(doc):
    from dochan.model.document import Paragraph
    from dochan.model.table import Table
    from dochan.model.header_footer import HeaderFooter, Footnote
    parts = []
    tables = 0
    for section in doc.sections:
        for element in section.elements:
            # Link-only fallback paragraphs and comments are annotation metadata,
            # not page text. They changed representation between the revisions.
            if (getattr(getattr(element, "provenance", None), "path", "") == "annots"
                    or getattr(element, "type", "") == "comment"):
                continue
            if isinstance(element, Table):
                tables += 1
                for row in element.rows:
                    for cell in row:
                        if not cell.is_merged_away:
                            parts.append(cell.text)
            elif isinstance(element, (Paragraph, HeaderFooter, Footnote)):
                parts.append(element.text)
    return "\n".join(parts), tables


def _worker(repo, path, mode):
    # Absolute imports must refer exclusively to the selected repository.
    sys.path.insert(0, str(Path(repo).resolve()))
    import dochan
    from dochan.pdf.reader import PDFReader
    from dochan.pdf.structure import PDFFile
    result = {"module_path": dochan.__file__}
    try:
        if mode == "crypto":
            pdf = PDFFile(Path(path).read_bytes())
            result.update(encrypted=pdf.encrypted, decrypt_ok=pdf.decrypt_ok,
                          warnings=pdf.warnings)
            if not pdf.encrypted:
                return result
        doc = PDFReader(text_tables=mode == "tables").read(path)
        text, tables = _model_text(doc)
        result.update(text=text, tables=tables, errors=doc.errors)
        reader_failures = [error for error in doc.errors if error.startswith("ERR:")]
        if reader_failures:
            result["error"] = "; ".join(reader_failures)
    except Exception as exc:
        result["error"] = repr(exc)
    return result


def run_one(repo, path, mode, timeout):
    try:
        completed = subprocess.run(  # nosemgrep: dangerous-subprocess-use-audit, dangerous-subprocess-use-tainted-env-args
            [sys.executable, str(Path(__file__).resolve()), "--worker", str(repo), str(path), mode],
            cwd=str(repo), capture_output=True, text=True, timeout=timeout)
        if completed.returncode:
            return {"error": "worker_exit_{}: {}".format(completed.returncode, completed.stderr[-1500:])}
        return json.loads(completed.stdout)
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    except (OSError, ValueError) as exc:
        return {"error": repr(exc)}


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        print(json.dumps(_worker(*sys.argv[2:]), ensure_ascii=False))
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--baseline-repo", type=Path, required=True)
    parser.add_argument("--candidate-repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--table-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=40)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.timeout <= 0 or not 1 <= args.workers <= 32:
        parser.error("timeout must be positive and workers must be 1..32")
    args.corpus = args.corpus.resolve()
    args.baseline_repo = args.baseline_repo.resolve()
    args.candidate_repo = args.candidate_repo.resolve()
    files = sorted(args.corpus.glob("*.pdf"))
    names = sorted(set(line.strip() for line in args.table_manifest.read_text().splitlines() if line.strip()))
    if not files:
        parser.error("corpus contains no PDF files")
    if not names:
        parser.error("manifest contains no PDF filenames")
    if any(Path(name).name != name for name in names):
        parser.error("manifest entries must be PDF basenames")

    def crypto(path):
        before = run_one(args.baseline_repo, path, "crypto", args.timeout)
        after = run_one(args.candidate_repo, path, "crypto", args.timeout)
        print("crypto " + path.name, file=sys.stderr, flush=True)
        return path.name, dict(compare_encryption(before, after), baseline=before, candidate=after)

    def table(name):
        path = args.corpus / name
        before = run_one(args.baseline_repo, path, "tables", args.timeout)
        after = run_one(args.candidate_repo, path, "tables", args.timeout)
        off = run_one(args.candidate_repo, path, "plain", args.timeout)
        print("tables " + name, file=sys.stderr, flush=True)
        return name, dict(compare_tables(before, after, off), baseline=before, candidate=after, mode_off=off)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        encryption = dict(pool.map(crypto, files))
        tables = dict(pool.map(table, names))
    summary = {
        "corpus_files": len(files), "encryption_status": dict(Counter(row["status"] for row in encryption.values())),
        "baseline_encrypted": sum(bool(row["baseline"].get("encrypted")) for row in encryption.values()),
        "baseline_decrypted": sum(bool(row["baseline"].get("encrypted") and row["baseline"].get("decrypt_ok")) for row in encryption.values()),
        "encryption_regressions": sum(bool(row["regressions"]) for row in encryption.values()),
        "table_files": len(names), "table_status": dict(Counter(row["status"] for row in tables.values())),
        "baseline_missing_characters": sum(sum(row["baseline_missing"].values()) for row in tables.values()),
        "mode_off_missing_characters": sum(sum(row["mode_off_missing"].values()) for row in tables.values()),
    }
    result = {"summary": summary, "baseline_repo": str(args.baseline_repo), "candidate_repo": str(args.candidate_repo),
              "encryption": encryption, "tables": tables}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return int(any(row["status"] != "pass" for row in list(encryption.values()) + list(tables.values())))


if __name__ == "__main__":
    sys.exit(main())
