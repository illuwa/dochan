"""Render a Markdown summary from an isolated competitor benchmark index."""
import argparse
import json
from pathlib import Path


def render_markdown_summary(index: dict) -> str:
    lines = [
        "# dochan Competitive Index Summary",
        "",
        f"Corpus: `{index.get('corpus', '')}`",
        "",
        "## Runs",
        "",
        "| Competitor | OK | Error |",
        "| --- | --- | --- |",
    ]
    competitors = index.get("competitors", [])
    for record in competitors:
        lines.append(
            "| {competitor} | {ok} | {error} |".format(
                competitor=record.get("competitor", ""),
                ok=str(record.get("ok", False)).lower(),
                error=record.get("error", ""),
            )
        )

    lines.extend([
        "",
        "## Competitive Summary",
        "",
        "| Competitor | Format | Speedup | Accuracy Delta | Success Delta | JSON Assets Delta | JSON Run Provenance Delta |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ])
    for record in competitors:
        summary = record.get("report_summary", {})
        for row in summary.get("competitive_summary", []):
            lines.append(
                "| {competitor} | {format} | {speedup} | {accuracy} | {success} | {json_assets} | {json_run_provenance} |".format(
                    competitor=row.get("competitor") or record.get("competitor", ""),
                    format=row.get("format", ""),
                    speedup=_format_multiplier(row.get("speedup_vs_competitor")),
                    accuracy=_format_signed(row.get("accuracy_delta")),
                    success=_format_signed(row.get("success_rate_delta")),
                    json_assets=_format_signed(row.get("median_json_asset_count_delta")),
                    json_run_provenance=_format_signed(row.get("median_json_run_provenance_count_delta")),
                )
            )

    lines.extend([
        "",
        "## dochan JSON Profile",
        "",
        "| Competitor Run | Format | JSON Assets | JSON Run Provenance |",
        "| --- | --- | ---: | ---: |",
    ])
    for record in competitors:
        summary = record.get("report_summary", {})
        for row in summary.get("format_summary", []):
            if row.get("converter") != "dochan":
                continue
            lines.append(
                "| {competitor} | {format} | {assets} | {run_provenance} |".format(
                    competitor=record.get("competitor", ""),
                    format=row.get("format", ""),
                    assets=_format_number(row.get("median_json_asset_count")),
                    run_provenance=_format_number(row.get("median_json_run_provenance_count")),
                )
            )

    lines.extend([
        "",
        "## Improvement Candidates",
        "",
        "| Competitor | Format | Gap Score | Reasons |",
        "| --- | --- | ---: | --- |",
    ])
    for record in competitors:
        summary = record.get("report_summary", {})
        for row in summary.get("improvement_candidates", []):
            lines.append(
                "| {competitor} | {format} | {score} | {reasons} |".format(
                    competitor=row.get("competitor") or record.get("competitor", ""),
                    format=row.get("format", ""),
                    score=_format_number(row.get("worst_gap_score")),
                    reasons=", ".join(row.get("reasons", [])),
                )
            )

    lines.extend([
        "",
        "## File Improvement Candidates",
        "",
        "| Competitor | Format | File | Gap Score | Reasons | dochan Output | Competitor Output |",
        "| --- | --- | --- | ---: | --- | --- | --- |",
    ])
    for record in competitors:
        summary = record.get("report_summary", {})
        for row in summary.get("file_improvement_candidates", []):
            lines.append(
                "| {competitor} | {format} | {file} | {score} | {reasons} | {dochan_output} | {competitor_output} |".format(
                    competitor=row.get("competitor") or record.get("competitor", ""),
                    format=row.get("format", ""),
                    file=row.get("file", ""),
                    score=_format_number(row.get("worst_gap_score")),
                    reasons=", ".join(row.get("reasons", [])),
                    dochan_output=row.get("dochan_output_path", ""),
                    competitor_output=row.get("competitor_output_path", ""),
                )
            )

    lines.append("")
    return "\n".join(lines)


def _format_multiplier(value) -> str:
    if value is None:
        return ""
    return f"{value:.2f}x"


def _format_signed(value) -> str:
    if value is None:
        return ""
    return f"{value:+.3f}"


def _format_number(value) -> str:
    if value is None:
        return ""
    return f"{value:.3f}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Render Markdown from run_isolated_competitor_benchmark index.json.")
    parser.add_argument("index", type=Path, help="Path to index.json")
    parser.add_argument("--output", type=Path, default=None, help="Optional Markdown output path")
    args = parser.parse_args()

    index = json.loads(args.index.read_text(encoding="utf-8"))
    markdown = render_markdown_summary(index)
    if args.output:
        args.output.write_text(markdown, encoding="utf-8")
    else:
        print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
