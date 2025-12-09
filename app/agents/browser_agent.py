# app/agents/browseruse_agent.py
from typing import List, Any
import json, os, re
from loguru import logger
from browser_use import Agent, ChatGoogle
from dotenv import load_dotenv

from ..utils.models import DealItem, UserQuery

load_dotenv()

SCHEMA_HINT = """
Return ONLY raw JSON. Shape:
{"deals":[
  {"store":"Target","store_domain":"target.com","product_name":"Bananas 1 lb",
   "brand":"Target","size":"1 lb","category":"produce","price":0.59,"list_price":0.79,
   "currency":"USD","discount_abs":0.20,"discount_pct":0.253,"deal_type":"SALE",
   "start_date":"2025-11-19","end_date":"2025-11-26","terms":"limit 2","product_url":"https://..."}
]}
- Focus on *deals* (sale/BOGO/club/was-price). If a field is unknown, omit it.
- Do not add markdown or text outside the JSON.
"""

def _to_text(result: Any) -> str:
    # 1) explicit
    val = getattr(result, "final_result", None)
    if isinstance(val, str) and val.strip():
        return val
    # 2) text may be str or callable
    val = getattr(result, "text", None)
    if callable(val):
        try:
            s = val()
            if isinstance(s, str) and s.strip():
                return s
        except Exception:
            pass
    elif isinstance(val, str) and val.strip():
        return val
    # 3) content fallback
    val = getattr(result, "content", None)
    if isinstance(val, str) and val.strip():
        return val
    # 4) stringify
    try:
        s = str(result)
        if s.strip():
            return s
    except Exception:
        pass
    return ""

def _strip_md(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.strip("`")
        nl = t.find("\n")
        if nl != -1:
            t = t[nl+1:].strip()
    return t

def _extract_json(text: str) -> dict:
    """
    Be forgiving:
    - allow top-level array
    - try to locate the largest JSON array if extra prose is present
    """
    t = _strip_md(text).strip()

    # direct parse
    try:
        obj = json.loads(t)
        if isinstance(obj, list):
            return {"deals": obj}
        if isinstance(obj, dict):
            if "deals" in obj:
                return obj
            # looks like one deal? wrap it.
            if all(k in obj for k in ("product_name", "price", "store")):
                return {"deals": [obj]}
    except Exception:
        pass

    # pull largest JSON array
    m = re.search(r"\[[\s\S]*\]", t)
    if m:
        try:
            arr = json.loads(m.group(0))
            if isinstance(arr, list):
                return {"deals": arr}
        except Exception:
            pass

    return {"deals": []}

class BrowserUseDealsAgent:
    def __init__(self, model: str = "gemini-flash-latest"):
        self.llm = ChatGoogle(model=model)

    async def run(self, q: UserQuery) -> List[DealItem]:
        city = q.city or os.getenv("DEFAULT_CITY", "Phoenix")
        state = q.state or os.getenv("DEFAULT_STATE", "AZ")
        zip_code = os.getenv("DEFAULT_ZIP", "85004")  # helps Target/Walmart localize

        # Target-specific instruction first for a reliable first run
        task = (
            "Open target.com, set the location/ZIP if prompted (ZIP {zip}). "
            "Search for fruits and produce deals (apples, bananas, berries, citrus, grapes, etc.). "
            "Scrape *deal-labeled* products (sale price or was-price/bogo/club price). "
            "For each item, capture product name, price, list/was-price when visible, deal badge type, and product URL. "
            "Limit to the first 30 clear matches. "
            f"{SCHEMA_HINT}"
        ).format(zip=zip_code)

        # If the user asked for something specific, append it
        if q.message:
            task += f"\nUser emphasis: {q.message}"

        agent = Agent(task=task, llm=self.llm)

        try:
            result = await agent.run()
            text = _to_text(result)
        except Exception as e:
            logger.exception(f"browser_use failed: {e}")
            return []

        if not text:
            logger.warning("browser_use returned empty result text.")
            return []

        logger.debug("RAW AGENT OUTPUT (first 1500 chars):\n" + text[:1500])

        data = _extract_json(text)
        raw_deals = data.get("deals", [])
        if not isinstance(raw_deals, list):
            raw_deals = []

        out: List[DealItem] = []
        for d in raw_deals:
            # light coercion for numbers emitted as strings
            for k in ("price", "list_price", "discount_abs", "discount_pct"):
                if k in d and isinstance(d[k], str):
                    s = d[k].replace("$", "").strip()
                    try:
                        d[k] = float(s)
                    except Exception:
                        pass
            # ensure required minimal fields
            d.setdefault("store", "Target")
            d.setdefault("store_domain", "target.com")
            try:
                out.append(DealItem(**d))
            except Exception:
                logger.warning(f"Skipping malformed row: {d}")
        return out
# app/agents/browser_agent.py
from typing import List
from ..utils.models import ScrapeTask, DealItem

class BrowserAgent:
    """No-op stub since we now ingest via browser_use."""
    async def run_tasks(self, tasks: List[ScrapeTask]) -> List[DealItem]:
        return []
