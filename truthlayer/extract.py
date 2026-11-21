"""Turn a document's prose into checkable claims."""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Optional, List, Tuple

SCALE = {
    "thousand": 1e3, "k": 1e3,
    "lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5,
    "million": 1e6, "mn": 1e6, "m": 1e6,
    "crore": 1e7, "crores": 1e7, "cr": 1e7,
    "billion": 1e9, "bn": 1e9, "b": 1e9,
    "trillion": 1e12, "tn": 1e12,
}

KINDS = [
    ("gdp_per_capita", ("per capita", "per-capita", "income per person")),
    ("population", ("population", "people", "inhabitants", "residents", "citizens")),
    ("gdp", ("gdp", "gross domestic product", "economic output")),
    ("inflation", ("inflation", "consumer price", "cpi")),
    ("life_expectancy", ("life expectancy", "lifespan", "life span")),
    ("unemployment", ("unemployment", "jobless")),
    ("area", ("area", "square kilomet", "sq km", "sq. km", "km2", "square mile")),
    ("internet", ("internet user", "internet penetration", "internet access", "online population")),
    ("co2", ("co2", "carbon emission", "emissions", "greenhouse gas")),
    ("literacy", ("literacy", "literate")),
    ("urban", ("urban population", "urbanisation", "urbanization")),
    ("fertility", ("fertility rate", "birth rate")),
    ("military", ("military spend", "defence budget", "defense budget", "military expenditure")),
    ("health", ("health spend", "healthcare spend", "health expenditure")),
    ("founded", ("founded", "established", "incorporated", "launched in", "started in")),
    ("revenue", ("revenue", "turnover", "sales", "arr")),
    ("users", ("users", "customers", "subscribers", "downloads", "agents", "clients")),
    ("employees", ("employees", "staff", "workforce", "headcount")),
    ("valuation", ("valuation", "valued at", "market cap")),
    ("funding", ("raised", "funding", "investment", "seed round")),
    ("growth", ("growth", "grew", "cagr", "year on year", "yoy")),
]

PERCENT_KINDS = {"inflation", "unemployment", "literacy", "urban", "internet",
                 "health", "military", "growth", "fertility"}

COUNTRY_ALIASES = {
    "india": "India", "indian": "India",
    "united states": "United States", "usa": "United States", "u.s.": "United States",
    "america": "United States", "us": "United States",
    "china": "China", "chinese": "China",
    "japan": "Japan", "germany": "Germany", "france": "France", "italy": "Italy",
    "spain": "Spain", "brazil": "Brazil", "russia": "Russia", "canada": "Canada",
    "australia": "Australia", "mexico": "Mexico", "indonesia": "Indonesia",
    "pakistan": "Pakistan", "bangladesh": "Bangladesh", "nigeria": "Nigeria",
    "south africa": "South Africa", "egypt": "Egypt", "turkey": "Turkey",
    "saudi arabia": "Saudi Arabia", "uae": "United Arab Emirates",
    "united arab emirates": "United Arab Emirates", "singapore": "Singapore",
    "south korea": "South Korea", "korea": "South Korea", "north korea": "North Korea",
    "vietnam": "Vietnam", "thailand": "Thailand", "malaysia": "Malaysia",
    "philippines": "Philippines", "sri lanka": "Sri Lanka", "nepal": "Nepal",
    "iran": "Iran", "iraq": "Iraq", "israel": "Israel", "kenya": "Kenya",
    "ethiopia": "Ethiopia", "ghana": "Ghana", "argentina": "Argentina",
    "chile": "Chile", "colombia": "Colombia", "peru": "Peru", "poland": "Poland",
    "ukraine": "Ukraine", "netherlands": "Netherlands", "belgium": "Belgium",
    "sweden": "Sweden", "norway": "Norway", "denmark": "Denmark",
    "finland": "Finland", "switzerland": "Switzerland", "austria": "Austria",
    "portugal": "Portugal", "greece": "Greece", "ireland": "Ireland",
    "new zealand": "New Zealand", "united kingdom": "United Kingdom",
    "uk": "United Kingdom", "britain": "United Kingdom", "qatar": "Qatar",
    "kuwait": "Kuwait", "oman": "Oman", "bahrain": "Bahrain", "jordan": "Jordan",
    "lebanon": "Lebanon", "morocco": "Morocco", "algeria": "Algeria",
    "tunisia": "Tunisia", "tanzania": "Tanzania", "uganda": "Uganda",
    "zimbabwe": "Zimbabwe", "zambia": "Zambia", "mozambique": "Mozambique",
    "cameroon": "Cameroon", "senegal": "Senegal", "kazakhstan": "Kazakhstan",
    "uzbekistan": "Uzbekistan", "afghanistan": "Afghanistan", "myanmar": "Myanmar",
    "cambodia": "Cambodia", "laos": "Laos", "mongolia": "Mongolia",
    "taiwan": "Taiwan", "hong kong": "Hong Kong", "cuba": "Cuba",
    "venezuela": "Venezuela", "ecuador": "Ecuador", "bolivia": "Bolivia",
    "uruguay": "Uruguay", "paraguay": "Paraguay", "costa rica": "Costa Rica",
    "panama": "Panama", "guatemala": "Guatemala", "honduras": "Honduras",
    "dominican republic": "Dominican Republic", "jamaica": "Jamaica",
    "iceland": "Iceland", "luxembourg": "Luxembourg", "czech republic": "Czechia",
    "czechia": "Czechia", "hungary": "Hungary", "romania": "Romania",
    "bulgaria": "Bulgaria", "croatia": "Croatia", "serbia": "Serbia",
    "slovakia": "Slovakia", "slovenia": "Slovenia", "estonia": "Estonia",
    "latvia": "Latvia", "lithuania": "Lithuania", "belarus": "Belarus",
    "georgia": "Georgia", "armenia": "Armenia", "azerbaijan": "Azerbaijan",
}

