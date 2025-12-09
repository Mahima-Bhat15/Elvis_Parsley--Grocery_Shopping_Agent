import re, json

def _load_any(path):
    """
    Accepts .json (array or object-with-items) or .jsonl.
    Cleans control chars and strips markdown fences.
    """
    def _clean_text(t: str) -> str:
        # remove control chars except \t \n \r
        t = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", t)
        t = t.strip()
        # strip ```json ... ``` fences if present
        if t.startswith("```"):
            t = t.strip("`")
            nl = t.find("\n")
            if nl != -1:
                t = t[nl+1:]
            t = t.strip()
        return t

    if path.lower().endswith(".jsonl"):
        rows = []
        with open(path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                line = _clean_text(line)
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as e:
                    print(f"⚠️  Skip bad JSON on line {i}: {e}")
        return rows

    # .json path
    with open(path, "r", encoding="utf-8") as f:
        text = _clean_text(f.read())
        if not text:
            print("⚠️  File is empty after cleaning.")
            return []
        # If there’s markdown/prose, try to extract the first {...} or [...]
        if not (text.lstrip().startswith("{") or text.lstrip().startswith("[")):
            # try to grab the largest JSON block
            m = re.search(r"(\{.*\}|\[.*\])", text, flags=re.DOTALL)
            if m:
                text = m.group(1)
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            print(f"❌ Not valid JSON: {e}")
            return []

        if isinstance(data, dict) and "items" in data:
            return data["items"]
        if isinstance(data, list):
            return data
        # if it’s a dict without items, wrap it
        return [data]
