"""Synthetic agent-log scale benchmark (explicitly NOT real-user performance)."""
from __future__ import annotations
import argparse, json, tempfile, tracemalloc, time, sys, platform
from pathlib import Path
from raee_lite.agent_logs import import_log


def run(events: int) -> dict:
    if not 1 <= events <= 200000:
        raise ValueError('events must be 1..200000')
    with tempfile.TemporaryDirectory() as d:
        root=Path(d); log=root/'synthetic.jsonl'
        # one standalone codex completion per line: no PII, no tokens, no downloaded data
        row={'type':'event_msg','payload':{'type':'item_completed','item':{'type':'CommandExecution','command':'python -m pytest -q','exit_code':0}}}
        sample=(json.dumps(row)+'\n').encode()
        with log.open('wb') as f:
            for _ in range(events): f.write(sample)
        tracemalloc.start(); t=time.perf_counter()
        try:
            result=import_log(root, log, 'codex')
            elapsed=time.perf_counter()-t
            _,peak=tracemalloc.get_traced_memory()
        finally:tracemalloc.stop()
        return {'provenance':'SYNTHETIC', 'events':events, 'input_bytes':log.stat().st_size,
                'seconds':round(elapsed,3),'tracemalloc_peak_mb':round(peak/1048576,2),
                'parsed_observations':result['new_observations'],
                'platform':platform.system(), 'python':platform.python_version(),
                'warning':'Python tracemalloc peak is not total RSS; do not extrapolate to real sessions.'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--events',type=int,default=20000);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();data=run(a.events);a.out.write_text(json.dumps(data,indent=2)+'\n');print(json.dumps(data,indent=2))
