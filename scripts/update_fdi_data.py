#!/usr/bin/env python3
"""Refresh World Bank FDI panels and GitHub Pages JSON assets."""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import country_converter as coco
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
BASE_URL = "https://api.worldbank.org/v2"
START_YEAR = 1990
END_YEAR = datetime.now(timezone.utc).year
PER_PAGE = 20000
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "WB-FDI-Research-Dashboard/1.0 (public World Bank API)"})

INDICATORS = {
    "inflow_usd": "BX.KLT.DINV.CD.WD",
    "outflow_usd": "BM.KLT.DINV.CD.WD",
    "inflow_pct_gdp": "BX.KLT.DINV.WD.GD.ZS",
    "outflow_pct_gdp": "BM.KLT.DINV.WD.GD.ZS",
    "gdp_usd": "NY.GDP.MKTP.CD",
    "population": "SP.POP.TOTL",
}

CONTINENT_CODE_MAP = {
    "AF": "Africa", "AS": "Asia", "EU": "Europe", "NA": "North America",
    "SA": "South America", "OC": "Oceania",
    "Africa": "Africa", "Asia": "Asia", "Europe": "Europe",
    "North America": "North America", "South America": "South America",
    "Oceania": "Oceania", "Antarctica": "Antarctica",
}


def get_json(url: str, params: dict | None = None, attempts: int = 4):
    """GET a public API endpoint with bounded retries and helpful errors."""
    last_error = None
    for attempt in range(attempts):
        try:
            response = SESSION.get(url, params=params, timeout=90)
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, list) and len(payload) > 1 and isinstance(payload[0], dict):
                if payload[0].get("message"):
                    raise RuntimeError("World Bank API message: " + str(payload[0]["message"]))
            return payload
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"API request failed after {attempts} attempts: {url}: {last_error}")


def fetch_country_metadata() -> dict[str, dict]:
    payload = get_json(f"{BASE_URL}/country", {"format": "json", "per_page": 400})
    items = payload[1] if isinstance(payload, list) and len(payload) > 1 else []
    metadata = {}
    for item in items:
        iso3 = (item.get("id") or "").upper()
        region = item.get("region") or {}
        income = item.get("incomeLevel") or {}
        # Country records have a populated World Bank region. Aggregate entries do not.
        if len(iso3) != 3 or not region.get("id"):
            continue
        metadata[iso3] = {
            "country_name": item.get("name"),
            "region_id": region.get("id"),
            "region_name": region.get("value"),
            "income_level_id": income.get("id") or "NA",
            "income_level_name": income.get("value") or "Not classified",
            "latitude": as_float(item.get("latitude")),
            "longitude": as_float(item.get("longitude")),
        }
    if not metadata:
        raise RuntimeError("No country metadata was returned from the World Bank API.")
    return metadata


