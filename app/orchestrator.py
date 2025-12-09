# # app/orchestrator.py
# from __future__ import annotations

# import asyncio
# from asyncio import Semaphore
# from typing import Any, List, Optional
# from loguru import logger

# from .utils.models import (
#     UserQuery,
#     OrchestratorResult,
#     IngestRequest,
#     IngestResult,
# )
# from .agents.kg_agent import KGAgent
#     # ^ contains the queries we just updated
# from .agents.answer_agent import AnswerAgent
# from .agents.browseruse_agent import BrowserUseDealsAgent
# from .agents.intent_agent import parse_query
# from .utils.images import resolve_images

# SCRAPE_SEMAPHORE = Semaphore(1)


# def _intent_get(obj: Any, key: str, default=None):
#     if isinstance(obj, dict):
#         return obj.get(key, default)
#     return getattr(obj, key, default)


# def _abs_url(url: Optional[str], store_domain: Optional[str]) -> Optional[str]:
#     if not url:
#         return url
#     if url.startswith("http://") or url.startswith("https://"):
#         return url
#     if url.startswith("/") and store_domain:
#         return f"https://{store_domain}{url}"
#     return url


# class Orchestrator:
#     def __init__(self) -> None:
#         self.browseruse = BrowserUseDealsAgent()
#         self.kg = KGAgent()
#         self.answer = AnswerAgent()

#     # ----------------------------- Chat (semantic → KG only) -----------------------------

#     async def handle(self, q: UserQuery) -> OrchestratorResult:
#         intent = parse_query(q.message)

#         needle = _intent_get(intent, "product_terms") or q.message
#         if not isinstance(needle, str):
#             needle = " ".join(needle or [])

#         rows = self.kg.search_best_filtered(
#             q=needle,
#             stores=_intent_get(intent, "stores") or None,
#             categories=_intent_get(intent, "categories") or None,
#             max_price=_intent_get(intent, "max_price"),
#             deal_only=_intent_get(intent, "deal_only", False),
#             limit=24,
#         )

#         msg = (
#             self.answer.craft_best_price(q.message, rows)
#             if hasattr(self.answer, "craft_best_price")
#             else self.answer.craft(q.message, rows)
#         )
#         return OrchestratorResult(deals=rows, answer=msg)

#     # ----------------------------- Ingestion (live scrape) -----------------------------

#     async def ingest_via_browseruse(self, req: IngestRequest) -> IngestResult:
#         pseudo = UserQuery(
#             message=req.message,
#             max_price=req.max_price,
#             categories=req.categories or [],
#             city=req.city,
#             state=req.state,
#         )

#         try:
#             if hasattr(self.browseruse, "run_multi"):
#                 items = await self.browseruse.run_multi(
#                     pseudo, ["walmart.com", "target.com", "instacart.com"]
#                 )
#             else:
#                 items = await self.browseruse.run(pseudo)
#         except Exception as e:
#             logger.exception(f"BrowserUse ingestion failed: {e}")
#             items = []

#         if items:
#             try:
#                 self.kg.upsert_offers(items)
#             except Exception as e:
#                 logger.exception(f"KG upsert failed: {e}")

#         sample = [i.model_dump() for i in items[:5]] if items else []
#         return IngestResult(ingested=len(items), sample=sample)

#     # ----------------------------- Cards from KG (+ image resolver) -----------------------------

#     async def best_with_images(
#         self, q: UserQuery, stores: Optional[List[str]] = None, limit: int = 4
#     ) -> List[dict]:
#         rows = self.kg.search_best_deals_products(
#             q.message, limit=limit, stores=stores or None
#         )

#         # prefer any image already on offers; collect missing for resolver
#         idx_to_url: dict[int, str] = {}
#         for i, r in enumerate(rows):
#             if r.get("image_url"):
#                 continue
#             candidate = None
#             for off in r.get("offers") or []:
#                 if off.get("image_url"):
#                     r["image_url"] = off["image_url"]
#                     break
#                 if not candidate and off.get("product_url"):
#                     candidate = _abs_url(off.get("product_url") or "", off.get("store_domain"))
#             if not r.get("image_url") and candidate:
#                 idx_to_url[i] = candidate

#         if idx_to_url:
#             try:
#                 pending = sorted(idx_to_url.items())
#                 payload = [{"product_url": url} for (_i, url) in pending]
#                 resolved = await resolve_images(payload)
#                 for (i, _url), rdict in zip(pending, resolved):
#                     img = (rdict or {}).get("image_url")
#                     if img and not rows[i].get("image_url"):
#                         rows[i]["image_url"] = img
#             except Exception as e:
#                 logger.exception(f"resolve_images failed: {e}")

