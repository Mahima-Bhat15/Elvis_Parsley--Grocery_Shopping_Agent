#!/usr/bin/env python3
import os, csv
from datetime import date
from typing import Dict, Any, List, Optional, Callable
from neo4j import GraphDatabase

# ---- Neo4j config from env ----
NEO4J_URI       = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER      = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD  = os.getenv("NEO4J_PASSWORD", "password")
NEO4J_DATABASE  = os.getenv("NEO4J_DATABASE") or None
BATCH_SIZE      = int(os.getenv("BATCH_SIZE", "2000"))

# ---------- helpers ----------
def money(x) -> Optional[float]:
    if x is None: return None
    s = str(x).replace("$","").replace(",","").strip()
    if not s or s.upper() in {"N/A","NA","NONE"}: return None
    try: return float(s)
    except: return None

def mk_offer_id(domain: str, name: str, price: Optional[float], zip_: Optional[str]=None) -> str:
    return f"{domain}|{name}|{price}|{zip_ or ''}|{date.today().isoformat()}"

# ---------- upsert cypher ----------
UPSERT = """
UNWIND $rows AS d
MERGE (st:Store {id:d.store_domain})
  ON CREATE SET st.name=d.store, st.domain=d.store_domain

MERGE (p:Product {id: toLower(d.store_domain)+'::'+toLower(d.product_name)})
  ON CREATE SET p.name=d.product_name
SET p.brand       = coalesce(d.brand, p.brand),
    p.category    = coalesce(d.category, p.category),
    p.subcategory = coalesce(d.subcategory, p.subcategory),
    p.department  = coalesce(d.department, p.department),
    p.size        = coalesce(d.size, p.size),
    p.sku         = coalesce(d.sku, p.sku)

MERGE (st)-[:SELLS]->(p)

MERGE (o:Offer {id:d.offer_id})
  ON CREATE SET
    o.price        = d.price,
    o.list_price   = d.list_price,
    o.currency     = coalesce(d.currency,'USD'),
    o.is_deal      = coalesce(d.is_deal,false),
    o.deal_type    = d.deal_type,
    o.discount_abs = d.discount_abs,
    o.discount_pct = d.discount_pct,
    o.product_url  = d.product_url,
    o.zip          = d.zip,
    o.start_date   = d.start_date
MERGE (o)-[:APPLIES_TO]->(p)
MERGE (o)-[:AT]->(st);
"""

# ---------- mappers (extendable) ----------
def map_walmart(row: Dict[str,Any]) -> Dict[str,Any]:
    # Expected headers per your dataset description
    name = (row.get("PRODUCT_NAME") or "").strip()
    price = money(row.get("PRICE_CURRENT"))
    list_price = money(row.get("PRICE_RETAIL"))
    is_deal = bool(row.get("PROMOTION")) or (price is not None and list_price and price < list_price)
    deal_type = (row.get("PROMOTION") or "").strip() or ("SALE" if is_deal else None)
    domain = "walmart.com"
    return {
        "store": "Walmart",
        "store_domain": domain,
        "product_name": name,
        "brand": (row.get("BRAND") or None),
        "category": (row.get("CATEGORY") or None),
        "subcategory": (row.get("SUBCATEGORY") or None),
        "department": (row.get("DEPARTMENT") or None),
        "size": (row.get("PRODUCT_SIZE") or None),
        "sku": (row.get("SKU") or None),
        "price": price,
        "list_price": list_price,
        "currency": "USD",
        "is_deal": is_deal,
        "deal_type": deal_type,
        "discount_abs": (round(list_price - price, 2) if list_price and price is not None else None),
        "discount_pct": (round(1 - price/list_price, 3) if list_price and price not in (None,0) else None),
        "product_url": row.get("PRODUCT_URL") or None,
        "zip": (row.get("SHIPPING_LOCATION") or None),
        "start_date": date.today().isoformat(),
        "offer_id": mk_offer_id(domain, name, price, row.get("SHIPPING_LOCATION")),
    }

def map_costco(row: Dict[str,Any]) -> Dict[str,Any]:
    # Be lenient with header names that vary
    name = (row.get("Title") or row.get("PRODUCT_NAME") or "").strip()
    price = money(row.get("Price") or row.get("PRICE_CURRENT"))
    list_price = money(row.get("List Price") or row.get("PRICE_RETAIL"))
    promo = row.get("Promotion") or row.get("PROMOTION")
    is_deal = bool(promo) or (price is not None and list_price and price < list_price)
    deal_type = (promo or "").strip() or ("SALE" if is_deal else None)
    domain = "costco.com"
    return {
        "store": "Costco",
        "store_domain": domain,
        "product_name": name,
        "brand": (row.get("Brand") or row.get("BRAND") or None),
        "category": (row.get("Category") or row.get("CATEGORY") or None),
        "subcategory": (row.get("Sub Category") or row.get("SUBCATEGORY") or None),
        "department": (row.get("Department") or row.get("DEPARTMENT") or None),
        "size": (row.get("Product Size") or row.get("PRODUCT_SIZE") or None),
        "sku": (row.get("SKU") or None),
        "price": price,
        "list_price": list_price,
        "currency": (row.get("Currency") or "USD"),
        "is_deal": is_deal,
        "deal_type": deal_type,
        "discount_abs": (round(list_price - price, 2) if list_price and price is not None else None),
        "discount_pct": (round(1 - price/list_price, 3) if list_price and price not in (None,0) else None),
        "product_url": row.get("PRODUCT_URL") or row.get("Url") or None,
        "zip": None,
        "start_date": date.today().isoformat(),
        "offer_id": mk_offer_id(domain, name, price),
    }

# Decide which mapper to use by filename or headers
def detect_mapper(path: str, headers: List[str]) -> Callable[[Dict[str,Any]], Dict[str,Any]]:
    fname = os.path.basename(path).lower()
    hs = {h.lower().strip() for h in headers}

    if "walmart" in fname or {"product_name","price_current","price_retail"} <= hs:
        return map_walmart
    if "costco" in fname or {"title","price"} <= hs or {"product_name","price_current"} <= hs:
        return map_costco
    # default: try Walmart first, then Costco
    if "product_name" in hs and "price_current" in hs:
        return map_walmart
    return map_costco

# ---------- main loader ----------
def load_csv(path: str) -> int:
    if not os.path.exists(path):
        print(f"Not found: {path}")
        return 0

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        mapper = detect_mapper(path, reader.fieldnames or [])
        rows = []
        for r in reader:
            m = mapper(r)
            if not m.get("product_name") or m.get("price") is None:
                continue
            rows.append(m)

    if not rows:
        print(f"No priced rows in {path}")
        return 0

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    total = 0
    try:
        with driver.session(database=NEO4J_DATABASE) as s:
            for i in range(0, len(rows), BATCH_SIZE):
                chunk = rows[i:i+BATCH_SIZE]
                s.run(UPSERT, rows=chunk)
                total += len(chunk)
                print(f"{os.path.basename(path)}: upserted {total}/{len(rows)}")
    finally:
        driver.close()

    print(f"Loaded {total} offers from {path}")
    return total

def main():
    import sys
    if len(sys.argv) < 2:
        print("Usage: python scripts/load_groceries_csv.py data/walmart.csv [data/costco.csv ...]")
        raise SystemExit(2)
    grand = 0
    for p in sys.argv[1:]:
        grand += load_csv(p)
    print(f"✅ Done. Total offers loaded: {grand}")

if __name__ == "__main__":
    main()
