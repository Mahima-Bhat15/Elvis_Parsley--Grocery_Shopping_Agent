# save as scripts/eval_run.py and run with: python3 scripts/eval_run.py
import json, time, requests, csv
API="http://localhost:8000/best_cards_live"

def parse_list(s): return [t.strip() for t in s.split("|") if t.strip()]
def as_float(s): return float(s) if s else None

rows=[]
with open("eval_queries.csv") as f:
    rdr=csv.DictReader(f)
    for r in rdr:
        payload={"message": r["query"]}
        if r["max_price"]:
            payload["max_price"]=as_float(r["max_price"])
        t0=time.time()
        resp=requests.post(API, json=payload, timeout=60)
        dt=time.time()-t0
        data=resp.json()
        rows.append({
            "query": r["query"],
            "terms": parse_list(r["terms"]),
            "allowed_categories": parse_list(r["allowed_categories"]),
            "stores": parse_list(r["stores"]),
            "max_price": as_float(r["max_price"]),
            "latency": dt,
            "result": data.get("results", data)
        })

with open("/tmp/eval_runs.jsonl","w") as w:
    for r in rows: w.write(json.dumps(r)+"\n")
print(f"wrote {len(rows)} results → /tmp/eval_runs.jsonl")
