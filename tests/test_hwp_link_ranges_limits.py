"""Hyperlink range work and output contracts on synthetic text runs."""
from dataclasses import asdict, replace
import random

from dochan.hwp import section
from dochan.model.document import TextRun


def _reference(runs, ranges):
    """Sequential range overlay: retain all cuts and let the last link win."""
    for start, end, url in ranges:
        result = []
        offset = 0
        for run in runs:
            stop = offset + len(run.text)
            if not run.text or stop <= start or offset >= end:
                result.append(run)
            else:
                left, right = max(start - offset, 0), min(end - offset, len(run.text))
                if left:
                    result.append(replace(run, text=run.text[:left]))
                result.append(replace(run, text=run.text[left:right], link=url))
                if right < len(run.text):
                    result.append(replace(run, text=run.text[right:]))
            offset = stop
        runs = result
    return runs


def test_many_disjoint_links_do_not_rescan_all_previous_runs(monkeypatch):
    class CountedText(str):
        length_reads = 0

        def __len__(self):
            type(self).length_reads += 1
            return super().__len__()

    original_replace = section._dc_replace

    def measured_replace(run, **changes):
        if "text" in changes:
            changes["text"] = CountedText(changes["text"])
        return original_replace(run, **changes)

    monkeypatch.setattr(section, "_dc_replace", measured_replace)
    count = 1000
    runs = [TextRun(CountedText("x" * count), bold=True)]
    result = section._apply_link_ranges(runs, [(i, i + 1, str(i)) for i in range(count)])
    assert [(r.text, r.link, r.bold) for r in result] == [
        ("x", str(i), True) for i in range(count)
    ]
    assert CountedText.length_reads <= count * 20


def test_link_boundary_sweep_preserves_overlaps_styles_and_empty_runs():
    randomizer = random.Random(1942)
    for _ in range(200):
        runs = [TextRun("abc", bold=True, link="existing"), TextRun("", note_ref=4),
                TextRun("defghi", italic=True, char_shape_id=5), TextRun("jkl", underline=True)]
        ranges = []
        for index in range(20):
            start = randomizer.randrange(-3, 15)
            ranges.append((start, start + randomizer.randrange(1, 12), str(index)))
        expected = _reference(runs, ranges)
        actual = section._apply_link_ranges(runs, ranges)
        assert [asdict(run) for run in actual] == [asdict(run) for run in expected]
