# scripts/load_target_milk_json.py
import json, hashlib, re, sys
from datetime import date
from neo4j import GraphDatabase
from pathlib import Path

# --- config: read from env or just edit these three ---
import os
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
NEO4J_DATABASE = (os.getenv("NEO4J_DATABASE") or "").strip() or None  # optional

STORE_NAME = "Target"
STORE_DOMAIN = "target.com"
CATEGORY = "milk"   # force category so your queries pick it up

UPSERT = """
UNWIND $items AS d
MERGE (s:Store {id: d.store_domain})
  ON CREATE SET s.name = d.store, s.domain = d.store_domain
MERGE (p:Product {id: d.product_id})
  ON CREATE SET p.name = d.product_name, p.brand = d.brand, p.category = d.category
  ON MATCH SET  p.brand = coalesce(p.brand, d.brand),
                p.category = coalesce(p.category, d.category)
MERGE (s)-[:SELLS]->(p)
MERGE (o:Offer {id: d.id})
SET   o.price        = d.price,
      o.list_price   = d.list_price,
      o.currency     = d.currency,
      o.deal_type    = d.deal_type,
      o.is_deal      = coalesce(d.is_deal, false),
      o.discount_abs = d.discount_abs,
      o.discount_pct = d.discount_pct,
      o.product_url  = d.product_url,
      o.start_date   = date(d.start_date)
MERGE (o)-[:APPLIES_TO]->(p)
MERGE (o)-[:AT]->(s);
"""

def offer_id(domain: str, product_name: str, price: float, sd: str) -> str:
    key = f"{domain}|{product_name}|{price}|{sd}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()

def product_id(domain: str, product_name: str) -> str:
    return f"{domain}::{product_name.lower()}"

def norm_brand(b: str | None) -> str | None:
    if not b:
        return b
    # strip weird symbols like ™, ® and extra whitespace
    b = re.sub(r"[™®]", "", b)
    return re.sub(r"\s+", " ", b).strip()

def load_json_array(path: str) -> list[dict]:
    text = Path(path).read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"{path} is empty")
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError("Expected a JSON array at top level")
    return data

def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/load_target_milk_json.py data/target_milk.json")
        sys.exit(1)

    src = sys.argv[1]
    rows = load_json_array(src)

    today = date.today().isoformat()
    items = []
    bad = 0

    for r in rows:
        # Your JSON has: url, title, brand, price, size, sku
        url   = r.get("url")
        title = (r.get("title") or "").strip()
        brand = norm_brand(r.get("brand"))
        price = r.get("price")
        size  = (r.get("size") or "").strip()  # optional
        # sku present but not required here
        if not title or price is None:
            bad += 1
            continue

        # Build unified shape
        d = {
            "store": STORE_NAME,
            "store_domain": STORE_DOMAIN,
            "product_name": title,
            "brand": brand,
            "category": CATEGORY,
            "price": float(price),
            "list_price": None,
            "currency": "USD",
            "deal_type": None,
            "is_deal": False,
            "discount_abs": None,
            "discount_pct": None,
            "product_url": url,
            "start_date": today,
        }
        d["product_id"] = product_id(STORE_DOMAIN, d["product_name"])
        d["id"] = offer_id(STORE_DOMAIN, d["product_name"], d["price"], today)
        items.append(d)

    print(f"Prepared {len(items)} milk items (skipped {bad}) from {src}")

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    sess_kwargs = {}
    if NEO4J_DATABASE:
        sess_kwargs["database"] = NEO4J_DATABASE

    with driver.session(**sess_kwargs) as s:
        s.run(UPSERT, items=items)
    driver.close()
    print("✅ Upsert complete.")

if __name__ == "__main__":
    main()
