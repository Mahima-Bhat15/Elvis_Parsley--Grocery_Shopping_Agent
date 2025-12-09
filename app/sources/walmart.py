# app/sources/walmart.py
from .base_scraper import BaseScraper
from typing import List, Any
from ..utils.models import ScrapeTask, DealItem
from datetime import date
import os

__all__ = ["WalmartScraper"]


class WalmartScraper(BaseScraper):
    site = "Walmart"
    domains = ["walmart.com"]

    async def scrape_with_context(self, task: ScrapeTask, context: Any) -> List[DealItem]:
        """
        Minimal, resilient implementation:
        - If SCRAPER_MOCK=true -> return a fake deal (to validate the pipeline).
        - Else -> uses the provided Playwright 'context' to load a page (selectors are placeholders).
        """
        # Mock mode to validate import & end-to-end flow
        if os.getenv("SCRAPER_MOCK", "false").lower() == "true":
            return [
                DealItem(
                    store="Walmart",
                    store_domain="walmart.com",
                    product_name="Cereal Crunch 18oz",
                    price=2.49,
                    list_price=4.99,
                    discount_abs=2.50,
                    discount_pct=0.5,
                    deal_type="SALE",
                    start_date=date.today(),
                    currency="USD",
                    product_url="https://www.walmart.com/ip/mock",
                )
            ]

        # ---- Real scraping path (skeleton; replace selectors with real Walmart ones) ----
        try:
            page = await context.new_page()
            q = "+".join(task.search_terms) if task.search_terms else ""
            url = task.url.replace("{q}", q)
            await page.goto(url, wait_until="domcontentloaded")

            # TODO: Update to real Walmart selectors
            await page.wait_for_selector('[data-test="product-card"]', timeout=10000)
            cards = await page.query_selector_all('[data-test="product-card"]')

            items: List[DealItem] = []
            for card in cards:
                name_el = await card.query_selector(".name")
                if not name_el:
                    continue
                name = (await name_el.inner_text()).strip()

                price_el = await card.query_selector(".price .sale")
                if not price_el:
                    continue
                price_text = (await price_el.inner_text()).strip().replace("$", "")
                try:
                    price = float(price_text.split("/")[0])
                except Exception:
                    continue

                list_price = None
                list_el = await card.query_selector(".price .list")
                if list_el:
                    s = (await list_el.inner_text()).strip().replace("$", "")
                    try:
                        list_price = float(s)
                    except Exception:
                        pass

                deal_type = "SALE"
                badge = await card.query_selector(".badge.deal, .badge.bogo, .badge.club")
                if badge:
                    try:
                        deal_type = (await badge.inner_text()).strip().upper() or "SALE"
                    except Exception:
                        pass

                link_el = await card.query_selector("a.product-link")
                product_url = await link_el.get_attribute("href") if link_el else None

                items.append(
                    DealItem(
                        store="Walmart",
                        store_domain="walmart.com",
                        product_name=name,
                        price=price,
                        list_price=list_price,
                        discount_abs=(list_price - price) if list_price else None,
                        discount_pct=(1 - price / list_price) if list_price else None,
                        deal_type=deal_type,
                        start_date=date.today(),
                        currency="USD",
                        product_url=product_url,
                    )
                )

            await page.close()
            return items

        except Exception:
            # Fail softly so the pipeline continues
            return []
