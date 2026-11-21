"""Live, key-less evidence sources: World Bank, Wikipedia, Wikidata.

Everything here is free and needs no API key, so the app runs anywhere
including a free Streamlit Community Cloud or Hugging Face Space.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

UA = {"User-Agent": "TruthLayer/1.0 (fact-check demo; +https://huggingface.co)"}
TIMEOUT = 6
WIKI_API = "https://en.wikipedia.org/w/api.php"


def _json(url: str, tries: int = 3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:  # noqa: BLE001
            last = e
            if i + 1 < tries:
                import time; time.sleep(0.5)
    raise last


@lru_cache(maxsize=1)
def country_index() -> Dict[str, str]:
    """Country name / code -> ISO3, from the World Bank's own country list."""
    idx: Dict[str, str] = {}
    try:
        data = _json("https://api.worldbank.org/v2/country?format=json&per_page=400")
        for row in (data[1] or []):
            iso3 = (row.get("id") or "").strip()
            name = (row.get("name") or "").strip()
            if len(iso3) != 3 or not name:
                continue
            idx[name.lower()] = iso3
            iso2 = (row.get("iso2Code") or "").strip()
            if len(iso2) == 2:
                idx[iso2.lower()] = iso3
    except Exception:
        pass
    idx.update({
        "united states": "USA", "usa": "USA", "us": "USA", "america": "USA",
        "united kingdom": "GBR", "uk": "GBR", "britain": "GBR",
        "south korea": "KOR", "north korea": "PRK", "russia": "RUS",
        "vietnam": "VNM", "iran": "IRN", "syria": "SYR", "egypt": "EGY",
        "turkey": "TUR", "uae": "ARE", "united arab emirates": "ARE",
        "czech republic": "CZE", "czechia": "CZE", "ivory coast": "CIV",
        "hong kong": "HKG", "taiwan": "TWN",
    })
    return idx


def country_iso3(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    return country_index().get(name.strip().lower())


@lru_cache(maxsize=512)
def worldbank_series(indicator: str, iso3: str):
    """Recent non-null values, newest first, as ((year, value), ...), and the label."""
    for q in ("mrv=25", "mrnev=1"):
        url = ("https://api.worldbank.org/v2/country/%s/indicator/%s"
               "?format=json&per_page=60&%s" % (iso3, indicator, q))
        try:
            data = _json(url)
        except Exception:
            continue
        if not isinstance(data, list) or len(data) < 2 or not data[1]:
            continue
        rows = []
        label = indicator
        for r in data[1]:
            if r.get("value") is None:
                continue
            try:
                rows.append((int(r["date"]), float(r["value"])))
            except (TypeError, ValueError):
                continue
            label = ((r.get("indicator") or {}).get("value") or label)
        if rows:
            rows.sort(reverse=True)
            return tuple(rows), label
    return None


def worldbank(indicator: str, iso3: str) -> Optional[Tuple[float, int, str]]:
    """Latest non-null value, its year and the indicator's own label."""
    got = worldbank_series(indicator, iso3)
    if not got:
        return None
    (year, value), label = got[0][0], got[1]
    return value, year, label


@lru_cache(maxsize=256)
def wiki_search(query: str, limit: int = 3) -> List[str]:
    params = {"action": "query", "list": "search", "srsearch": query,
              "format": "json", "srlimit": limit}
    try:
        data = _json(WIKI_API + "?" + urllib.parse.urlencode(params))
    except Exception:
        return []
    return [r["title"] for r in (data.get("query", {}).get("search") or [])]


@lru_cache(maxsize=256)
def wiki_extract(title: str) -> str:
    params = {"action": "query", "prop": "extracts", "explaintext": 1,
              "titles": title, "format": "json", "redirects": 1}
    try:
        data = _json(WIKI_API + "?" + urllib.parse.urlencode(params))
    except Exception:
        return ""
    for p in (data.get("query", {}).get("pages") or {}).values():
        return p.get("extract") or ""
    return ""


@lru_cache(maxsize=128)
def wikidata_inception(name: str) -> Optional[int]:
    """The year an organisation or place was founded, from Wikidata (P571)."""
    try:
        s = _json("https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(
            {"action": "wbsearchentities", "search": name, "language": "en",
             "format": "json", "limit": 1}))
        hits = s.get("search") or []
        if not hits:
            return None
        qid = hits[0]["id"]
        e = _json("https://www.wikidata.org/wiki/Special:EntityData/%s.json" % qid)
        claims = (e.get("entities", {}).get(qid, {}).get("claims") or {}).get("P571") or []
        for c in claims:
            try:
                time = c["mainsnak"]["datavalue"]["value"]["time"]
                m = re.match(r"[+-](\d{4})", time)
                if m:
                    return int(m.group(1))
            except (KeyError, TypeError):
                continue
    except Exception:
        return None
    return None


