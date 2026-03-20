import html
import re
import time
import urllib.request
from typing import Optional

from .models import SearchItem, SourceSnapshot


def _strip_html(raw: str) -> str:
    text = re.sub(r"<script.*?>.*?</script>", " ", raw, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style.*?>.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_title(raw: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", raw, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return _strip_html(match.group(1))


def fetch_source_snapshot(
    item: SearchItem,
    timeout_seconds: float = 10.0,
    max_chars: int = 3000,
    retries: int = 1,
) -> Optional[SourceSnapshot]:
    headers = {
        "User-Agent": "RAWV-Research/1.0 (+https://github.com/Shreemahor/rawv)",
        "Accept": "text/html,application/xhtml+xml",
    }

    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(item.url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
                content_type = response.headers.get("Content-Type", "")
                if "text/html" not in content_type and "xml" not in content_type:
                    return None
                body = response.read().decode("utf-8", errors="ignore")

            title = _extract_title(body) or item.title
            excerpt = _strip_html(body)
            if len(excerpt) > max_chars:
                excerpt = excerpt[:max_chars] + "..."

            return SourceSnapshot(title=title, url=item.url, excerpt=excerpt)
        except Exception:
            if attempt >= retries:
                return None
            time.sleep(0.6 * (attempt + 1))

    return None
