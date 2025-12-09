#!/usr/bin/env python3
import csv, os, re
from datetime import date
from neo4j import GraphDatabase

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE")  # optional

STORE_NAME = "Walmart"
STORE_DOMAIN = "walmart.com"

UPSERT = """
UNWIND $rows AS d
MERGE (st:Store {id:d.store_domain})
  ON CREATE SET st.name=d.store, st.domain=d.store_domain

MERGE (p:Product {id:toLower(d.store_domain)+'::'+toLower(d.product_name)})
  ON CREATE SET p.name=d.product_name
SET  p.brand       = coalesce(d.brand, p.brand),
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

def parse_money(v):
    if not v: return None
    s = str(v).replace("$","").replace(",","").strip()
    try: return float(s)
    except: return None

def main(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            name = (r.get("PRODUCT_NAME") or "").strip()
            if not name: continue
            price = parse_money(r.get("PRICE_CURRENT"))
            list_price = parse_money(r.get("PRICE_RETAIL"))
            is_deal = False
            deal_type = None
            if r.get("PROMOTION"):
                is_deal = True
                deal_type = (r["PROMOTION"] or "").strip()

            offer_id = f"{STORE_DOMAIN}|{name}|{price}|{date.today().isoformat()}"
            rows.append({
                "store": STORE_NAME,
                "store_domain": STORE_DOMAIN,
                "product_name": name,
                "brand": (r.get("BRAND") or "").strip() or None,
                "category": (r.get("CATEGORY") or "").strip() or None,
                "subcategory": (r.get("SUBCATEGORY") or "").strip() or None,
                "department": (r.get("DEPARTMENT") or "").strip() or None,
                "sku": (r.get("SKU") or "").strip() or None,
                "size": (r.get("PRODUCT_SIZE") or "").strip() or None,
                "price": price,
                "list_price": list_price,
                "currency": "USD",
                "is_deal": is_deal,
                "deal_type": deal_type,
                "discount_abs": None if not (price and list_price) else round(list_price - price, 2),
                "discount_pct": None if not (price and list_price and list_price>0)
                                else round(1 - price / list_price, 3),
                "product_url": r.get("PRODUCT_URL") or None,
                "zip": (r.get("SHIPPING_LOCATION") or "").strip() or None,
                "start_date": date.today().isoformat(),
                "offer_id": offer_id,
            })

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with driver.session(database=NEO4J_DATABASE) as s:
        s.run(UPSERT, rows=rows)
    driver.close()
    print(f"Loaded {len(rows)} Walmart grocery offers into Neo4j.")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python scripts/load_walmart_grocery_csv.py data/walmart.csv")
        raise SystemExit(2)
    main(sys.argv[1])