# ---------------------------------------------------------------------------
# Wikidata country statistics: a second live source with dated values, used
# when the World Bank API is slow or down. Each value carries its point in
# time (P585), so outdated figures can be told apart from false ones.
# ---------------------------------------------------------------------------
WD_PROP = {
    "population": "P1082",
    "gdp": "P2131",
    "gdp_per_capita": "P2132",
    "life_expectancy": "P2250",
    "unemployment": "P1198",
    "fertility": "P4841",
}
WD_COUNTRY = {
    "india": "Q668", "united states": "Q30", "china": "Q148", "japan": "Q17",
    "germany": "Q183", "france": "Q142", "united kingdom": "Q145", "italy": "Q38",
    "brazil": "Q155", "russia": "Q159", "canada": "Q16", "australia": "Q408",
    "indonesia": "Q252", "nigeria": "Q1033", "pakistan": "Q843", "bangladesh": "Q902",
    "mexico": "Q96", "spain": "Q29", "south korea": "Q884", "south africa": "Q258",
    "egypt": "Q79", "turkey": "Q43", "saudi arabia": "Q851",
    "united arab emirates": "Q878", "singapore": "Q334", "sri lanka": "Q854",
    "nepal": "Q837", "vietnam": "Q881", "thailand": "Q869", "philippines": "Q928",
    "argentina": "Q414", "kenya": "Q114", "ethiopia": "Q115", "iran": "Q794",
}


def _wd_qid(country: str) -> Optional[str]:
    key = (country or "").strip().lower()
    if key in WD_COUNTRY:
        return WD_COUNTRY[key]
    try:
        s = _json("https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(
            {"action": "wbsearchentities", "search": country, "language": "en",
             "format": "json", "limit": 5, "type": "item"}))
    except Exception:
        return None
    for h in s.get("search") or []:
        d = (h.get("description") or "").lower()
        if "country" in d or "sovereign state" in d:
            return h["id"]
    return None


@lru_cache(maxsize=512)
def wikidata_series(kind: str, country: str):
    """((year, value), ...) newest first for a country statistic, from Wikidata."""
    prop = WD_PROP.get(kind)
    qid = _wd_qid(country) if prop else None
    if not qid:
        return None
    try:
        data = _json("https://www.wikidata.org/w/api.php?" + urllib.parse.urlencode(
            {"action": "wbgetclaims", "entity": qid, "property": prop, "format": "json"}))
    except Exception:
        return None
    rows = {}
    undated = None
    for c in (data.get("claims") or {}).get(prop) or []:
        if c.get("rank") == "deprecated":
            continue
        try:
            v = float(c["mainsnak"]["datavalue"]["value"]["amount"])
        except (KeyError, TypeError, ValueError):
            continue
        year = None
        for q in ((c.get("qualifiers") or {}).get("P585") or []):
            try:
                m = re.match(r"[+-](\d{4})", q["datavalue"]["value"]["time"])
                year = int(m.group(1)) if m else None
            except (KeyError, TypeError):
                pass
        if year is None:
            if c.get("rank") == "preferred" or undated is None:
                undated = v
            continue
        if year not in rows or c.get("rank") == "preferred":
            rows[year] = v
    out = sorted(rows.items(), reverse=True)
    if not out and undated is not None:
        out = [(0, undated)]
    return tuple(out) or None
