# app/agents/kg_agent.py
from __future__ import annotations

from datetime import date
import hashlib
from typing import List, Optional

from neo4j import GraphDatabase

from .kg_queries import (
    UPSERT_CYPHER,
    SEARCH_BEST_PRICES,
    SEARCH_DEALS,
    SEARCH_BEST_DEALS_PRODUCTS,
    SEARCH_BEST_PRICES_FILTERED,
    UPDATE_PRODUCT_IMAGE,  # must exist in kg_queries.py
)
from ..utils.settings import settings
from ..utils.models import DealItem


def _offer_id(store_domain: str, product_name: str, price: float, start_date_str: Optional[str]) -> str:
    """
    Stable ID for an offer so re-ingests update rather than duplicate.
    """
    key = f"{store_domain}|{product_name}|{price}|{start_date_str or ''}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def product_id_from_offer(domain: str, product_name: str) -> str:
    """
    Must match how Product.id is generated elsewhere (domain::lower(name)).
    """
    return f"{domain}::{product_name.lower()}"


class KGAgent:
    """Handles all Neo4j reads/writes."""

    def __init__(self) -> None:
        self.uri = settings.NEO4J_URI
        self.user = settings.NEO4J_USER
        self.password = settings.NEO4J_PASSWORD

        # Optional database name (Neo4j Enterprise / Aura)
        raw_db = getattr(settings, "NEO4J_DATABASE", None)
        self.db: Optional[str] = (raw_db or "").strip() or None

        self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))

    # ------------------ low-level ------------------

    def _session(self):
        """Open a Neo4j session with db if configured."""
        if self.db:
            return self.driver.session(database=self.db)
        return self.driver.session()

    # ------------------ upsert ------------------

    def upsert_offers(self, items: List[DealItem]) -> None:
        if not items:
            return

        payload = []
        for d in items:
            sd = d.start_date.isoformat() if d.start_date else None
            ed = d.end_date.isoformat() if d.end_date else None
            payload.append(
                {
                    **d.model_dump(),
                    "start_date": sd,
                    "end_date": ed,
                    "id": _offer_id(d.store_domain, d.product_name, d.price, sd),
                }
            )

        with self._session() as s:
            s.run(UPSERT_CYPHER, items=payload)

    # ------------------ searches ------------------

    def search_best_prices(
        self,
        q: str,
        max_price: Optional[float] = None,
        categories: Optional[List[str]] = None,
        stores: Optional[List[str]] = None,
    ) -> List[dict]:
        params = {
            "q": q or "",
            "maxPrice": max_price,
            "categories": categories,
            "stores": stores,
        }
        with self._session() as s:
            recs = s.run(SEARCH_BEST_PRICES, **params).data()
        return [dict(r) for r in recs]

    def search_deals(
        self,
        q: str,
        max_price: Optional[float] = None,
        categories: Optional[List[str]] = None,
    ) -> List[dict]:
        params = {
            "q": q or "",
            "maxPrice": max_price,
            "categories": categories,
            "today": date.today().isoformat(),
        }
        with self._session() as s:
            recs = s.run(SEARCH_DEALS, **params).data()
        return [dict(r) for r in recs]

    def search_best_deals_products(
        self,
        q: str,
        limit: int = 4,
        stores: Optional[List[str]] = None,
    ) -> List[dict]:
        params = {"q": q or "", "limit": limit, "stores": stores}
        with self._session() as s:
            recs = s.run(SEARCH_BEST_DEALS_PRODUCTS, **params).data()
        return [dict(r) for r in recs]

    def search_best_filtered(
        self,
        *,
        q: str,
        stores: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        max_price: Optional[float] = None,
        deal_only: bool = False,
        limit: int = 24,
    ) -> List[dict]:
        params = {
            "q": q or "",
            "stores": stores or [],
            "categories": categories or [],
            "maxPrice": max_price,
            "dealOnly": deal_only,
            "limit": limit,
        }
        with self._session() as s:
            recs = s.run(SEARCH_BEST_PRICES_FILTERED, **params).data()
        return [dict(r) for r in recs]

    # ------------------ images ------------------

    def set_product_image(self, product_id: str, image_url: Optional[str]) -> None:
        """
        Persist a resolved image URL on the Product node so future queries
        can use it without re-scraping.
        """
        if not image_url:
            return
        with self._session() as s:
            s.run(UPDATE_PRODUCT_IMAGE, product_id=product_id, image_url=image_url)
