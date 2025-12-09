# app/agents/intent_parser.py
from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel
import re

# quick lexicons
STORE_MAP = {
    "walmart": "walmart.com",
    "target": "target.com",
    "costco": "costco.com",
    "instacart": "instacart.com",   # if you later ingest
    "kroger": "kroger.com",
}
CATEGORY_SYNONYMS = {
    "veg": "produce", "veggies": "produce", "vegetable": "produce", "vegetables": "produce",
    "fruit": "produce", "fruits": "produce",
    "dairy": "dairy", "milk": "dairy",
    "meat": "meat", "beef": "meat", "chicken": "meat",
}
# product name normalizations (helps for plural → singular, common produce)
TERM_NORMALIZE = {
    "cucumbers": "cucumber",
    "avocados": "avocado",
    "bananas": "banana",
    "potatoes": "potato",
    "tomatoes": "tomato",
}

DEAL_TRIGGERS = {"deal", "deals", "on sale", "sale", "bogo", "discount", "cheapest"}
PRICE_RE = re.compile(r"(?:under|below|<=?|less than)\s*\$?\s*(\d+(?:\.\d{1,2})?)", re.I)
SIZE_OZ_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:oz|ounce(?:s)?)", re.I)
SIZE_GAL_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:gal|gallon(?:s)?)", re.I)

class QueryIntent(BaseModel):
    # core
    terms: List[str] = []
    categories: List[str] = []
    include_domains: List[str] = []
    exclude_domains: List[str] = []
    # constraints
    max_price: Optional[float] = None
    size_oz: Optional[float] = None
    size_gal: Optional[float] = None
    deal_only: bool = False

def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9\-%]+", text.lower())

def parse_intent(user_text: str) -> QueryIntent:
    t = user_text.lower()

    # stores
    include_domains = []
    for k, dom in STORE_MAP.items():
        # "from walmart / at walmart / walmart" → include walmart
        if re.search(rf"(?:from|at|in)\s+{k}\b|\b{k}\b", t):
            include_domains.append(dom)

    # max price
    max_price = None
    m = PRICE_RE.search(t)
    if m:
        try:
            max_price = float(m.group(1))
        except Exception:
            pass

    # sizes (if given)
    size_oz = None
    size_gal = None
    m = SIZE_OZ_RE.search(t)
    if m:
        try: size_oz = float(m.group(1))
        except: pass
    m = SIZE_GAL_RE.search(t)
    if m:
        try: size_gal = float(m.group(1))
        except: pass

    # deal-only?
    deal_only = any(w in t for w in DEAL_TRIGGERS if w != "cheapest")
    # note: if user says "cheapest ..." we don't force deals-only; we let price win

    # category hints
    cats = set()
    for k, v in CATEGORY_SYNONYMS.items():
        if re.search(rf"\b{k}\b", t):
            cats.add(v)

    # product terms = user words minus store names and stopwords
    toks = _tokenize(t)
    stop = set(list(STORE_MAP.keys()) + ["best", "price", "prices", "give", "me", "the", "for", "from", "at", "on"])
    terms = []
    for w in toks:
        if w in stop: 
            continue
        w = TERM_NORMALIZE.get(w, w)
        # avoid replacing “milk” if user already said dairy category
        terms.append(w)

    # Light heuristic: if user asked “price of cucumbers” → prefer produce
    if any(x in t for x in ["vegetable", "vegetables", "veggies", "cucumber", "tomato", "lettuce", "avocado"]):
        cats.add("produce")

    return QueryIntent(
        terms=[w for w in terms if not w.isdigit()],
        categories=sorted(cats),
        include_domains=sorted(set(include_domains)),
        exclude_domains=[],
        max_price=max_price,
        size_oz=size_oz,
        size_gal=size_gal,
        deal_only=deal_only,
    )
