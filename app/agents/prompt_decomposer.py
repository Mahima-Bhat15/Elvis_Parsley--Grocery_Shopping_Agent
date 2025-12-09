# app/agents/prompt_decomposer.py
from ..utils.models import UserQuery, ScrapeTask
from ..utils.llm import llm
from ..utils.settings import settings
import json

SYSTEM = """
You turn grocery requests into JSON array of site-specific scraping tasks.
Focus on deals: sale, bogo, coupon, club price. Use user's city/state when given.
Return ONLY JSON. Fields: site, url, search_terms, filters.
"""

DEFAULT_SITES = [
    {"site": "Target",  "url": "https://www.target.com/s?searchTerm={q}"},
    {"site": "Walmart", "url": "https://www.walmart.com/search?q={q}"},
]

class PromptDecomposer:
    def build_tasks(self, q: UserQuery) -> list[ScrapeTask]:
        user = f"""
Request: {q.message}
City: {q.city or settings.DEFAULT_CITY}
State: {q.state or settings.DEFAULT_STATE}
Sites:
{json.dumps(DEFAULT_SITES)}
Output JSON array only.
"""
        txt = None
        try:
            # LLM path (may fail if no key / network / etc.)
            txt = llm.complete(SYSTEM, user)
            raw = json.loads(txt)
        except Exception:
            # Fallback: deterministic static tasks
            raw = [
                {
                    "site": s["site"],
                    "url": s["url"].replace("{q}", q.message),
                    "search_terms": [q.message],
                    "filters": {},
                }
                for s in DEFAULT_SITES
            ]
        return [ScrapeTask(**r) for r in raw]
