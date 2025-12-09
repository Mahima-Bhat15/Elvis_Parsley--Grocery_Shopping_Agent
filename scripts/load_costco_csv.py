#!/usr/bin/env python3
import csv, os, re, math
from datetime import date
from neo4j import GraphDatabase

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE")  # optional

STORE_NAME = "Costco"
STORE_DOMAIN = "costco.com"

UPSERT = """
UNWIND $rows AS d
WITH d,
     toLower(d.store_domain) AS dom,
     trim(toLower(d.product_name)) AS pname
MERGE (st:Store {id: d.store_domain})
  ON CREATE SET st.name = d.store, st.domain = d.store_domain
MERGE (p:Product {id: dom + '::' + pname})
  ON CREATE SET p.name = d.product_name
SET  p.brand      = coalesce(d.brand, p.brand),
     p.category   = coalesce(d.category, p.category),
     p.size       = coalesce(d.size, p.size),
     p.rating     = coalesce(d.rating, p.rating),
     p.features   = coalesce(d.features, p.features),
     p.description= coalesce(d.description, p.description)

MERGE (st)-[:SELLS]->(p)

MERGE (o:Offer {id: d.offer_id})
  ON CREATE SET
    o.price        = d.price,
    o.list_price   = d.list_price,
    o.currency     = coalesce(d.currency, 'USD'),
    o.is_deal      = coalesce(d.is_deal, false),
    o.deal_type    = d.deal_type,
    o.discount_abs = d.discount_abs,
    o.discount_pct = d.discount_pct,
    o.start_date   = d.start_date,
    o.end_date     = d.end_date,
    o.terms        = d.terms,
    o.product_url  = d.product_url
SET  o.price        = coalesce(d.price, o.price),
     o.list_price   = coalesce(d.list_price, o.list_price),
     o.currency     = coalesce(d.currency, o.currency),
     o.is_deal      = coalesce(d.is_deal, o.is_deal),
     o.deal_type    = coalesce(d.deal_type, o.deal_type),
     o.discount_abs = coalesce(d.discount_abs, o.discount_abs),
     o.discount_pct = coalesce(d.discount_pct, o.discount_pct),
     o.product_url  = coalesce(d.product_url, o.product_url)

MERGE (o)-[:APPLIES_TO]->(p)
MERGE (o)-[:AT]->(st);
"""

def parse_money(s):
    if s is None: return None
    s = str(s).strip()
    if not s: return None
    s = s.replace("$","").replace(",","").strip()
    try:
        return float(s)
    except:
        return None

def parse_discount(s, price):
    """
    Returns: (discount_abs, discount_pct, list_price, is_deal, deal_type)
    Accepts formats like:
      "10%"  -> pct
      "10 %"
      "$2 off", "2 off", "Save $2" -> abs
    """
    if s is None: return (None, None, None, False, None)
    text = str(s).strip().lower()
    if not text: return (None, None, None, False, None)

    # percent like "10%" or "10 %"
    m = re.search(r"(\d+(\.\d+)?)\s*%", text)
    if m:
        pct = float(m.group(1)) / 100.0
        lp = None
        if price is not None and pct < 1:
            lp = round(price / (1 - pct), 2)
        return (None, pct, lp, True, "SALE")

    # dollar off like "$2 off" / "save $2"
    m = re.search(r"\$?\s*(\d+(\.\d+)?)\s*(off|save)", text)
    if m:
        disc = float(m.group(1))
        lp = price + disc if price is not None else None
        return (disc, None, lp, True, "SALE")

    # "$12.99" in discount field (some feeds misuse the column)
    money = parse_money(text)
    if money is not None:
        if price is not None and money > price:
            return (money - price, (money - price)/money if money else None, money, True, "SALE")
        # ambiguous → treat as list_price if > price
    return (None, None, None, False, None)

def main(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            product_name = (r.get("Title") or "").strip()
            if not product_name:
                continue

            price = parse_money(r.get("Price"))
            currency = (r.get("Currency") or "USD").strip() or "USD"
            subcat = (r.get("Sub Category") or "").strip() or None
            rating = r.get("Rating")
            try:
                rating = float(rating) if rating not in (None, "", "NA") else None
            except:
                rating = None
            features = (r.get("Feature") or "").strip() or None
            desc = (r.get("Product Description") or "").strip() or None

            disc_abs, disc_pct, list_price, is_deal, deal_type = parse_discount(r.get("Discount"), price)

            # stable offer id: store|product|price|yyyymmdd
            start_date = date.today().isoformat()
            offer_id = f"{STORE_DOMAIN}|{product_name}|{price}|{start_date}"

            rows.append({
                "store": STORE_NAME,
                "store_domain": STORE_DOMAIN,
                "product_name": product_name,
                "brand": None,
                "category": subcat,
                "size": None,
                "rating": rating,
                "features": features,
                "description": desc,
                "price": price,
                "list_price": list_price,
                "currency": currency,
                "is_deal": is_deal,
                "deal_type": deal_type,
                "discount_abs": disc_abs,
                "discount_pct": disc_pct,
                "product_url": None,
                "start_date": start_date,
                "end_date": None,
                "terms": None,
                "offer_id": offer_id,
            })

    drv = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    with drv.session(database=NEO4J_DATABASE) as s:
        s.run(UPSERT, rows=rows)
    drv.close()
    print(f"Loaded {len(rows)} Costco offers into Neo4j.")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python scripts/load_costco_csv.py data/costco.csv")
        raise SystemExit(2)
    main(sys.argv[1])
