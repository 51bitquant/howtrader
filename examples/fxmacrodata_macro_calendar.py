from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.request import Request, urlopen


def load_fxmacrodata_events(currency: str = "usd", top_tier_only: bool = True) -> list[dict[str, Any]]:
    headers = {"Accept": "application/json", "User-Agent": "howtrader-fxmacrodata-example"}
    request = Request(
        f"https://api.fxmacrodata.com/v1/calendar/{currency.lower()}",
        headers=headers,
    )
    api_key = (os.getenv("FXMD_API_KEY") or "").strip()
    if api_key:
        if not api_key.isprintable():
            raise ValueError("FXMD_API_KEY contains invalid characters")
        # Unredirected: the key is never re-sent if the API answers with a redirect.
        request.add_unredirected_header("X-API-Key", api_key)
    with urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        raise ValueError("Unexpected FXMacroData calendar response")
    rows = [row for row in data if isinstance(row, dict)]
    if top_tier_only:
        rows = [row for row in rows if row.get("top_tier_for_currency") or row.get("market_tier") == 1]
    return rows


def macro_event_guard(timestamp: datetime, events: list[dict[str, Any]]) -> bool:
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    before = timedelta(hours=4)
    after = timedelta(hours=2)
    for row in events:
        value = row.get("announcement_datetime_utc") or row.get("announcement_datetime_local")
        if not value:
            continue
        event_time = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if event_time - before <= timestamp <= event_time + after:
            return True
    return False


if __name__ == "__main__":
    events = load_fxmacrodata_events("usd")
    print(f"Loaded {len(events)} top-tier USD macro releases")
    print("Macro guard active:", macro_event_guard(datetime.now(timezone.utc), events))