def as_float(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fetch_indicator(indicator_code: str, country: str = "all") -> dict[tuple[str, int], float | None]:
    endpoint = f"{BASE_URL}/country/{country}/indicator/{indicator_code}"
    payload = get_json(
        endpoint,
        {
            "format": "json",
            "per_page": PER_PAGE,
            "date": f"{START_YEAR}:{END_YEAR}",
        },
    )
    items = payload[1] if isinstance(payload, list) and len(payload) > 1 else []
    result = {}
    for item in items or []:
        iso3 = (item.get("countryiso3code") or "").upper()
        year_text = str(item.get("date") or "")
        if len(iso3) != 3 or not year_text.isdigit():
            continue
        year = int(year_text)
        if START_YEAR <= year <= END_YEAR:
            result[(iso3, year)] = as_float(item.get("value"))
    return result


def add_continents(metadata: dict[str, dict]) -> None:
    iso3_codes = list(metadata.keys())
    try:
        converted = coco.convert(names=iso3_codes, to="continent", not_found=None)
        if isinstance(converted, str):
            converted = [converted]
        for iso3, value in zip(iso3_codes, converted):
            metadata[iso3]["continent"] = CONTINENT_CODE_MAP.get(value, value if value in {
                "Africa", "Asia", "Europe", "North America", "South America", "Oceania"
            } else None)
    except Exception as exc:
        print(f"Warning: country-to-continent conversion unavailable: {exc}")

    # Fallback keeps most countries classified if the optional converter does not recognize an ISO3 code.
    fallback = {
        "AFR": "Africa", "SSF": "Africa", "EAS": "Asia", "SAS": "Asia",
        "ECS": "Europe", "LCN": None, "NAC": "North America", "MEA": None,
    }
    for row in metadata.values():
        if not row.get("continent"):
            row["continent"] = fallback.get(row.get("region_id"))


def load_cluster_definitions() -> dict[str, tuple[str, set[str]]]:
    path = ROOT / "config" / "country_clusters.csv"
    if not path.exists():
        return {}
    frame = pd.read_csv(path, dtype=str).fillna("")
    clusters = {}
    for cluster_id, group in frame.groupby("cluster_id", sort=True):
        names = group["cluster_name"].dropna()
        cluster_name = names.iloc[0] if not names.empty else cluster_id
        clusters[cluster_id] = (cluster_name, set(group["iso3"].str.upper()))
    return clusters


def clean_for_json(frame: pd.DataFrame) -> pd.DataFrame:
    """Convert pandas missing / infinite values to JSON nulls."""
    clean = frame.copy().astype(object)
    clean = clean.where(pd.notna(clean), None)
    clean = clean.replace([float("inf"), float("-inf")], None)
    return clean


def write_panel(frame: pd.DataFrame, stem: str) -> None:
    clean = clean_for_json(frame)
    clean.to_csv(DATA_DIR / f"{stem}.csv", index=False, na_rep="")
    clean.to_json(
        DATA_DIR / f"{stem}.json",
        orient="records",
        force_ascii=False,
        date_format="iso",
        double_precision=4,
    )


def sum_group(frame: pd.DataFrame, group_type: str, key_col: str, label_col: str) -> pd.DataFrame:
    usable = frame[frame[key_col].notna() & (frame[key_col].astype(str) != "")]
    if usable.empty:
        return pd.DataFrame()
    rows = []
    sum_columns = ["inflow_usd", "outflow_usd", "gdp_usd", "population"]
    for (group_id, group_name, year), group in usable.groupby([key_col, label_col, "year"], dropna=False):
        row = {
            "group_type": group_type,
            "group_id": str(group_id),
            "group_name": str(group_name),
            "year": int(year),
        }
        for col in sum_columns:
            series = group[col] if col in group else pd.Series(dtype=float)
            row[col] = series.sum(min_count=1)
        for direction in ["inflow", "outflow"]:
            flow = row.get(direction + "_usd")
            gdp = row.get("gdp_usd")
            row[direction + "_pct_gdp_aggregate"] = (flow / gdp * 100) if pd.notna(flow) and pd.notna(gdp) and gdp else None
        row["country_count_reporting_inflow"] = int(group["inflow_usd"].notna().sum())
        row["country_count_reporting_outflow"] = int(group["outflow_usd"].notna().sum())
        rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"Refreshing World Bank FDI series for {START_YEAR}-{END_YEAR} at {updated_at}")
    metadata = fetch_country_metadata()
    add_continents(metadata)
    indicator_data = {}
    for field, code in INDICATORS.items():
        print(f"Downloading {field} ({code})")
        indicator_data[field] = fetch_indicator(code, "all")

    all_keys = set()
    for observations in indicator_data.values():
        all_keys.update(key for key in observations if key[0] in metadata)

    country_rows = []
    clusters = load_cluster_definitions()
    country_to_clusters = {}
    for cluster_id, (cluster_name, iso3s) in clusters.items():
        for iso3 in iso3s:
            country_to_clusters.setdefault(iso3, []).append((cluster_id, cluster_name))

    for iso3, year in sorted(all_keys):
        meta = metadata[iso3]
        row = {
            "country_iso3": iso3,
            "country_name": meta["country_name"],
            "year": year,
            "world_bank_region_id": meta["region_id"],
            "world_bank_region": meta["region_name"],
            "income_level_id": meta["income_level_id"],
            "income_level": meta["income_level_name"],
            "continent": meta.get("continent"),
            "latitude": meta["latitude"],
            "longitude": meta["longitude"],
            "cluster_ids": ";".join(pair[0] for pair in country_to_clusters.get(iso3, [])),
            "cluster_names": "; ".join(pair[1] for pair in country_to_clusters.get(iso3, [])),
        }
        for field, observations in indicator_data.items():
            row[field] = observations.get((iso3, year))
        country_rows.append(row)

    country = pd.DataFrame(country_rows)
    if country.empty:
        raise RuntimeError("No country-year data returned. Existing published data has been left untouched.")
    country["year"] = country["year"].astype(int)
    for field in INDICATORS:
        country[field] = pd.to_numeric(country[field], errors="coerce")
    country = country.sort_values(["country_name", "year"]).reset_index(drop=True)
    write_panel(country, "fdi_country_panel")

    # World aggregate rows are retrieved directly from the WDI API, rather than summing countries.
    global_rows = {}
    for field, code in INDICATORS.items():
        for (iso3, year), value in fetch_indicator(code, "WLD").items():
            global_rows.setdefault(year, {"year": year})[field] = value
    global_frame = pd.DataFrame([global_rows[y] for y in sorted(global_rows)])
    if global_frame.empty:
        global_frame = pd.DataFrame(columns=["year", *INDICATORS.keys()])
    write_panel(global_frame, "fdi_global_panel")

    # Group totals are sums of available country-level net flows and GDP; ratios are calculated from totals.
    group_frames = [
        sum_group(country, "income_level", "income_level_id", "income_level"),
        sum_group(country, "world_bank_region", "world_bank_region_id", "world_bank_region"),
        sum_group(country, "continent", "continent", "continent"),
    ]
    for cluster_id, (cluster_name, iso3s) in clusters.items():
        subset = country[country["country_iso3"].isin(iso3s)].copy()
        if subset.empty:
            continue
        subset["cluster_id"] = cluster_id
        subset["cluster_name"] = cluster_name
        group_frames.append(sum_group(subset, "strategic_cluster", "cluster_id", "cluster_name"))
    group_frames = [part for part in group_frames if not part.empty]
    group_frame = pd.concat(group_frames, ignore_index=True) if group_frames else pd.DataFrame()
    if not group_frame.empty:
        group_frame = group_frame.sort_values(["group_type", "group_name", "year"]).reset_index(drop=True)
    write_panel(group_frame, "fdi_group_panel")

    # Add a schema-only file for the next-phase IMF bilateral positions integration; no values are imputed.
    bilateral_path = DATA_DIR / "bilateral_fdi_positions.csv"
    if not bilateral_path.exists():
        pd.DataFrame(columns=[
            "year", "reporting_economy_iso3", "reporting_economy_name",
            "counterpart_economy_iso3", "counterpart_economy_name",
            "direction", "instrument", "position_usd", "data_type",
            "mirror_data_flag", "source", "source_url",
        ]).to_csv(bilateral_path, index=False)

    def latest_non_null(frame, col):
        if col not in frame or frame.empty:
            return None
        valid = frame.loc[frame[col].notna(), "year"]
        return int(valid.max()) if not valid.empty else None

    status = {
        "updated_at_utc": updated_at,
        "start_year": START_YEAR,
        "requested_end_year": END_YEAR,
        "country_count": int(country["country_iso3"].nunique()),
        "country_year_observations": int(len(country)),
        "latest_year_by_indicator": {field: latest_non_null(country, field) for field in INDICATORS},
        "sources": [
            {"name": "World Bank World Development Indicators", "url": "https://api.worldbank.org/v2/"},
            {"name": "World Bank country metadata", "url": "https://api.worldbank.org/v2/country?format=json"},
            {"name": "IMF Direct Investment Positions by Counterpart Economy (bilateral data integration planned)", "url": "https://data.imf.org/en/Datasets/DIP"},
        ],
        "notes": [
            "Inward/outward values are annual net flows, not FDI stocks.",
            "Current US dollar amounts are nominal, not inflation-adjusted.",
            "Historical group totals use current country classifications.",
            "Strategic clusters are analyst-defined, overlapping groups.",
            "WDI does not provide partner-country breakdowns; bilateral position data must be sourced separately from IMF DIP.",
        ],
    }
    (DATA_DIR / "data_status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
