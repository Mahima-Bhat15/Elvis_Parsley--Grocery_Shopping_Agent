# app/agents/browseruse_agent.py
from __future__ import annotations

import asyncio, json, os, re
from typing import Any, List, Optional
from dotenv import load_dotenv
from loguru import logger
# simple global throttle for browser-use agent calls
_MAX_CONCURRENT = int(os.getenv("SCRAPE_CONCURRENCY", "1"))  # 1 = run serially
_SCRAPE_SEM = asyncio.Semaphore(_MAX_CONCURRENT)
_SCRAPE_COOLDOWN_SEC = float(os.getenv("SCRAPE_COOLDOWN_SEC", "0.0"))



# Import all supported providers; Cohere is new here
from browser_use import Agent, ChatGoogle, ChatOpenAI
try:
    from browser_use import ChatCohere  # available in recent browser-use
except ImportError:
    ChatCohere = None

from ..utils.models import DealItem, UserQuery

load_dotenv()

def make_llm():
    prov = (os.getenv("BROWSERUSE_LLM_PROVIDER", "openai") or "openai").lower()
    model = os.getenv("BROWSERUSE_LLM_MODEL", "")
    if prov == "google":
        return ChatGoogle(model=model or "gemini-2.5-flash")
    elif prov == "openai":
        return ChatOpenAI(model=model or "gpt-4o-mini")
    else:
        raise RuntimeError(
            f"Unsupported BROWSERUSE_LLM_PROVIDER='{prov}'. Use 'openai' or 'google'."
        )





# ---- Prompt / schema ---------------------------------------------------------

SCHEMA_HINT = """
Return ONLY raw JSON:
{"items":[
  {"store":"Target","store_domain":"target.com",
   "product_name":"Romaine Hearts 3ct","brand":"Good & Gather","size":"3 ct","category":"vegetable",
   "price":2.49,"list_price":2.99,"currency":"USD",
   "is_deal": true, "deal_type":"SALE", "discount_abs":0.50, "discount_pct":0.167,
   "product_url":"https://...", "image_url":"https://..."}
]}
Rules:
- Always return current price even if there is NO deal (set is_deal=false).
- You MUST include product_url. If the list page only has relative links, convert them to absolute (e.g., "https://{store_domain}{path}"). If no product link is visible, open the product tile to get it. If still not possible, DO NOT include the item.
- Include image_url if visible; if not visible, still return the item as long as product_url is present.
- Strictly keep to the requested category focus (e.g., "avocado"): exclude non-matching items (no peaches if user asked for avocado).
- No prose/markdown outside JSON. JSON must be parseable.
"""


SITE_TASKS = {
    "walmart.com": (
        "Open walmart.com, set ZIP to {zip}, then search for: {query}. "
        "Extract items with current price, list price (if shown), deal badge/type, product_url, image_url."
    ),
    "target.com": (
        "Open target.com, set your store/ZIP to {zip}, then search for: {query}. "
        "Prefer pickup/in-stock items. Extract same fields."
    ),
    "instacart.com": (
        "Open instacart.com, set delivery ZIP to {zip}, then search for: {query}. "
        "Prefer stable product pages if possible. Extract same fields."
    ),
}

# ---- Helpers ----------------------------------------------------------------


def _to_text(result: Any) -> str:
    """Extract usable text from Browser Use result object."""
    for attr in ("final_result", "text", "content"):
        val = getattr(result, attr, None)
        if callable(val):
            try:
                val = val()
            except Exception:
                val = None
        if isinstance(val, str) and val.strip():
            return val
    try:
        s = str(result)
        return s if s.strip() else ""
    except Exception:
        return ""


def _strip_md(text: str) -> str:
    """Remove ``` fences and language hints; return just the body."""
    t = text.strip()
    if t.startswith("```"):
        # remove opening fence
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        # remove closing fence
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def _json_from_text(text: str) -> Optional[dict]:
    """
    Try to parse a dict from agent text. If strict parse fails, try to
    snip the first {..."items":[...]} block.
    """
    raw = _strip_md(text)
    # strict attempt
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    # fallback: find a top-level object that contains "items":[...]
    m = re.search(r"\{[\s\S]*\"items\"\s*:\s*\[[\s\S]*?\}\s*\]", raw)
    if m:
        try:
            data = json.loads(m.group(0))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return None


def _coerce_numbers(d: dict, keys: tuple[str, ...] = ("price", "list_price", "discount_abs", "discount_pct")) -> None:
    """Convert '3.99'/'$3.99' -> 3.99 floats in-place where possible."""
    for k in keys:
        v = d.get(k)
        if isinstance(v, str):
            s = v.replace("$", "").replace(",", "").strip()
            try:
                d[k] = float(s)
            except Exception:
                # leave as-is if it won't coerce
                pass


