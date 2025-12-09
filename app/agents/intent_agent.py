# app/agents/intent_agent.py
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import List, Optional

STORE_ALIASES = {
    "target": "target.com",
    "walmart": "walmart.com",
    "instacart": "instacart.com",
    "kroger": "kroger.com",
    "costco": "costco.com",
    "safeway": "safeway.com",
}

# Map head terms to canonical category hints for the KG
TERM_TO_CATEGORY = {
    # produce
    "avocado": "avocado",
    "tomato": "tomato",
    "cucumber": "cucumber",
    "banana": "banana",
    "pepper": "pepper",
    "onion": "onion",
    "lettuce": "lettuce",
    "broccoli": "broccoli",
    "mushroom": "mushroom",
    "vegetable": "vegetable",
    "veggies": "vegetable",
    "produce": "produce",
    # dairy
    "milk": "milk",
    "yogurt": "yogurt",
    "cheese": "cheese",
    "butter": "butter",
    "eggs": "eggs",
    # cereal & pantry
    "cereal": "cereal",
    "oats": "cereal",
    "granola": "cereal",
    "pasta": "pasta",
    "rice": "rice",
}

# “Nearby but wrong” items to exclude when a head term is present
EXCLUDES_FOR_TERM = {
    "milk": ["yogurt", "pudding", "shake", "creamer"],
    "avocado": ["guacamole"],  # unless explicitly asked
    "tomato": ["sauce", "ketchup", "paste"],  # unless explicitly asked
    "cereal": ["oatmeal cups", "instant oatmeal"]  # tune as needed
}

@dataclass
class ParsedIntent:
    # hard filters
    stores: List[str]
    categories: List[str]
    max_price: Optional[float]
    deal_only: bool

    # semantic helpers
    head_terms: List[str]
    must_include: List[str]
    must_exclude: List[str]
    require_organic: bool


def _tokens(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z0-9]+", (text or "").lower())


def _detect_stores(toks: List[str]) -> List[str]:
    found = []
    for t in toks:
        if t in STORE_ALIASES:
            dom = STORE_ALIASES[t]
            if dom not in found:
                found.append(dom)
    return found


def _detect_price(text: str) -> Optional[float]:
    # “under $3”, “below 3”, “max 2.50”, “<= 1.99”
    m = re.search(r"(?:under|below|less than|max|<=?)\s*\$?\s*([0-9]+(?:\.[0-9]+)?)", text, flags=re.I)
    if m:
        try:
            return float(m.group(1))
        except Exception:
            return None
    # lone $number
    m2 = re.search(r"\$\s*([0-9]+(?:\.[0-9]+)?)", text)
    if m2:
        try:
            return float(m2.group(1))
        except Exception:
            return None
    return None


def _detect_deals_only(text: str) -> bool:
    return bool(re.search(r"\b(deal|deals|on sale|discount|rollback)\b", text, flags=re.I))


def _detect_head_terms(toks: List[str]) -> List[str]:
    heads = []
    for t in toks:
        if t in TERM_TO_CATEGORY and t not in heads:
            heads.append(t)
    return heads


def _detect_categories(heads: List[str]) -> List[str]:
    cats = []
    for h in heads:
        c = TERM_TO_CATEGORY.get(h)
        if c and c not in cats:
            cats.append(c)
    # if no head, keep empty (UI / orchestrator will not force category)
    return cats


def parse_query(text: str) -> ParsedIntent:
    text = text or ""
    toks = _tokens(text)

    # 1) stores
    stores = _detect_stores(toks)

    # 2) head terms & categories
    heads = _detect_head_terms(toks)
    categories = _detect_categories(heads)

    # 3) organic
    require_organic = "organic" in toks

    # 4) include/exclude lists
    must_include = heads.copy()  # ensure we search names with head term
    must_exclude: List[str] = []
    for h in heads:
        for bad in EXCLUDES_FOR_TERM.get(h, []):
            if bad not in must_exclude:
                must_exclude.append(bad)

    # 5) price & deals
    max_price = _detect_price(text)
    deal_only = _detect_deals_only(text)

    return ParsedIntent(
        stores=stores,
        categories=categories,
        max_price=max_price,
        deal_only=deal_only,
        head_terms=heads,
        must_include=must_include,
        must_exclude=must_exclude,
        require_organic=require_organic,
    )
