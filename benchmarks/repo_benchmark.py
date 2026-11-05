"""Source fingerprint benchmark for synthetic source trees (not real-world workloads)."""
import argparse
import json
import tempfile
import time
import tracemalloc
from pathlib import Path
from raee_lite.core import fingerprint


def run(n):
    with tempfile.TemporaryDirectory() as d:
        root=Path(d)
        for i in range(n):
            (root / f'source_{i:06d}.py').write_text('def f():\n    return 42\n')
        tracemalloc.start()
        start=time.perf_counter()
        result=fingerprint(root)
        elapsed=time.perf_counter()-start
        _,peak=tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return {'synthetic_files':n,'hashed_files':result['files'],
                'skipped_count':len(result['skipped']), 'elapsed_s':round(elapsed,3),
                'peak_tracemalloc_mb':round(peak/1e6,2)}

if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--files',type=int,default=2000)
    print(json.dumps(run(p.parse_args().files),indent=2))
