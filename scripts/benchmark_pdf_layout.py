"""Measure a fixed public-PDF manifest against a source checkout.

Use --parse-only with one worker for alternating timings or cProfile. The
normal mode uses probe_output_speed's four-output hash collector; compare the
result JSON files with python -m scripts.probe_output_speed compare.
"""
import argparse
import cProfile
import json
import multiprocessing
import os
from pathlib import Path
import sys
import time

from scripts.probe_output_speed import _init_worker, measure_file


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('--source', required=True)
    p.add_argument('--manifest', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--workers', type=int, default=1)
    p.add_argument('--profile')
    p.add_argument('--parse-only', action='store_true')
    args = p.parse_args(argv)
    if (args.parse_only or args.profile) and args.workers != 1:
        p.error('--parse-only and --profile require --workers 1')
    paths = json.loads(Path(args.manifest).read_text())
    if not isinstance(paths, list) or not all(isinstance(path, str) for path in paths):
        p.error('manifest must be a JSON list of file paths')
    if len(paths) != len(set(paths)):
        p.error('manifest contains duplicate paths')
    args.source = str(Path(args.source).resolve())
    started = time.perf_counter()
    profile = cProfile.Profile() if args.profile else None
    if args.workers == 1:
        _init_worker(args.source, 180)
        if args.parse_only:
            from dochan import Dochan
        if profile:
            profile.enable()
        if args.parse_only:
            records = {}
            for path in paths:
                before = time.perf_counter()
                doc = Dochan(path)
                elapsed = time.perf_counter() - before
                records[path] = {'parse': elapsed}
                del doc
        else:
            records = dict(measure_file(path) for path in paths)
        if profile:
            profile.disable()
            profile.dump_stats(args.profile)
    else:
        with multiprocessing.Pool(args.workers, _init_worker, (args.source, 180), maxtasksperchild=300) as pool:
            records = dict(pool.imap_unordered(measure_file, paths, chunksize=2))
    result = dict(source=args.source, python=sys.version, disabled=os.environ.get('DOCHAN_DISABLE_ACCEL'),
                  wall=time.perf_counter()-started, records=records)
    Path(args.output).write_text(json.dumps(result))
    print(json.dumps(dict(files=len(records), failures=sum('failure' in r for r in records.values()),
                          parse=sum(r.get('parse', 0) for r in records.values()), wall=result['wall'])), flush=True)


if __name__ == '__main__':
    main()
