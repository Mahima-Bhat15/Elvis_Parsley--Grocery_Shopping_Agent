from typing import List
from ..utils.models import ScrapeTask, DealItem


class BaseScraper:
    site: str
    domains: list[str]


async def scrape(self, task: ScrapeTask) -> List[DealItem]:
    raise NotImplementedError