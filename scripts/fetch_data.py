"""
fetch_data.py
=============
Pulls Q3 (July-September) refrigerated truck volume data from the USDA AMS
Specialty Crops Program, via Socrata Open Data API at agtransport.usda.gov
(dataset rfpn-7etz — same source that powers the AgTransport Refrigerated
Truck Dashboard).

Output: data/q3_volumes.json — aggregated Q3 volumes by region & commodity,
4-year average. No API key required (public Socrata read).
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

SOCRATA_DOMAIN = "agtransport.usda.gov"
DATASET_ID = "rfpn-7etz"
API_URL = f"https://{SOCRATA_DOMAIN}/resource/{DATASET_ID}.json"

N_YEARS = 4
Q3_MONTHS = (7, 8, 9)
PAGE_SIZE = 50_000

# USDA AMS shipping regions — matches the image / AgRTQ canonical list.
KNOWN_REGIONS: list[str] = [
    "Arizona", "California", "Colorado", "Florida", "Great Lakes",
    "Mexico-Arizona", "Mexico-California", "Mexico-New Mexico", "Mexico-Texas",
    "Mid-Atlantic", "New York", "PNW", "Southeast", "Texas",
]


def get_app_token() -> str | None:
    return os.environ.get("SOCRATA_APP_TOKEN") or None


def _get_with_retry(
    url: str,
    *,
    params: dict[str, Any],
    headers: dict[str, str],
    timeout: int,
    max_retries: int = 3,
) -> requests.Response:
    retryable = (requests.exceptions.Timeout, requests.exceptions.ConnectionError)
    for attempt in range(max_retries + 1):
        try:
            return requests.get(url, params=params, headers=headers, timeout=timeout)
        except retryable as e:
            if attempt == max_retries:
                raise
            backoff = 2 ** attempt
            print(f"\n    {type(e).__name__} on attempt {attempt + 1}/{max_retries + 1}; "
                  f"retrying in {backoff}s …", flush=True)
            time.sleep(backoff)
            print(f"  → page offset={params.get('$offset', 0):>7} (retry) ", end="", flush=True)
    raise RuntimeError("unreachable")


def fetch_all(start_year: int, end_year: int) -> list[dict[str, Any]]:
    headers: dict[str, str] = {}
    token = get_app_token()
    if token:
        headers["X-App-Token"] = token

    rows: list[dict[str, Any]] = []
    offset = 0
    detected_date_field: str | None = None

    while True:
        params: dict[str, Any] = {
            "$limit": PAGE_SIZE,
            "$offset": offset,
            "$order": ":id",
        }
        if detected_date_field:
            params["$where"] = (
                f"{detected_date_field} >= '{start_year}-01-01T00:00:00.000' AND "
                f"{detected_date_field} < '{end_year + 1}-01-01T00:00:00.000'"
            )

        print(f"  → page offset={offset:>7} ", end="", flush=True)
        r = _get_with_retry(API_URL, params=params, headers=headers, timeout=300)
        if r.status_code != 200:
            print(f"HTTP {r.status_code}: {r.text[:200]}")
            sys.exit(1)
        batch = r.json()
        print(f"({len(batch):>5} rows)")
        if not batch:
            break

        if detected_date_field is None:
            for candidate in ("week_ending", "report_date", "date", "ship_date"):
                if candidate in batch[0]:
                    detected_date_field = candidate
                    print(f"    detected date field: {detected_date_field}")
                    break
            if detected_date_field is None:
                print("    WARNING: could not detect date field. Available keys:",
                      list(batch[0].keys()))
                rows.extend(batch)
                offset += len(batch)
                if len(batch) < PAGE_SIZE:
                    break
                continue
            # Restart with $where filter now that we have the date field
            rows = []
            offset = 0
            continue

        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        offset += len(batch)
        if offset > 5_000_000:
            print("    safety cap hit; stopping.")
            break

    return rows


def parse_date(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {"production": {}, "commodities": [], "regions": []}

    sample = records[0]
    date_field = next((f for f in ("week_ending", "report_date", "date", "ship_date") if f in sample), None)
    region_field = next((f for f in ("region", "origin_region", "shipping_region") if f in sample), None)
    commodity_field = next((f for f in ("commodity", "commodity_name", "item") if f in sample), None)
    volume_field = next((f for f in ("volume", "shipment_volume", "total_volume", "volume_tons",
                                     "pounds", "volume_pounds") if f in sample), None)

    print(f"  fields → date={date_field}, region={region_field}, commodity={commodity_field}, volume={volume_field}")

    if not all([date_field, region_field, commodity_field, volume_field]):
        print("  ERROR: could not auto-detect required fields. Sample keys:")
        for k in sample.keys():
            print(f"    - {k}")
        sys.exit(1)

    acc: dict[str, dict[str, dict[int, dict[int, float]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    )

    kept = 0
    for rec in records:
        d = parse_date(rec.get(date_field, ""))
        if d is None or d.month not in Q3_MONTHS:
            continue
        region = (rec.get(region_field) or "").strip()
        commodity = (rec.get(commodity_field) or "").strip()
        if not region or not commodity:
            continue
        try:
            vol = float(rec.get(volume_field, ""))
        except (TypeError, ValueError):
            continue
        # Unit normalization: AMS reefer volumes are typically tons → convert to lbs
        if "pound" not in volume_field.lower() and "lbs" not in volume_field.lower():
            vol *= 2000.0
        acc[commodity][region][d.year][d.month] += vol
        kept += 1

    print(f"  kept {kept:,} Q3 records → {len(acc)} commodities × "
          f"{len({r for c in acc.values() for r in c})} regions")

    production: dict[str, dict[str, dict[str, float]]] = {}
    for commodity, regions in acc.items():
        production[commodity] = {}
        for region, by_year in regions.items():
            n = len(by_year)
            if n == 0:
                continue
            month_totals = {7: 0.0, 8: 0.0, 9: 0.0}
            for year_data in by_year.values():
                for m in Q3_MONTHS:
                    month_totals[m] += year_data.get(m, 0.0)
            production[commodity][region] = {
                "jul": round(month_totals[7] / n / 1_000_000, 2),
                "aug": round(month_totals[8] / n / 1_000_000, 2),
                "sep": round(month_totals[9] / n / 1_000_000, 2),
            }

    # Keep only the top 20 commodities by Q3 total volume (dashboard readability)
    commodity_totals = [
        (c, sum(months["jul"] + months["aug"] + months["sep"] for months in regions.values()))
        for c, regions in production.items()
    ]
    commodity_totals.sort(key=lambda x: x[1], reverse=True)
    top_commodities = [c for c, _ in commodity_totals[:20]]
    production = {c: production[c] for c in top_commodities}

    # "All Commodities" rollup
    all_c: dict[str, dict[str, float]] = defaultdict(lambda: {"jul": 0.0, "aug": 0.0, "sep": 0.0})
    for c_data in production.values():
        for region, months in c_data.items():
            for m in ("jul", "aug", "sep"):
                all_c[region][m] += months[m]
    for region in all_c:
        for m in ("jul", "aug", "sep"):
            all_c[region][m] = round(all_c[region][m], 2)
    production = {"All Commodities": dict(all_c), **production}

    all_regions = sorted({r for c in production.values() for r in c})
    return {
        "production": production,
        "commodities": list(production.keys()),
        "regions": all_regions,
    }


def main() -> None:
    now = datetime.now()
    end_year = now.year - 1
    start_year = end_year - (N_YEARS - 1)

    print(f"Fetching AMS Refrigerated Truck Volumes ({DATASET_ID}) for {start_year}–{end_year} …")
    records = fetch_all(start_year, end_year)
    print(f"  total raw rows: {len(records):,}\n")

    print("Aggregating Q3 (Jul–Sep) by commodity × region …")
    agg = aggregate(records)

    out = {
        "metadata": {
            "source": f"USDA AMS Specialty Crops Movement Reports (Socrata: {SOCRATA_DOMAIN}/resource/{DATASET_ID})",
            "years": [str(y) for y in range(start_year, end_year + 1)],
            "n_years_avg": N_YEARS,
            "metric": "Refrigerated truck volume, Q3 (Jul-Sep) average, in millions of pounds",
            "fetched_at": now.isoformat(),
        },
        "production": agg["production"],
        "commodities": agg["commodities"],
        "regions": agg["regions"],
        "known_regions": KNOWN_REGIONS,
    }

    out_path = Path(__file__).resolve().parent.parent / "data" / "q3_volumes.json"
    out_path.parent.mkdir(exist_ok=True, parents=True)
    out_path.write_text(json.dumps(out, indent=2))
    print(f"\n✓ Wrote {out_path}")


if __name__ == "__main__":
    main()
