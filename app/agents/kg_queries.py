# app/agents/kg_queries.py

# -------------------------
# Write generic offers (stores image_url too)
# -------------------------
UPSERT_CYPHER = """
UNWIND $items AS d
WITH d,
     toLower(d.store_domain) AS dom,
     trim(toLower(d.product_name)) AS pname

MERGE (st:Store {id: d.store_domain})
  ON CREATE SET st.name = d.store, st.domain = d.store_domain

WITH d, st, dom + '::' + pname AS pid
MERGE (p:Product {id: pid})
  ON CREATE SET p.name     = d.product_name,
                p.brand    = d.brand,
                p.category = d.category,
                p.size     = d.size

MERGE (st)-[:SELLS]->(p)

MERGE (o:Offer {id: d.id})
  ON CREATE SET
    o.price        = d.price,
    o.list_price   = d.list_price,
    o.currency     = coalesce(d.currency,'USD'),
    o.is_deal      = coalesce(d.is_deal,false),
    o.deal_type    = d.deal_type,
    o.discount_abs = d.discount_abs,
    o.discount_pct = d.discount_pct,
    o.start_date   = d.start_date,
    o.end_date     = d.end_date,
    o.terms        = d.terms,
    o.product_url  = d.product_url,
    o.image_url    = d.image_url
  ON MATCH SET
    o.price        = coalesce(d.price, o.price),
    o.list_price   = coalesce(d.list_price, o.list_price),
    o.is_deal      = coalesce(d.is_deal, o.is_deal),
    o.deal_type    = coalesce(d.deal_type, o.deal_type),
    o.discount_abs = coalesce(d.discount_abs, o.discount_abs),
    o.discount_pct = coalesce(d.discount_pct, o.discount_pct),
    o.product_url  = coalesce(d.product_url, o.product_url),
    o.image_url    = coalesce(d.image_url, o.image_url)

MERGE (o)-[:APPLIES_TO]->(p)
MERGE (o)-[:AT]->(st);
"""

# -------------------------
# Simple “best prices” (top up to 3 offers per product)
# -------------------------
SEARCH_BEST_PRICES = """
WITH [t IN split(toLower($q), ' ') WHERE t <> ''] AS terms,
     $stores AS stores
MATCH (st:Store)-[:SELLS]->(p:Product)
WHERE (stores IS NULL OR st.id IN stores OR st.domain IN stores)
  AND ($q = '' OR any(t IN terms WHERE toLower(p.name) CONTAINS t))
OPTIONAL MATCH (o:Offer)-[:APPLIES_TO]->(p)
WHERE ($maxPrice IS NULL OR (o.price IS NOT NULL AND o.price <= $maxPrice))
  AND ($categories IS NULL OR p.category IN $categories)
WITH p, st, o
ORDER BY coalesce(o.price, 9e9) ASC, coalesce(o.discount_pct,0) DESC
WITH p, collect({
  store: st.name,
  store_domain: coalesce(st.id, st.domain),
  price: o.price,
  list_price: o.list_price,
  is_deal: o.is_deal,
  deal_type: o.deal_type,
  discount_pct: o.discount_pct,
  discount_abs: o.discount_abs,
  product_url: o.product_url,
  image_url: o.image_url
}) AS offers
WITH p, [x IN offers WHERE x.price IS NOT NULL][0..3] AS top_offers
RETURN p.name AS product_name, p.brand AS brand, p.category AS category, top_offers AS offers
LIMIT 25;
"""

# -------------------------
# Legacy deals-only view
# -------------------------
SEARCH_DEALS = """
MATCH (st:Store)-[:SELLS]->(p:Product)
MATCH (o:Offer {is_deal:true})-[:APPLIES_TO]->(p)
WHERE (toLower(p.name) CONTAINS toLower($q) OR $q = "")
  AND ($maxPrice IS NULL OR (o.price IS NOT NULL AND o.price <= $maxPrice))
  AND ($categories IS NULL OR p.category IN $categories)
  AND (o.end_date IS NULL OR o.end_date >= $today)
WITH p, st, o
ORDER BY coalesce(o.discount_pct,0) DESC, coalesce(o.discount_abs,0) DESC
RETURN p.name AS product_name,
       st.name AS store, st.domain AS store_domain,
       o.price AS deal_price, o.list_price AS list_price,
       o.discount_abs AS discount_abs, o.discount_pct AS discount_pct,
       o.deal_type AS deal_type, o.start_date AS start_date, o.end_date AS end_date
LIMIT 25;
"""

