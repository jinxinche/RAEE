"""Independent human-labelled relevance eval; summary contains no requirement text.

False-positive RATE requires known negatives; unlike corpus false discovery rate.
These metrics describe suggested links, never actual executed-test correctness.
"""
from __future__ import annotations
import math
from .topic_tags import tags


def wilson(x: int, n: int, z: float = 1.96) -> list[float] | None:
    if n == 0:
        return None
    p = x / n
    a = 1 + z*z/n
    center=(p+z*z/(2*n))/a
    offset=z * math.sqrt((p*(1-p)+z*z/(4*n))/n)/a
    return [round(max(0.0, center-offset),4),round(min(1.0,center+offset),4)]


def evaluate(rows: list[dict], *, provenance: str = 'synthetic', consent: bool = False) -> dict:
    if provenance not in ('synthetic', 'consented-real'):
        raise ValueError('Specify fixture provenance: synthetic or consented-real')
    if provenance == 'consented-real' and not consent:
        raise ValueError('Consent must be affirmed before evaluating private annotations')
    if not isinstance(rows,list) or not 0 < len(rows) <= 100000:
        raise ValueError('Need 1..100000 labelled candidate pairs')
    tp=fp=tn=fn=0
    for row in rows:
        if not isinstance(row,dict) or type(row.get('relevant')) is not bool:
            raise ValueError('Each pair needs a validated binary relevance label')
        if not isinstance(row.get('requirement'),str) or not isinstance(row.get('observed_target'),str):
            raise ValueError('Text fields must be strings')
        kinds = row.get('expected_kinds')
        if not isinstance(kinds,list) or not all(isinstance(k,str) for k in kinds):
            raise ValueError('Invalid expectation kinds')
        proposed = row.get('observed_kind') in kinds and bool(set(tags(row['requirement'])) & set(tags(row['observed_target'])))
        truth = row['relevant']
        if proposed and truth: tp+=1
        elif proposed: fp+=1
        elif truth: fn+=1
        else: tn+=1
    def fraction(x,n):return round(x/n,4) if n else None
    return {'provenance':provenance,'n_pairs':len(rows), 'TP':tp,'FP':fp,'FN':fn,'TN':tn,
            'precision':fraction(tp,tp+fp),'recall':fraction(tp,tp+fn),
            'false_positive_rate':fraction(fp,fp+tn),
            'precision_wilson95':wilson(tp,tp+fp),
            'recall_wilson95':wilson(tp,tp+fn),
            'fpr_wilson95':wilson(fp,fp+tn),
            'warning':'Relevance labels only; cannot prove executed tests are sufficient. Synthetic results do not generalize to real software.'}
