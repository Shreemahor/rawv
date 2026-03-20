import time
from typing import List

from .models import SearchItem

try:
    from ddgs import DDGS
except Exception:
    DDGS = None


def run_search(query: str, limit: int = 5, retries: int = 2, retry_delay: float = 0.75) -> List[SearchItem]:
    if DDGS is None:
        return []

    attempt = 0
    while attempt <= retries:
        try:
            items: List[SearchItem] = []
            with DDGS() as ddgs:
                results = ddgs.text(query, max_results=limit)
            for result in results:
                title = result.get("title") or result.get("heading")
                url = result.get("href") or result.get("url")
                if title and url:
                    items.append(SearchItem(title=title, url=url))
            return items
        except Exception:
            if attempt == retries:
                return []
            time.sleep(retry_delay * (attempt + 1))
            attempt += 1

    return []
