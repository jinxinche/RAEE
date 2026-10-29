"""Evaluate the coarse scope/topic hint against explicitly labelled pairs.

SYNTHETIC FIXTURE ONLY. Do NOT advertise this as a field error rate.
"""
import argparse
import json
from pathlib import Path
from raee_lite.association_metrics import evaluate

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--index',type=Path,default=Path(__file__).parent/'labelled_hints.json')
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--provenance',choices=['synthetic','consented-real'],default='synthetic')
    parser.add_argument('--consent',action='store_true')
    args=parser.parse_args()
    if args.index.is_symlink() or args.index.stat().st_size > 8_000_000:
        raise SystemExit('Rejecting unsafe or oversized labelled dataset')
    rows=json.loads(args.index.read_text())
    result=evaluate(rows,provenance=args.provenance,consent=args.consent)
    args.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k in ('n_pairs','precision','recall','false_positive_rate','provenance')},indent=2))