#         # persist on Product for speed
#         for r in rows:
#             img = r.get("image_url")
#             offers = r.get("offers") or []
#             if img and offers:
#                 dom = offers[0].get("store_domain")
#                 if dom:
#                     pid = f"{dom}::{r['product_name'].lower()}"
#                     try:
#                         self.kg.set_product_image(pid, img)
#                     except Exception:
#                         pass

#         return rows

#     # ----------------------------- Live cards -----------------------------

#     async def best_cards_live(self, q: UserQuery, limit: int = 6) -> List[dict]:
#         intent = parse_query(q.message)

#         # stores = _intent_get(intent, "stores") or ["target.com"]
#         # categories = _intent_get(intent, "categories") or ["vegetable"]
#         stores = _intent_get(intent, "stores") or ["target.com","walmart.com"]
#         categories = _intent_get(intent, "categories") or None
#         max_price = _intent_get(intent, "max_price")
#         product_terms = _intent_get(intent, "product_terms") or q.message
#         if not isinstance(product_terms, str):
#             product_terms = " ".join(product_terms or [])
#         category_hint = None
#         pt = _intent_get(intent, "product_terms") or []
#         if isinstance(pt, list) and pt:
#             category_hint = pt[0]


#         items_all = []
#         for sd in stores:
#             async with SCRAPE_SEMAPHORE:
#                 try:
#                     scraped = await self.browseruse.run_live(
#                                 store_domain=sd,
#                                 category_hint=category_hint,
#                                 max_price=max_price,
#                                 query_terms=" ".join(pt) if isinstance(pt, list) else (pt or ""),
#                                 limit=12,
#                             )
#                     if scraped:
#                         items_all.extend(scraped)
#                 except Exception as e:
#                     logger.exception(f"Live scrape failed for {sd}: {e}")
#                 await asyncio.sleep(20)

#         if items_all:
#             try:
#                 self.kg.upsert_offers(items_all)
#             except Exception as e:
#                 logger.exception(f"KG upsert failed: {e}")

#         try:
#             rows = self.kg.search_best_filtered(
#                 q="",
#                 stores=stores,
#                 categories=categories,
#                 max_price=max_price,
#                 deal_only=_intent_get(intent, "deal_only", False),
#                 limit=limit,
#             )
#         except Exception as e:
#             logger.exception(f"KG filtered search failed: {e}")
#             rows = []

#         # images: offer.image_url → resolver(product_url) → placeholder
#         idx_to_url: dict[int, str] = {}
#         for i, r in enumerate(rows):
#             if r.get("image_url"):
#                 continue
#             candidate = None
#             for off in r.get("offers") or []:
#                 if off.get("image_url"):
#                     r["image_url"] = off["image_url"]
#                     break
#                 if not candidate and off.get("product_url"):
#                     candidate = _abs_url(off.get("product_url") or "", off.get("store_domain"))
#             if not r.get("image_url") and candidate:
#                 idx_to_url[i] = candidate

#         if idx_to_url:
#             try:
#                 pending = sorted(idx_to_url.items())
#                 payload = [{"product_url": url} for (_i, url) in pending]
#                 resolved = await resolve_images(payload)
#                 for (i, _url), rdict in zip(pending, resolved):
#                     img = (rdict or {}).get("image_url")
#                     if img and not rows[i].get("image_url"):
#                         rows[i]["image_url"] = img
#             except Exception as e:
#                 logger.exception(f"resolve_images failed: {e}")

#         for r in rows:
#             img = r.get("image_url")
#             offers = r.get("offers") or []
#             if img and offers:
#                 dom = offers[0].get("store_domain")
#                 if dom:
#                     pid = f"{dom}::{r['product_name'].lower()}"
#                     try:
#                         self.kg.set_product_image(pid, img)
#                     except Exception:
#                         pass

#         return rows
# Integrated Orchestrator with image-resolution block merged into best_with_images
# NOTE: This is a cleaned and fully-integrated version based on your provided diff.
# You can now edit or adjust inside this canvas.

# from __future__ import annotations
# import asyncio
# from asyncio import Semaphore
# from typing import List, Optional, Any, Dict
# from loguru import logger

# SCRAPE_SEMAPHORE = Semaphore(1)

