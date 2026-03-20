import os
from typing import Dict, List

from .models import BrowserEvidence


class BrowserAdapter:
    def __init__(self) -> None:
        self.enabled = os.getenv("RAWV_BROWSER_EVIDENCE", "false").lower() == "true"

    def capture(self, target_url: str, limit: int = 10) -> BrowserEvidence:
        if not self.enabled:
            return BrowserEvidence(
                available=False,
                details="Browser evidence is disabled. Set RAWV_BROWSER_EVIDENCE=true to enable.",
            )

        try:
            import sys
            import time
            import os as _os

            sys.path.append(_os.path.join(_os.getcwd(), "src", "Version-3", "chrome"))
            from chrome_client import open_page  # type: ignore
            from accessibilty_parser import capture_significant_uids  # type: ignore

            open_page(target_url)
            time.sleep(2)
            snapshot = capture_significant_uids(limit=limit, include_snapshot_text=True)
            raw_items: List[Dict[str, str]] = snapshot.get("items", [])
            compact_items = []
            for item in raw_items[:limit]:
                compact_items.append(
                    {
                        "uid": str(item.get("uid", "")),
                        "role": str(item.get("role", "element")),
                        "name": str(item.get("name", "")),
                    }
                )

            return BrowserEvidence(
                available=True,
                details=f"Captured {len(compact_items)} significant UI elements from browser.",
                items=compact_items,
            )
        except Exception as exc:
            return BrowserEvidence(
                available=False,
                details=f"Browser evidence unavailable: {exc}",
            )