def _normalize_rows(
    data: dict, *, store_label: str, domain: str, category_hint: Optional[str], limit: int
) -> List[DealItem]:
    rows = data.get("items") or data.get("deals") or data.get("results") or []
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list):
        rows = []

    out: List[DealItem] = []
    for d in rows[:limit]:
        d.setdefault("store", store_label)
        d.setdefault("store_domain", domain)
        if category_hint and not d.get("category"):
            d["category"] = category_hint

        # normalize absolute product_url
        pu = (d.get("product_url") or "").strip()
        if pu and pu.startswith("/"):
            pu = f"https://{domain}{pu}"
            d["product_url"] = pu
        elif pu and pu.startswith("www."):
            pu = f"https://{pu}"
            d["product_url"] = pu

        # coerce numerics
        _coerce_numbers(d)

        # heuristics: skip clearly irrelevant rows if we have a category hint
        if category_hint:
            name_l = (d.get("product_name") or "").lower()
            cat_l  = (d.get("category") or "").lower()
            if category_hint.lower() not in name_l and category_hint.lower() not in cat_l:
                # allow through if it's on sale AND looks like a close synonym of category
                synonyms = {"avocado": ["avocado", "hass"], "tomato": ["tomato", "roma", "cherry"]}
                allow = any(any(tok in name_l for tok in synonyms.get(category_hint.lower(), [])))
                if not allow:
                    continue

        # hard requirement: we need a product_url to be usable in UI
        if not d.get("product_url"):
            continue

        if d.get("is_deal") is None:
            d["is_deal"] = bool(d.get("discount_abs") or d.get("discount_pct") or d.get("deal_type"))

        try:
            out.append(DealItem(**d))
        except Exception as ex:
            logger.warning(f"Skipping malformed row from {domain}: {d} ({ex})")

    return out



# ---- Agent ------------------------------------------------------------------


class BrowserUseDealsAgent:
    """
    A thin wrapper around Browser Use that:
    - sends proper inputs to .run()
    - extracts/cleans agent output to strict JSON
    - returns normalized DealItem rows
    """

    def __init__(self, model: Optional[str] = None):
        self.llm = make_llm()
        self._sem = asyncio.Semaphore(int(os.getenv("BROWSERUSE_MAX_CONCURRENCY", "1")))
        self._pace_ms = int(os.getenv("BROWSERUSE_PACE_MS", "800"))

        

    # One-store live scrape (used by /best_cards_live)
    async def run_live(
        self,
        *,
        store_domain: str,
        category_hint: Optional[str],
        max_price: Optional[float],
        query_terms: str,
        limit: int = 12,
    ) -> List[DealItem]:
        store_label = (
            "Target" if "target.com" in store_domain
            else "Walmart" if "walmart.com" in store_domain
            else store_domain
        )

        price_clause = f"Focus on items priced at or under ${max_price:.2f}. " if max_price is not None else "Include well-priced items. "
        task = (
            f"Go to {store_domain} and search for grocery items specifically for: '{query_terms}'. "  # head term like 'milk'
            f"Category focus: {category_hint or 'grocery'}. "
            f"{price_clause}"
            f"Return up to {limit} items as JSON per the schema. "
            f"{SCHEMA_HINT}"
        )


        agent = Agent(task=task, llm=self.llm)
        try:
            async with _SCRAPE_SEM:
                result = await agent.run()
                if _SCRAPE_COOLDOWN_SEC:
                    await asyncio.sleep(_SCRAPE_COOLDOWN_SEC)
        except Exception as e:
            logger.exception(f"browser_use run_live crashed for {store_domain}: {e}")
            return []


        text = _to_text(result)
        if not text or text.startswith("AgentHistoryList"):
            logger.warning(f"{store_domain}: agent returned no parseable text.")
            return []

        data = _json_from_text(text)
        if not data:
            logger.warning(f"{store_domain}: could not parse JSON.\nRAW START\n{text[:1500]}\nRAW END")
            return []

        return _normalize_rows(
            data,
            store_label=store_label,
            domain=store_domain,
            category_hint=category_hint,
            limit=limit,
        )

    # Multi-store convenience (used by /ingest or ad-hoc refresh)
    async def _run_one(self, domain: str, q: UserQuery, *, default_zip: str = "85001") -> List[DealItem]:
        zip_code = q.city or os.getenv("DEFAULT_ZIP", default_zip)
        tpl = SITE_TASKS.get(domain)
        if not tpl:
            logger.warning(f"No SITE_TASKS template for {domain}")
            return []

        task = (
            f"{tpl.format(zip=zip_code, query=q.message)} "
            f"Return 10–30 rows if available. {SCHEMA_HINT}"
        )

        agent = Agent(task=task, llm=self.llm)
        try:
            async with _SCRAPE_SEM:
                result = await agent.run()
                if _SCRAPE_COOLDOWN_SEC:
                    await asyncio.sleep(_SCRAPE_COOLDOWN_SEC)
        except Exception as e:
            logger.exception(f"{domain} scrape error: {e}")
            return []

        text = _to_text(result)
        if not text or text.startswith("AgentHistoryList"):
            logger.warning(f"{domain}: agent returned no parseable text.")
            return []

        data = _json_from_text(text)
        if not data:
            logger.warning(f"{domain}: could not parse JSON.\nRAW START\n{text[:1500]}\nRAW END")
            return []

        store_label = domain.split(".")[0].title()
        return _normalize_rows(
            data,
            store_label=store_label,
            domain=domain,
            category_hint=None,
            limit=30,
        )

    async def run_multi(self, q: UserQuery, domains: List[str]) -> List[DealItem]:
        """Scrape several sites concurrently and merge results."""
        tasks = [self._run_one(d, q) for d in domains]
        chunks = await asyncio.gather(*tasks, return_exceptions=True)
        out: List[DealItem] = []
        for ch in chunks:
            if isinstance(ch, Exception):
                logger.exception(ch)
                continue
            out.extend(ch)
        return out
