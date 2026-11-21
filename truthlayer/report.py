"""Summarise verdicts and export them."""
from __future__ import annotations

import csv
import io
from typing import Dict, List

from .extract import Claim
from .verify import Verdict, VERIFIED, INACCURATE, FALSE


def summarise(verdicts: List[Verdict]) -> Dict[str, int]:
    out = {VERIFIED: 0, INACCURATE: 0, FALSE: 0}
    for v in verdicts:
        out[v.status] = out.get(v.status, 0) + 1
    return out


def rows(claims: List[Claim], verdicts: List[Verdict]) -> List[dict]:
    out = []
    for c, v in zip(claims, verdicts):
        out.append({
            "claim": c.sentence,
            "kind": c.kind,
            "entity": c.entity or "",
            "claimed": c.raw,
            "verdict": v.status,
            "real_value": v.actual,
            "real_year": v.year or "",
            "source": v.source,
            "source_url": v.url,
            "note": v.note,
        })
    return out


def to_csv(claims: List[Claim], verdicts: List[Verdict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["claim", "kind", "entity", "claimed", "verdict",
                                        "real_value", "real_year", "source", "source_url", "note"])
    w.writeheader()
    for r in rows(claims, verdicts):
        w.writerow(r)
    return buf.getvalue()
