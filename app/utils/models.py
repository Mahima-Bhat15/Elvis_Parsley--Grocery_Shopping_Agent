# app/utils/models.py
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel
from datetime import date


# ---------- Request models ----------

class UserQuery(BaseModel):
    message: str
    max_price: Optional[float] = None
    categories: Optional[List[str]] = None
    city: Optional[str] = None
    state: Optional[str] = None


class IngestRequest(BaseModel):
    message: str
    max_price: Optional[float] = None
    categories: Optional[List[str]] = None
    city: Optional[str] = None
    state: Optional[str] = None


# ---------- Core item (used for scraping / ingestion) ----------

class DealItem(BaseModel):
    store: str
    store_domain: str
    product_name: str
    price: float
    list_price: Optional[float] = None
    currency: str = "USD"
    discount_abs: Optional[float] = None
    discount_pct: Optional[float] = None
    deal_type: Optional[str] = None
    is_deal: Optional[bool] = None
    brand: Optional[str] = None
    size: Optional[str] = None
    category: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    terms: Optional[str] = None
    product_url: Optional[str] = None


# ---------- Best-price view (what /chat returns) ----------

class OfferView(BaseModel):
    store: Optional[str] = None
    store_domain: Optional[str] = None
    price: Optional[float] = None
    list_price: Optional[float] = None
    is_deal: Optional[bool] = None
    deal_type: Optional[str] = None
    discount_pct: Optional[float] = None
    discount_abs: Optional[float] = None
    product_url: Optional[str] = None


class BestPriceRow(BaseModel):
    product_name: str
    brand: Optional[str] = None
    category: Optional[str] = None
    offers: List[OfferView] = []   # top offers already sorted in Cypher


# ---------- Response models ----------

class OrchestratorResult(BaseModel):
    answer: str
    # Now the deals field contains rows with offers (best-price view)
    deals: List[BestPriceRow]


class IngestResult(BaseModel):
    ingested: int
    sample: List[dict] = []
