"""Command line: python -m truthlayer.cli document.pdf"""
from __future__ import annotations

import sys

from pypdf import PdfReader

from .extract import find_claims
from .verify import verify_all
from .report import summarise, rows


def main(path: str) -> int:
    reader = PdfReader(path)
    text = "\n".join((p.extract_text() or "") for p in reader.pages)
    claims = find_claims(text)
    verdicts = verify_all(claims)
    for r in rows(claims, verdicts):
        print("[%s] %s" % (r["verdict"], r["claim"][:110]))
        if r["real_value"] is not None:
            print("    real: %s (%s)" % (r["real_value"], r["source"]))
    print(summarise(verdicts))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