# from .utils.models import (
#     UserQuery,
#     OrchestratorResult,
#     IngestRequest,
#     IngestResult,
# )
# from .agents.kg_agent import KGAgent
# from .agents.answer_agent import AnswerAgent
# from .agents.browseruse_agent import BrowserUseDealsAgent
# from .agents.intent_agent import parse_query, ParsedIntent
# from .utils.images import resolve_images


# def _intent_get(obj: Any, key: str, default=None):
#     if isinstance(obj, dict):
#         return obj.get(key, default)
#     return getattr(obj, key, default)


# def _interleave_by_store(rows: List[dict], max_total: int) -> List[dict]:
#     buckets: Dict[str, List[dict]] = {}
#     for r in rows:
#         dom = None
#         if r.get("offers"):
#             dom = r["offers"][0].get("store_domain")
#         dom = dom or "unknown"
#         buckets.setdefault(dom, []).append(r)

#     order = []
#     while len(order) < max_total and any(buckets.values()):
#         for dom in list(buckets.keys()):
#             if buckets[dom]:
#                 order.append(buckets[dom].pop(0))
#             if len(order) >= max_total:
#                 break
#         for d in list(buckets.keys()):
#             if not buckets[d]:
#                 buckets.pop(d, None)
#     return order[:max_total]


# def _pass_semantic(row: dict, intent: ParsedIntent) -> bool:
#     name = (row.get("product_name") or "").lower()
#     brand = (row.get("brand") or "").lower()
#     cat = (row.get("category") or "").lower()
#     blob = " ".join([name, brand, cat])

#     for inc in intent.must_include:
#         if inc not in blob:
#             return False
#     if intent.require_organic and "organic" not in blob:
#         return False
#     for exc in intent.must_exclude:
#         if exc in blob:
#             return False
#     return True


# def _absolute_url(u: Optional[str], dom: Optional[str]) -> Optional[str]:
#     if not u:
#         return None
#     u = u.strip()
#     if u.startswith("http://") or u.startswith("https://"):
#         return u
#     if u.startswith("//"):
#         return f"https:{u}"
#     if u.startswith("/"):
#         return f"https://{dom}{u}" if dom else None
#     if "." in u and " " not in u:
#         return f"https://{u}"
#     return None


# class Orchestrator:
#     def __init__(self) -> None:
#         self.browseruse = BrowserUseDealsAgent()
#         self.kg = KGAgent()
#         self.answer = AnswerAgent()

#     # ----------------------------------------------------------------------
#     # Chat handler
#     # ----------------------------------------------------------------------
#     async def handle(self, q: UserQuery) -> OrchestratorResult:
#         intent = parse_query(q.message)
#         stores = intent.stores or ["target.com", "walmart.com"]

#         needle_terms = intent.must_include or []
#         needle = " ".join(needle_terms)

#         rows = self.kg.search_best_filtered(
#             q=needle,
#             stores=stores,
#             categories=intent.categories or None,
#             max_price=intent.max_price,
#             deal_only=intent.deal_only,
#             limit=64,
#         )

#         rows = [r for r in rows if _pass_semantic(r, intent)]

#         for r in rows:
#             for off in r.get("offers") or []:
#                 off["product_url"] = _absolute_url(off.get("product_url"), off.get("store_domain"))

#         rows = _interleave_by_store(rows, 24)

#         msg = (
#             self.answer.craft_best_price(q.message, rows)
#             if hasattr(self.answer, "craft_best_price")
#             else self.answer.craft(q.message, rows)
#         )
#         return OrchestratorResult(deals=rows, answer=msg)

#     # ----------------------------------------------------------------------
#     # Ingestion
#     # ----------------------------------------------------------------------
#     async def ingest_via_browseruse(self, req: IngestRequest) -> IngestResult:
#         pseudo = UserQuery(
#             message=req.message,
#             max_price=req.max_price,
#             categories=req.categories or [],
#             city=req.city,
#             state=req.state,
#         )

#         try:
#             if hasattr(self.browseruse, "run_multi"):
#                 items = await self.browseruse.run_multi(
#                     pseudo, ["walmart.com", "target.com", "instacart.com"]
#                 )
#             else:
#                 items = await self.browseruse.run(pseudo)
#         except Exception as e:
#             logger.exception(f"BrowserUse ingestion failed: {e}")
#             items = []

#         if items:
#             try:
#                 self.kg.upsert_offers(items)
#             except Exception as e:
#                 logger.exception(f"KG upsert failed: {e}")