STOP = {"the", "this", "that", "these", "those", "a", "an", "in", "on", "of", "and",
        "but", "for", "with", "from", "by", "as", "at", "it", "its", "our", "we",
        "however", "meanwhile", "today", "according", "source", "figure", "report"}

NUM_RE = re.compile(
    r"(?<![\w.])(?:(?:rs\.?|inr|usd|us\$|\$|eur|€|gbp|£|₹)\s?)?"
    r"(\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"\s*(%|percent|per cent|per-cent|thousand|million|billion|trillion|lakh|lakhs|crore|crores|bn|mn|tn|k|cr)?",
    re.I,
)

SENT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")


@dataclass
class Claim:
    sentence: str
    raw: str
    value: Optional[float]
    unit: str
    kind: str
    entity: Optional[str]
    entity_type: Optional[str]
    page: int = 0

    def as_dict(self):
        return asdict(self)


def sentences(text: str) -> List[str]:
    out = []
    for block in re.split(r"\n+", text or ""):
        block = block.strip(" \t-•*")
        if not block:
            continue
        for s in SENT_RE.split(block):
            s = s.strip(" \t-•*")
            if len(s) >= 20:
                out.append(s)
    return out


def parse_number(num: str, unit: Optional[str]) -> Tuple[Optional[float], Optional[str]]:
    try:
        v = float((num or "").replace(",", ""))
    except (TypeError, ValueError):
        return None, None
    u = (unit or "").lower().strip(".")
    if u in ("%", "percent", "per cent", "per-cent"):
        return v, "percent"
    if u in SCALE:
        return v * SCALE[u], "count"
    return v, "count"


def classify_kind(low: str) -> Optional[str]:
    for kind, words in KINDS:
        for w in words:
            if w in low:
                return kind
    return None


def find_entity(sentence: str) -> Tuple[Optional[str], Optional[str]]:
    low = sentence.lower()
    best = None
    for alias, canon in COUNTRY_ALIASES.items():
        if re.search(r"\b" + re.escape(alias) + r"\b", low):
            if best is None or len(alias) > len(best[0]):
                best = (alias, canon)
    if best:
        return best[1], "country"
    m = re.search(r"\b([A-Z][A-Za-z&.\-]+(?:\s+[A-Z][A-Za-z&.\-]+){0,3})\b", sentence)
    if m:
        cand = m.group(1).strip()
        if cand.lower() not in STOP and len(cand) > 2:
            return cand, "org"
    return None, None


def find_claims(text: str, page: int = 0, max_claims: int = 40) -> List[Claim]:
    claims: List[Claim] = []
    seen = set()
    for s in sentences(text):
        low = s.lower()
        m = NUM_RE.search(s)
        if not m:
            continue
        value, unit = parse_number(m.group(1), m.group(2))
        if value is None:
            continue
        kind = classify_kind(low)
        has_signal = bool(m.group(2)) or any(
            w in low for w in ("population", "gdp", "revenue", "users", "founded",
                               "area", "inflation", "rate", "percent", "million",
                               "billion", "crore", "lakh", "trillion")
        )
        if kind is None and not has_signal:
            continue
        if kind is None:
            kind = "number"
        if kind != "founded" and unit == "count" and 1900 <= value <= 2100 and not m.group(2):
            continue
        entity, etype = find_entity(s)
        key = (s[:90], round(value, 4))
        if key in seen:
            continue
        seen.add(key)
        claims.append(Claim(sentence=s, raw=m.group(0).strip(), value=value, unit=unit or "",
                            kind=kind, entity=entity, entity_type=etype, page=page))
        if len(claims) >= max_claims:
            break
    return claims
