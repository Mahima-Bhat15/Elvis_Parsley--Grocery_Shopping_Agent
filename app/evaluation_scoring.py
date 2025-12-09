# scripts/eval_score.py
import json, re, statistics

def norm(s): return (s or "").lower()
def has_terms(prod, terms):
    bag = f"{norm(prod.get('product_name'))} {norm(prod.get('category'))}"
    return all(t in bag for t in terms)

def in_allowed_category(prod, allowed):
    if not allowed: return True
    cat = norm(prod.get("category"))
    return any(a in cat for a in allowed)

def within_price_cap(prod, cap):
    if cap is None: return True
    offers = prod.get("offers") or []
    for o in offers:
        p=o.get("price")
        if p is None: continue
        if p<=cap: return True
    return False

def has_store(prod, stores):
    if not stores: return True
    offers = prod.get("offers") or []
    seen=set(o.get("store_domain") for o in offers if o.get("store_domain"))
    return all(s in seen or any(s in (o.get("store_domain") or "") for o in offers) for s in stores)

latencies=[]
n=0; m1=m2=m3=m4=0
with open("/tmp/eval_runs.jsonl") as f:
    for line in f:
        r=json.loads(line)
        n+=1
        items=r["result"] if isinstance(r["result"], list) else (r["result"].get("results") or [])
        latencies.append(r["latency"])
        # M1
        term_ok = any(has_terms(x, r["terms"]) for x in items) if r["terms"] else True
        m1 += int(term_ok)
        # M2
        cat_ok = all(in_allowed_category(x, r["allowed_categories"]) for x in items)
        m2 += int(cat_ok)
        # M3
        price_ok = all(within_price_cap(x, r["max_price"]) for x in items)
        m3 += int(price_ok)
        # M4
        sc_ok = has_store({"offers": sum([x.get("offers") or [] for x in items],[])}, r["stores"])
        m4 += int(sc_ok)

print(f"M1 term recall: {m1/n:.2%}")
print(f"M2 category precision: {m2/n:.2%}")
print(f"M3 price cap compliance: {m3/n:.2%}")
print(f"M4 store coverage: {m4/n:.2%}")
print(f"M13 latency P50={statistics.median(latencies):.2f}s P95={sorted(latencies)[int(0.95*len(latencies))-1]:.2f}s")