#         sample = [i.model_dump() for i in items[:5]] if items else []
#         return IngestResult(ingested=len(items), sample=sample)

#     # ----------------------------------------------------------------------
#     # best_with_images — your requested integration here
#     # ----------------------------------------------------------------------
#     async def best_with_images(
#         self, q: UserQuery, stores: Optional[List[str]] = None, limit: int = 4
#     ) -> List[dict]:

#         rows = self.kg.search_best_deals_products(
#             q.message, limit=limit, stores=stores or None
#         )

#         # ====== INTEGRATED IMAGE RESOLUTION BLOCK (your snippet) ======
#         pending = []
#         for i, r in enumerate(rows):
#             if r.get("image_url"):
#                 continue
#             url = None
#             for off in r.get("offers") or []:
#                 if off.get("image_url"):
#                     r["image_url"] = off.get("image_url")
#                     break
#                 if not url and off.get("product_url"):
#                     url = off.get("product_url")
#             if not r.get("image_url") and url:
#                 pending.append((i, url))

#         if pending:
#             try:
#                 payload = [{"product_url": u} for (_i, u) in pending]
#                 resolved = await resolve_images(payload)
#                 for (i, _u), rd in zip(pending, resolved):
#                     img = (rd or {}).get("image_url")
#                     if img and not rows[i].get("image_url"):
#                         rows[i]["image_url"] = img
#             except Exception as e:
#                 logger.exception(f"resolve_images failed: {e}")

#         # Persist
#         for r in rows:
#             img = r.get("image_url")
#             offers = r.get("offers") or []
#             if img and offers:
#                 dom = offers[0].get("store_domain")
#                 if dom:
#                     pid = f"{dom}::{r['product_name'].lower()}"
#                     try:
#                         self.kg.set_product_image(pid, img)
#                     except Exception:
#                         pass
#         # ====== END OF INTEGRATION ======

#         return rows

#     # ----------------------------------------------------------------------
#     # Live cards
#     # ----------------------------------------------------------------------
#     async def best_cards_live(self, q: UserQuery, limit: int = 6) -> List[dict]:
#         intent = parse_query(q.message)
#         stores = _intent_get(intent, "stores") or ["target.com", "walmart.com"]
#         categories = _intent_get(intent, "categories") or []
#         max_price = _intent_get(intent, "max_price")
#         product_terms = _intent_get(intent, "product_terms") or q.message
#         if not isinstance(product_terms, str):
#             product_terms = " ".join(product_terms or [])

#         items_all = []
#         for sd in stores:
#             async with SCRAPE_SEMAPHORE:
#                 try:
#                     scraped = await self.browseruse.run_live(
#                         store_domain=sd,
#                         category_hint=(categories[0] if categories else None),
#                         max_price=max_price,
#                         query_terms=product_terms,
#                         limit=12,
#                     )
#                     if scraped:
#                         items_all.extend(scraped)
#                 except Exception as e:
#                     logger.exception(f"Live scrape failed for {sd}: {e}")
#                 await asyncio.sleep(2)

#         if items_all:
#             try:
#                 self.kg.upsert_offers(items_all)
#             except Exception as e:
#                 logger.exception(f"KG upsert failed: {e}")

#         try:
#             rows = self.kg.search_best_filtered(
#                 q="",
#                 stores=stores,
#                 categories=categories or None,
#                 max_price=max_price,
#                 deal_only=False,
#                 limit=limit,
#             )
#         except Exception as e:
#             logger.exception(f"KG filtered search failed: {e}")
#             rows = []

#         # Image resolution logic remains the same as earlier
#         idx_to_url: Dict[int, str] = {}
#         for i, r in enumerate(rows):
#             if r.get("image_url"):
#                 continue
#             candidate = None
#             for off in r.get("offers") or []:
#                 if off.get("image_url"):
#                     r["image_url"] = off["image_url"]
#                     break
#                 if not candidate and off.get("product_url"):
#                     candidate = _absolute_url(off.get("product_url"), off.get("store_domain"))
#             if not r.get("image_url") and candidate:
#                 idx_to_url[i] = candidate

#         if idx_to_url:
#             try:
#                 pending = sorted(idx_to_url.items())
#                 payload = [{"product_url": url} for (_i, url) in pending]
#                 resolved = await resolve_images(payload)
#                 for (i, _url), rdict in zip(pending, resolved):
#                     img = (rdict or {}).get("image_url")
#                     if img and not rows[i].get("image_url"):
#                         rows[i]["image_url"] = img
#             except Exception as e:
#                 logger.exception(f"resolve_images failed: {e}")

