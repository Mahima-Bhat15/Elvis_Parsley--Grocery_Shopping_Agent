from .base_scraper import BaseScraper
from typing import List
from playwright.async_api import BrowserContext
from ..utils.models import ScrapeTask, DealItem
from datetime import date


class TargetGroceryScraper(BaseScraper):
    site = "Target"
    domains = ["target.com"]

    async def scrape_with_context(self, task: ScrapeTask, context: BrowserContext) -> List[DealItem]:
        page = await context.new_page()
        q = "+".join(task.search_terms) if task.search_terms else ""
        url = task.url.replace("{q}", q)
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_selector("li[data-test='product-list-item']", timeout=10000)

        tiles = await page.query_selector_all("li[data-test='product-list-item']")
        items: List[DealItem] = []

        for t in tiles:
            # Product name
            name_el = await t.query_selector("a[data-test='product-title']")
            if not name_el:
                continue
            name = (await name_el.inner_text()).strip()

            # Sale and list prices
            sale_el = await t.query_selector("span[data-test='current-price']")
            if not sale_el:
                continue  # Skip items without visible sale or price
            price_text = (await sale_el.inner_text()).strip().replace("$", "")

            list_el = await t.query_selector("span[data-test='was-price']")
            list_price = None
            if list_el:
                try:
                    list_price = float((await list_el.inner_text()).strip().replace("$", ""))
                except Exception:
                    pass

            # Convert sale price to float
            try:
                price = float(price_text.split("/")[0])
            except Exception:
                continue

            # Detect deal type or promo flag
            badge_el = await t.query_selector("span[data-test='promo-badge']")
            deal_type = (await badge_el.inner_text()).strip().upper() if badge_el else "SALE"

            # Product link
            link_el = await t.query_selector("a[data-test='product-title']")
            product_url = await link_el.get_attribute("href") if link_el else None
            if product_url and product_url.startswith("/"):
                product_url = "https://www.target.com" + product_url

            # Append deal item
            items.append(
                DealItem(
                    store="Target",
                    store_domain="target.com",
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
