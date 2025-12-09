# scripts/clean_target_dump.py
import argparse, json, re, sys, os
from typing import List, Dict, Any

PRICE_KEYS = ("Price", "PRICE", "price")

def _clean_ctrl(s: str) -> str:
    return re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", s)

def _parse_fenced_json(text: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    # ```json ... ``` blocks
    for m in re.finditer(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.S|re.I):
        block = m.group(1).strip()
        # try array first
        try:
            data = json.loads(block)
            if isinstance(data, list):
                rows.extend(data)
                continue
            if isinstance(data, dict):
                # common wrapper { "items": [...] }
                if "items" in data and isinstance(data["items"], list):
                    rows.extend(data["items"])
                    continue
                rows.append(data)
                continue
        except Exception:
            pass
        # try to find first [...] JSON inside the block
        m2 = re.search(r"\[[\s\S]*\]", block)
        if m2:
            try:
                arr = json.loads(m2.group(0))
                if isinstance(arr, list):
                    rows.extend(arr)
            except Exception:
                pass
    return rows

def _parse_markdown_tables(text: str) -> List[Dict[str, Any]]:
    """
    Parse GitHub-style markdown tables:
    | Col A | Col B |
    | ----- | ----- |
    | val1  | val2  |
    """
    rows: List[Dict[str, Any]] = []
    lines = [ln.rstrip() for ln in text.splitlines()]
    i = 0
    while i < len(lines):
        if lines[i].strip().startswith("|") and i + 1 < len(lines) and set(lines[i+1].strip()) <= set("|:- "):
            header_line = lines[i]
            sep_line = lines[i+1]
            i += 2
            headers = [h.strip().strip("`") for h in header_line.strip().strip("|").split("|")]
            # read body until blank or non-pipe line
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                # pad/truncate
                if len(cells) < len(headers):
                    cells += [""] * (len(headers) - len(cells))
                elif len(cells) > len(headers):
                    cells = cells[:len(headers)]
                obj = dict(zip(headers, cells))
                rows.append(obj)
                i += 1
            continue
        i += 1
    return rows

def _coerce_price(x):
    if x is None or x == "":
        return None
    s = str(x)
    s = s.split("/")[0]  # drop '/ounce'
    s = s.replace("$", "").replace(",", "").strip()
    try:
        return float(s)
    except Exception:
        return None

def _normalize(obj: Dict[str, Any]) -> Dict[str, Any]:
    # Map various field spellings to a consistent shape
    name = obj.get("Product Name") or obj.get("title") or obj.get("name")
    brand = obj.get("Brand") or obj.get("brand")
    price = None
    for k in PRICE_KEYS:
        if k in obj:
            price = _coerce_price(obj[k])
            break
    product_url = obj.get("Product Link") or obj.get("url") or obj.get("link")
    size = obj.get("Size") or obj.get("Product Size") or obj.get("size")
    sku = obj.get("SKU") or obj.get("sku")
    rating = obj.get("Rating Value") or obj.get("rating")
    rating_count = obj.get("Number of Ratings") or obj.get("rating_count")
    ppu = obj.get("Price Per Unit") or obj.get("price_per_unit")

    return {
        "Product Name": name,
        "Brand": brand,
        "Price": price,
        "Price Per Unit": ppu,
        "Rating Value": rating,
        "Number of Ratings": rating_count,
        "Product Link": product_url,
        "Size": size,
        "SKU": sku,
    }

def load_any(path: str) -> List[Dict[str, Any]]:
    ext = os.path.splitext(path)[1].lower()
    text = _clean_ctrl(open(path, "r", encoding="utf-8").read())
    out: List[Dict[str, Any]] = []

    if ext == ".json":
        try:
            data = json.loads(text)
            if isinstance(data, list):
                out.extend(data)
            elif isinstance(data, dict) and "items" in data and isinstance(data["items"], list):
                out.extend(data["items"])
            elif isinstance(data, dict):
                out.append(data)
        except Exception:
            # might be markdown-ish JSON dumps; fall through to fenced/table parsing
            pass
        # also parse any fences/tables present
        out.extend(_parse_fenced_json(text))
        out.extend(_parse_markdown_tables(text))
        return out

    if ext == ".jsonl":
        # one JSON object per line OR markdown-ish content; try both
        for i, line in enumerate(text.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                # ignore; will scan fenced/table below
                pass
        # Also try to extract fenced arrays/tables from the entire file
        out.extend(_parse_fenced_json(text))
        out.extend(_parse_markdown_tables(text))
        return out

    if ext in (".md", ".markdown"):
        out.extend(_parse_fenced_json(text))
        out.extend(_parse_markdown_tables(text))
        return out

    # default attempt
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
    except Exception:
        pass
    # fallback: fenced/table extraction
    out.extend(_parse_fenced_json(text))
    out.extend(_parse_markdown_tables(text))
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+", help="Input files (md/json/jsonl)")
    ap.add_argument("-o", "--out", default="data/target_veggies_clean.json", help="Output JSON file")
    args = ap.parse_args()

    all_raw: List[Dict[str, Any]] = []
    for p in args.inputs:
        if not os.path.exists(p):
            print(f"⚠️  Missing file: {p}")
            continue
        got = load_any(p)
        print(f"Read {len(got)} rows from {p}")
        all_raw.extend(got)

    # normalize and dedupe on (Product Name, Product Link, Price)
    norm = []
    seen = set()
    for r in all_raw:
        n = _normalize(r)
        if not n.get("Product Name"):
            continue
        key = (n.get("Product Name"), n.get("Product Link"), n.get("Price"))
        if key in seen:
            continue
        seen.add(key)
        norm.append(n)

    print(f"Total normalized rows: {len(norm)}")
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(norm, f, indent=2)
    print(f"✅ Wrote {len(norm)} clean rows to {args.out}")

if __name__ == "__main__":
    main()