#         for r in rows:
#             img = r.get("image_url")
#             offers = r.get("offers") or []
#             if img and offers:
#                 dom = offers[0].get("store_domain")
#                 if dom:
#                     pid = f"{dom}::{r['product_name'].lower()}"
#                     try:
#                         self.kg.set_product_image(pid, img)
#                     except Exception:
#                         pass

#         return rows

# app/orchestrator.py
from __future__ import annotations
import asyncio
from asyncio import Semaphore
from typing import List, Optional, Any, Dict
from loguru import logger

SCRAPE_SEMAPHORE = Semaphore(1)

from .utils.models import (
    UserQuery,
    OrchestratorResult,
    IngestRequest,
    IngestResult,
)
from .agents.kg_agent import KGAgent
from .agents.answer_agent import AnswerAgent
from .agents.browseruse_agent import BrowserUseDealsAgent
from .agents.intent_agent import parse_query, ParsedIntent
from .utils.images import resolve_images


def _intent_get(obj: Any, key: str, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _interleave_by_store(rows: List[dict], max_total: int) -> List[dict]:
    """Round-robin by store_domain to show variety."""
    buckets: Dict[str, List[dict]] = {}
    for r in rows:
        dom = None
        if r.get("offers"):
            dom = r["offers"][0].get("store_domain")
        dom = dom or "unknown"
        buckets.setdefault(dom, []).append(r)

    order = []
    while len(order) < max_total and any(buckets.values()):
        for dom in list(buckets.keys()):
            if buckets[dom]:
                order.append(buckets[dom].pop(0))
            if len(order) >= max_total:
                break
        # drop empty buckets
        for d in list(buckets.keys()):
            if not buckets[d]:
                buckets.pop(d, None)
    return order[:max_total]


def _pass_semantic(row: dict, intent: ParsedIntent) -> bool:
    """Apply include/exclude + organic hard checks to a KG row."""
    name = (row.get("product_name") or "").lower()
    brand = (row.get("brand") or "").lower()
    cat = (row.get("category") or "").lower()

    blob = " ".join([name, brand, cat])

    # must include (if specified)
    for inc in intent.must_include:
        if inc not in blob:
            return False

    # organic
    if intent.require_organic and "organic" not in blob:
        return False

    # excludes
    for exc in intent.must_exclude:
        if exc in blob:
            return False

    return True


def _absolute_url(u: Optional[str], dom: Optional[str]) -> Optional[str]:
    if not u:
        return None
    u = u.strip()
    if u.startswith("http://") or u.startswith("https://"):
        return u
    if u.startswith("//"):
        return f"https:{u}"
    if u.startswith("/"):
        return f"https://{dom}{u}" if dom else None
    # "www.domain.com/..." case
    if "." in u and " " not in u:
        return f"https://{u}"
    return None


class Orchestrator:
    def __init__(self) -> None:
        self.browseruse = BrowserUseDealsAgent()
        self.kg = KGAgent()
        self.answer = AnswerAgent()

    # ----------------------------- Chat (semantic → KG only) -----------------------------

    async def handle(self, q: UserQuery) -> OrchestratorResult:
        intent = parse_query(q.message)

        # Default to both stores if user didn’t specify
        stores = intent.stores or ["target.com", "walmart.com"]

        # Compose a small "needle" from head terms to keep KG text-match tight
        needle_terms = intent.must_include or []
        needle = " ".join(needle_terms)

        rows = self.kg.search_best_filtered(
            q=needle,
            stores=stores,
            categories=intent.categories or None,
            max_price=intent.max_price,
            deal_only=intent.deal_only,
            limit=64,  # take a larger pool, we’ll filter/diversify
        )

        # Semantic hard checks (include/exclude, organic)
        rows = [r for r in rows if _pass_semantic(r, intent)]

        # Fix URLs (avoid localhost 404s)
        for r in rows:
            for off in r.get("offers") or []:
                off["product_url"] = _absolute_url(off.get("product_url"), off.get("store_domain"))

        # Diversity by store then cap at 24
        rows = _interleave_by_store(rows, 24)

        msg = (
            self.answer.craft_best_price(q.message, rows)
            if hasattr(self.answer, "craft_best_price")
            else self.answer.craft(q.message, rows)
        )
        return OrchestratorResult(deals=rows, answer=msg)

    # ----------------------------- Ingestion (live scrape) -----------------------------

    async def ingest_via_browseruse(self, req: IngestRequest) -> IngestResult:
        pseudo = UserQuery(
            message=req.message,
            max_price=req.max_price,
            categories=req.categories or [],
            city=req.city,
            state=req.state,
        )

        try:
            if hasattr(self.browseruse, "run_multi"):
                items = await self.browseruse.run_multi(
                    pseudo, ["walmart.com", "target.com", "instacart.com"]
                )
            else:
                items = await self.browseruse.run(pseudo)
        except Exception as e:
            logger.exception(f"BrowserUse ingestion failed: {e}")
            items = []

        if items:
            try:
                self.kg.upsert_offers(items)
            except Exception as e:
                logger.exception(f"KG upsert failed: {e}")

        sample = [i.model_dump() for i in items[:5]] if items else []
        return IngestResult(ingested=len(items), sample=sample)

    # ----------------------------- Live cards (intent → scrape → KG → images) -----------------------------

    async def best_cards_live(self, q: UserQuery, limit: int = 6) -> List[dict]:
        intent = parse_query(q.message)

        # 1) Which stores?
        stores = intent.stores or ["target.com", "walmart.com"]

        # 2) Live scrape (optional best-effort)
        items_all = []
        for sd in stores:
            async with SCRAPE_SEMAPHORE:
                try:
                    scraped = await self.browseruse.run_live(
                        store_domain=sd,
                        category_hint=(intent.categories[0] if intent.categories else None),
                        max_price=intent.max_price,
                        query_terms=" ".join(intent.must_include or []) or q.message,
                        limit=12,
                    )
                    if scraped:
                        items_all.extend(scraped)
                except Exception as e:
                    logger.exception(f"Live scrape failed for {sd}: {e}")
                await asyncio.sleep(8)  # brief pause to be gentle

        # 3) Upsert into KG so subsequent queries benefit
        if items_all:
            try:
                self.kg.upsert_offers(items_all)
            except Exception as e:
                logger.exception(f"KG upsert failed: {e}")

        # 4) Query KG using semantic needle
        needle = " ".join(intent.must_include or [])
        try:
            rows = self.kg.search_best_filtered(
                q=needle,
                stores=stores,
                categories=intent.categories or None,
                max_price=intent.max_price,
                deal_only=intent.deal_only,
                limit=64,  # gather pool
            )
        except Exception as e:
            logger.exception(f"KG filtered search failed: {e}")
            rows = []

        # 5) Semantic hard checks (include/exclude + organic)
        rows = [r for r in rows if _pass_semantic(r, intent)]

        # 6) Ensure URLs are absolute (avoid localhost 404)
        for r in rows:
            for off in r.get("offers") or []:
                off["product_url"] = _absolute_url(off.get("product_url"), off.get("store_domain"))

        # 7) Image resolution (existing image → resolver → placeholder handled on FE)
        idx_to_url = {}
        for i, r in enumerate(rows):
            if r.get("image_url"):
                continue
            candidate = None
            for off in r.get("offers") or []:
                if off.get("image_url"):
                    r["image_url"] = off["image_url"]
                    candidate = None
                    break
                if not candidate and off.get("product_url"):
                    candidate = off.get("product_url")
            if not r.get("image_url") and candidate:
                idx_to_url[i] = candidate

        if idx_to_url:
            try:
                # backend resolver accepts dict index->url OR list; here: use dict with string keys
                safe_map = {str(i): url for i, url in idx_to_url.items()}
                raw = await resolve_images(safe_map)

                # convert keys back to integers & map images back to correct rows
                img_map = {int(k): v for k, v in raw.items()}

                for i, r in enumerate(rows):
                    if not r.get("image_url"):
                        img = img_map.get(i)
                        if img:
                            r["image_url"] = img

            except Exception as e:
                logger.exception(f"resolve_images failed: {e}")

        # 8) Diversity across stores, then cap
        rows = _interleave_by_store(rows, limit)

        # 9) Persist images back to KG
        for r in rows:
            img = r.get("image_url")
            offers = r.get("offers") or []
            if img and offers:
                dom = offers[0].get("store_domain")
                if dom:
                    pid = f"{dom}::{r['product_name'].lower()}"
                    try:
                        self.kg.set_product_image(pid, img)
                    except Exception:
                        pass

        return rows
