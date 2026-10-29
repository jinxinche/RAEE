"""Generate ONLY synthetic event streams; outputs throughput and peak tracemalloc.

Benchmark totals are machine-dependent; for reproducibility provide --lines.
"""
import argparse
import json
import tempfile
import time
import tracemalloc
from pathlib import Path
from raee_lite.agent_logs import import_log
from raee_lite.core import init


def run(n):
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        init(root)
        fp = root / 'sample.jsonl'
        with fp.open('w', encoding='utf-8') as out:
            for i in range(n):
                if i % 2 == 0:
                    e = {'type':'assistant','message':{'content':[{'type':'tool_use','name':'Bash','id':f'b{i}', 'input':{'command':'pytest -q'}}]}}
                else:
                    e = {'type':'user','message':{'content':[{'type':'tool_result','tool_use_id':f'b{i-1}', 'content':'Exit code: 0\n'}]}}
                out.write(json.dumps(e)+'\n')
        tracemalloc.start()
        start = time.perf_counter()
        result = import_log(root, fp, 'claude')
        elapsed = time.perf_counter()-start
        _,peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return {'lines':n,'file_bytes':fp.stat().st_size, 'elapsed_s':round(elapsed,3),
                'lines_per_s':round(n/elapsed), 'peak_tracemalloc_mb':round(peak/1_000_000,2),
                'records':result['new_observations']}

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--lines', type=int, default=20000)
    n=p.parse_args().lines
    print(json.dumps(run(n),indent=2))
