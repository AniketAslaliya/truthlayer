"""Match each claim against live evidence and give it a verdict.

Verdicts:
- Verified   : the claim matches the latest live figure.
- Inaccurate : the claim is outdated (it matches an older figure) or is close but off.
- False      : the claim is contradicted by live data, or no evidence supports it.
Every non-verified verdict carries the real, current fact when one is found.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import List, Optional, Tuple

from . import sources, llm
from .extract import Claim, PERCENT_KINDS, SCALE, KINDS, STOP

WB = {
    "population": "SP.POP.TOTL",
    "gdp": "NY.GDP.MKTP.CD",
    "gdp_per_capita": "NY.GDP.PCAP.CD",
    "inflation": "FP.CPI.TOTL.ZG",
    "life_expectancy": "SP.DYN.LE00.IN",
    "unemployment": "SL.UEM.TOTL.ZS",
    "internet": "IT.NET.USER.ZS",
    "literacy": "SE.ADT.LITR.ZS",
    "urban": "SP.URB.TOTL.IN.ZS",
    "fertility": "SP.DYN.TFRT.IN",
    "military": "MS.MIL.XPND.GD.ZS",
    "health": "SH.XPD.CHEX.GD.ZS",
    "co2": "EN.GHG.CO2.MT.CE.AR5",
}
RATE_KINDS = {"life_expectancy", "fertility"}

VERIFIED, INACCURATE, FALSE = "Verified", "Inaccurate", "False"


@dataclass
class Verdict:
    status: str
    claimed: Optional[float]
    actual: Optional[float]
    year: Optional[int]
    source: str
    url: str
    note: str

    def as_dict(self):
        return asdict(self)


def human(v: float) -> str:
    a = abs(v)
    if a >= 1e12:
        return "%.2f trillion" % (v / 1e12)
    if a >= 1e9:
        return "%.2f billion" % (v / 1e9)
    if a >= 1e6:
        return "%.2f million" % (v / 1e6)
    if a >= 1e3:
        return "{:,.0f}".format(v)
    return "%.2f" % v


def is_pct(claim: Claim) -> bool:
    return claim.unit == "percent" or (claim.kind in PERCENT_KINDS and claim.kind not in RATE_KINDS)


def fmt(claim: Claim, v: float) -> str:
    return ("%.1f%%" % v) if is_pct(claim) else human(v)


def close(claim: Claim, v: float, pct_tol: float, ratio_tol: float) -> bool:
    c = claim.value or 0.0
    if is_pct(claim):
        return abs(c - v) <= pct_tol
    if v == 0:
        return c == 0
    return abs(c / v - 1) <= ratio_tol


def rel(claim: Claim, v: float) -> float:
    c = claim.value or 0.0
    if is_pct(claim):
        return abs(c - v)
    return abs(c / v - 1) if v else float("inf")


def judge_series(claim: Claim, series, label: str) -> Tuple[str, str, float, int]:
    """Verified if it matches the latest figure; Inaccurate (outdated) if it
    matches an older year better; else slightly off or False, always with the
    real latest figure."""
    pct = is_pct(claim)
    tight, loose, near = (0.3, 0.5, 2.0) if pct else (0.01, 0.03, 0.10)
    latest_year, latest = series[0]
    real = "%s (%d)" % (fmt(claim, latest), latest_year)
    d_latest = rel(claim, latest)
    older = [(rel(claim, v), y, v) for y, v in series[1:] if y < latest_year]
    best = min(older) if older else None
    if d_latest <= tight:
        return VERIFIED, "matches the latest figure: %s" % real, latest, latest_year
    if best and best[0] <= tight and best[0] < d_latest:
        return (INACCURATE, "outdated: %s was the %d figure. Latest is %s"
                % (fmt(claim, best[2]), best[1], real), latest, latest_year)
    if d_latest <= loose:
        return VERIFIED, "matches the latest figure (rounded): %s" % real, latest, latest_year
    if d_latest <= near:
        return INACCURATE, "slightly off. Latest is %s" % real, latest, latest_year
    return FALSE, "contradicted by live data. Real figure: %s" % real, latest, latest_year


NUM_IN_TEXT = re.compile(
    r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*"
    r"(%|percent|per cent|trillion|billion|million|thousand|lakh|crore|bn|mn)?", re.I)


def content_words(sentence: str) -> List[str]:
    words = re.findall(r"[A-Za-z][A-Za-z\-]{3,}", sentence.lower())
    return [w for w in words if w not in STOP and w not in
            {"million", "billion", "trillion", "percent", "crore", "lakh", "about",
             "around", "nearly", "over", "than", "more", "less", "which", "were",
             "have", "been", "currently", "approximately", "roughly", "total"}]


def kind_words(kind: str) -> Tuple[str, ...]:
    for k, words in KINDS:
        if k == kind:
            return words
    return ()


def evidence_numbers(text: str, claim: Claim):
    want_pct = is_pct(claim)
    cw = set(content_words(claim.sentence))
    kw = kind_words(claim.kind)
    out = []
    for sent in re.split(r"(?<=[.!?])\s+|\n+", text or ""):
        low = sent.lower()
        overlap = sum(1 for w in cw if w in low)
        about_kind = any(k in low for k in kw)
        if not (about_kind and overlap >= 1) and overlap < 3:
            continue
        for m in NUM_IN_TEXT.finditer(sent):
            try:
                v = float(m.group(1).replace(",", ""))
            except ValueError:
                continue
            u = (m.group(2) or "").lower()
            pct = u in ("%", "percent", "per cent")
            if pct != want_pct:
                continue
            if not pct and not u and 1900 <= v <= 2100 and claim.kind != "founded":
                continue
            if u in SCALE:
                v *= SCALE[u]
            c = claim.value or 0.0
            if not pct and c and not (0.1 <= v / c <= 10):
                continue
            out.append((v, sent.strip(), overlap + (2 if about_kind else 0)))
    return out


def _verify_free(claim: Claim) -> Verdict:
    if claim.entity_type == "country":
        iso3 = sources.country_iso3(claim.entity)
        if iso3 and claim.kind in WB:
            got = sources.worldbank_series(WB[claim.kind], iso3)
            if got:
                series, label = got
                status, note, actual, year = judge_series(claim, series, label)
                return Verdict(status, claim.value, actual, year, "World Bank: " + label,
                               "https://data.worldbank.org/indicator/%s?locations=%s"
                               % (WB[claim.kind], iso3), note)
        if claim.kind in sources.WD_PROP:
            series = sources.wikidata_series(claim.kind, claim.entity)
            if series:
                status, note, actual, year = judge_series(claim, series, claim.kind)
                note = note.replace(" (0)", "")
                return Verdict(status, claim.value, actual, year or None,
                               "Wikidata: %s of %s" % (claim.kind.replace("_", " "), claim.entity),
                               "https://www.wikidata.org/wiki/%s" % sources._wd_qid(claim.entity),
                               note)

    if claim.kind == "founded" and claim.entity:
        year = sources.wikidata_inception(claim.entity)
        if year:
            if int(claim.value or 0) == year:
                return Verdict(VERIFIED, claim.value, float(year), year, "Wikidata",
                               "https://www.wikidata.org/", "founded in %d" % year)
            return Verdict(FALSE, claim.value, float(year), year, "Wikidata",
                           "https://www.wikidata.org/",
                           "wrong date. Real fact: founded in %d" % year)

    q = " ".join(filter(None, [claim.entity, " ".join(kind_words(claim.kind)[:1])])) \
        or " ".join(content_words(claim.sentence)[:6])
    for title in sources.wiki_search(q, 3):
        text = sources.wiki_extract(title)
        if not text:
            continue
        url = "https://en.wikipedia.org/wiki/" + title.replace(" ", "_")
        ev = evidence_numbers(text, claim)
        if not ev:
            continue
        for v, sent, _ in ev:
            if close(claim, v, 0.5, 0.03):
                return Verdict(VERIFIED, claim.value, v, None, "Wikipedia: " + title, url,
                               "source says: \"%s\"" % sent[:220])
        ev.sort(key=lambda e: -e[2])
        v, sent, score = ev[0]
        if score >= 3:
            status = INACCURATE if close(claim, v, 2.0, 0.10) else FALSE
            return Verdict(status, claim.value, v, None, "Wikipedia: " + title, url,
                           "source says %s: \"%s\"" % (fmt(claim, v), sent[:220]))

    return Verdict(FALSE, claim.value, None, None, "no supporting source", "",
                   "no evidence found in live sources for this figure")


def verify(claim: Claim) -> Verdict:
    v = _verify_free(claim)
    if v.status == VERIFIED or v.source.startswith(("World Bank", "Wikidata")):
        return v
    if llm.available():
        try:
            obj, url, title = llm.verify_claim(claim.sentence, claim.raw)
            status = obj.get("status") if obj.get("status") in (VERIFIED, INACCURATE, FALSE) else FALSE
            note = (obj.get("correct_fact") or "").strip()
            if obj.get("explanation"):
                note = (note + " " + obj["explanation"].strip()).strip()
            yr = obj.get("year")
            return Verdict(status, claim.value, None, yr if isinstance(yr, int) else None,
                           "Google Search via Gemini" + (": " + title if title else ""), url, note)
        except Exception:  # noqa: BLE001
            pass
    return v


def verify_all(claims: List[Claim], per_claim_s: float = 45.0) -> List[Verdict]:
    """Check claims in parallel; a claim whose sources don't answer in time is
    reported as unverifiable rather than holding up the whole document."""
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FTimeout
    import time
    out: List[Optional[Verdict]] = [None] * len(claims)
    pool = ThreadPoolExecutor(max_workers=8)
    futs = [pool.submit(verify, c) for c in claims]
    deadline = time.time() + per_claim_s + 2 * len(claims)
    for i, f in enumerate(futs):
        try:
            out[i] = f.result(timeout=max(1.0, min(per_claim_s, deadline - time.time())))
        except FTimeout:
            out[i] = Verdict(FALSE, claims[i].value, None, None, "sources timed out", "",
                             "live sources did not answer in time: treat as unverified")
        except Exception as e:  # noqa: BLE001
            out[i] = Verdict(FALSE, claims[i].value, None, None, "error", "",
                             "could not check: %s" % str(e)[:80])
    pool.shutdown(wait=False, cancel_futures=True)
    return out  # type: ignore[return-value]