# -------------------------
# Best deals products (top 3 offers per product, order by savings then price)
# -------------------------
SEARCH_BEST_DEALS_PRODUCTS = """
WITH [t IN split(toLower($q), ' ') WHERE t <> ''] AS terms,
     $stores AS stores
MATCH (st:Store)-[:SELLS]->(p:Product)
WHERE (stores IS NULL OR st.id IN stores OR st.domain IN stores)
  AND ($q = '' OR any(t IN terms WHERE toLower(p.name) CONTAINS t))
MATCH (o:Offer)-[:APPLIES_TO]->(p)
WITH p, st, o
ORDER BY coalesce(o.discount_pct, 0) DESC, coalesce(o.price, 1e9) ASC
WITH p, collect({
  store: st.name,
  store_domain: coalesce(st.id, st.domain),
  price: o.price,
  list_price: o.list_price,
  currency: o.currency,
  is_deal: o.is_deal,
  deal_type: o.deal_type,
  discount_abs: o.discount_abs,
  discount_pct: o.discount_pct,
  product_url: o.product_url,
  image_url: o.image_url
}) AS offers
WITH p, [x IN offers WHERE x.price IS NOT NULL][0..3] AS top_offers
WHERE size(top_offers) > 0
RETURN p.name AS product_name,
       p.brand AS brand,
       p.category AS category,
       top_offers AS offers
ORDER BY
  coalesce(top_offers[0].discount_pct, 0) DESC,
  coalesce(top_offers[0].price, 1e9) ASC
LIMIT $limit;
"""

# -------------------------
# Filtered best prices (no variable LIMIT; uses list slicing)
# -------------------------
SEARCH_BEST_PRICES_FILTERED = """
WITH
  coalesce($q, "") AS q,
  [t IN split(toLower(coalesce($q, "")), " ") WHERE t <> ""] AS terms,
  CASE WHEN $stores IS NULL OR size($stores)=0 THEN NULL ELSE $stores END AS stores,
  CASE WHEN $categories IS NULL OR size($categories)=0 THEN NULL ELSE [c IN $categories | toLower(c)] END AS cats,
  $maxPrice AS maxPrice,
  $dealOnly AS dealOnly,
  toInteger(coalesce($limit, 24)) AS lim

MATCH (s:Store)-[:SELLS]->(p:Product)<-[:APPLIES_TO]-(o:Offer)
WHERE
  (size(terms)=0 OR any(t IN terms WHERE toLower(p.name) CONTAINS t))
  AND (stores IS NULL OR s.domain IN stores OR s.id IN stores)
  AND (
        cats IS NULL
        OR any(c IN cats WHERE toLower(coalesce(p.category, "")) CONTAINS c
                          OR toLower(p.name) CONTAINS c)
      )
  AND (maxPrice IS NULL OR o.price <= maxPrice)
  AND (dealOnly = false OR coalesce(o.is_deal,false) = true)

WITH p, s, o, lim
ORDER BY o.price ASC, coalesce(o.is_deal,false) DESC

// keep top 3 offers per product
WITH p, s, collect(o)[0..3] AS offs, lim
WITH
  p, lim,
  [o IN offs |
    {
      store: s.name,
      store_domain: coalesce(s.id, s.domain),
      price: o.price,
      list_price: o.list_price,
      currency: o.currency,
      is_deal: o.is_deal,
      deal_type: o.deal_type,
      discount_abs: o.discount_abs,
      discount_pct: o.discount_pct,
      product_url: o.product_url,
      image_url: o.image_url
    }
  ] AS offers

// Avoid LIMIT variable by slicing a collected list
WITH collect({
  product_name: p.name,
  brand: p.brand,
  category: p.category,
  offers: offers
}) AS rows, lim

UNWIND rows[0..lim] AS row
RETURN
  row.product_name AS product_name,
  row.brand AS brand,
  row.category AS category,
  row.offers AS offers;
"""

# -------------------------
# Update product image
# -------------------------
UPDATE_PRODUCT_IMAGE = """
MATCH (p:Product {id: $product_id})
SET p.image_url = $image_url
RETURN p.id AS id
"""
