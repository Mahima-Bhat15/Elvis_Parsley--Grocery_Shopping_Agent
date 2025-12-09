from __future__ import annotations
import asyncio
from typing import List, Dict, Optional
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
}


def _absolute(store_domain: Optional[str], product_url: str) -> str:
    """
    Ensure product_url is absolute. If it's already absolute, return it.
    If it's root-relative, prefix with https://{store_domain}.
    """
    if not product_url:
        return product_url
    s = product_url.strip()
    if s.startswith("http://") or s.startswith("https://"):
        return s
    if s.startswith("//"):
        return "https:" + s
    if s.startswith("/"):
        base = f"https://{store_domain}" if store_domain else "https://www.walmart.com"
        return urljoin(base, s)
    # bare path: assume store domain if given
    if store_domain:
        return f"https://{store_domain.rstrip('/')}/{s.lstrip('/')}"
    return s


async def _fetch(session: aiohttp.ClientSession, url: str) -> Optional[str]:
    try:
        async with session.get(url, headers=DEFAULT_HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status >= 400:
                return None
            return await resp.text(errors="ignore")
    except Exception:
        return None


def _extract_image(html: str, page_url: str) -> Optional[str]:
    """
    Heuristics to pull a representative image for a product page.
    Order: og:image, twitter:image, JSON-LD offers/product image, then common selectors.
    """
    soup = BeautifulSoup(html, "html.parser")

    # <meta property="og:image" ...>
    m = soup.find("meta", attrs={"property": "og:image"}) or soup.find("meta", attrs={"name": "og:image"})
    if m and m.get("content"):
        return urljoin(page_url, m["content"].strip())

    # <meta name="twitter:image" ...>
    m = soup.find("meta", attrs={"name": "twitter:image"}) or soup.find("meta", attrs={"property": "twitter:image"})
    if m and m.get("content"):
        return urljoin(page_url, m["content"].strip())

    # JSON-LD Product
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            import json
            data = json.loads(tag.string or "{}")
            # Sometimes it's a list
            candidates = data if isinstance(data, list) else [data]
            for d in candidates:
                if d.get("@type") in ("Product", "Offer") and d.get("image"):
                    img = d["image"]
                    if isinstance(img, list):
                        img = img[0]
                    return urljoin(page_url, str(img).strip())
        except Exception:
            pass

    # Common selectors (very defensive)
    sel = [
        "img#main-image", "img#imgTagWrapperId img",       # Amazon-like
        "img[data-testid='hero-image']",                   # Target-like
        "img[class*='hero']", "img[src*='walmartimages']", # Walmart-like
        "img[alt*='product']", "img[alt*='Product']",
    ]
    for s in sel:
        el = soup.select_one(s)
        if el and el.get("src"):
            return urljoin(page_url, el["src"].strip())

    # Fallback: the largest image on the page
    best = None
    best_area = 0
    for img in soup.find_all("img"):
        src = (img.get("src") or "").strip()
        if not src:
            continue
        w = int(img.get("width") or 0)
        h = int(img.get("height") or 0)
        area = w * h
        if area > best_area:
            best_area = area
            best = urljoin(page_url, src)
    return best


async def _resolve_one(session: aiohttp.ClientSession, row: Dict) -> Dict:
    product_url = row.get("product_url")
    store_domain = row.get("store_domain")
    out = {"product_url": product_url, "store_domain": store_domain, "image_url": None}

    if not product_url:
        return out

    abs_url = _absolute(store_domain, product_url)
    html = await _fetch(session, abs_url)
    if not html:
        return out

    img = _extract_image(html, abs_url)
    if img:
        out["image_url"] = img
    return out


async def resolve_images(items: List[Dict]) -> List[Dict]:
    """
    Accepts: [{"product_url": "...", "store_domain": "walmart.com"}, ...]
    Returns the same length list with "image_url" field filled if found.
    """
    # Normalize upfront so front-end/orchestrator can pass any domain/relative URLs.
    for it in items:
        if it.get("product_url"):
            it["product_url"] = _absolute(it.get("store_domain"), it["product_url"])

    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(*[_resolve_one(session, r) for r in items], return_exceptions=True)

    out: List[Dict] = []
    for r in results:
        if isinstance(r, Exception):
            out.append({"product_url": None, "store_domain": None, "image_url": None})
        else:
            out.append(r)
    return out
