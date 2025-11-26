#!/usr/bin/env python3
"""
Enrich a CSV of observations with taxonomic metadata from the iNaturalist API.

Adds columns:
- iconic_taxon_name
- common_name (preferred_common_name)
- group (flora / fauna / other / unknown) derived from iconic_taxon_name

Usage (from gdal_tools container):
  python3 eco_app.py enrich_taxa --in data/observations_swiss.csv --out data/observations_with_taxa.csv
"""
import argparse
import itertools
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import pandas as pd


API_URL = "https://api.inaturalist.org/v1/taxa"
MAX_IDS_PER_CALL = 200  # iNat allows up to ~200 ids per request
ICONIC_ANIMALS = {
    "mammalia",
    "aves",
    "reptilia",
    "amphibia",
    "actinopterygii",
    "insecta",
    "arachnida",
    "mollusca",
}


def _chunks(iterable, size):
    it = iter(iterable)
    while True:
        batch = list(itertools.islice(it, size))
        if not batch:
            break
        yield batch


def _print_progress(current, total, prefix=""):
    if total <= 0:
        return
    frac = current / total
    bar_len = 30
    filled = int(bar_len * frac)
    bar = "#" * filled + "-" * (bar_len - filled)
    sys.stdout.write(f"\r{prefix}[{bar}] {int(frac*100):3d}% ({current}/{total})")
    sys.stdout.flush()
    if current >= total:
        sys.stdout.write("\n")


def fetch_taxa(ids, delay=0.3, retries=3):
    """
    Fetch taxon metadata for a list of numeric taxon IDs.
    Returns a dict {taxon_id: {"iconic_taxon_name": ..., "common_name": ...}}
    """
    results = {}
    ids = list(ids)

    for batch in _chunks(ids, MAX_IDS_PER_CALL):
        params = "&".join(f"id={tid}" for tid in batch)
        url = f"{API_URL}?{params}&per_page={MAX_IDS_PER_CALL}"
        for attempt in range(1, retries + 1):
            try:
                with urllib.request.urlopen(url, timeout=30) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                for taxon in payload.get("results", []):
                    tid = taxon.get("id")
                    if tid is None:
                        continue
                    results[int(tid)] = {
                        "iconic_taxon_name": taxon.get("iconic_taxon_name"),
                        "common_name": taxon.get("preferred_common_name"),
                    }
                break  # success
            except urllib.error.HTTPError as e:
                # Backoff on rate limiting or server errors
                if e.code in (429, 500, 502, 503, 504) and attempt < retries:
                    time.sleep(delay * attempt)
                    continue
                raise
            except urllib.error.URLError:
                if attempt < retries:
                    time.sleep(delay * attempt)
                    continue
                raise
        time.sleep(delay)
    return results


def derive_group(meta):
    iconic = (meta or {}).get("iconic_taxon_name") or ""
    iconic_low = iconic.lower()
    if iconic_low == "plantae":
        return "flora"
    if iconic_low in ICONIC_ANIMALS:
        return "fauna"
    return "other" if iconic else "unknown"


def enrich_csv(inp, out, delay, batch_size):
    df = pd.read_csv(inp)
    if "taxon_id" not in df.columns:
        raise ValueError("Input CSV must contain a 'taxon_id' column.")

    unique_ids = sorted({int(t) for t in pd.to_numeric(df["taxon_id"], errors="coerce").dropna().unique()})
    if not unique_ids:
        raise ValueError("No valid taxon_id values found in the input CSV.")

    # Fetch metadata
    mapping = {}
    processed_ids = 0
    for batch in _chunks(unique_ids, batch_size):
        fetched = fetch_taxa(batch, delay=delay)
        mapping.update(fetched)
        processed_ids += len(batch)
        # Progress on attempted IDs to ensure 100% even if some are missing
        _print_progress(min(processed_ids, len(unique_ids)), len(unique_ids), prefix="Fetch taxa ")

    # Map back to dataframe
    df["iconic_taxon_name"] = df["taxon_id"].apply(
        lambda tid: mapping.get(int(tid), {}).get("iconic_taxon_name") if pd.notna(tid) else None
    )
    df["common_name"] = df["taxon_id"].apply(
        lambda tid: mapping.get(int(tid), {}).get("common_name") if pd.notna(tid) else None
    )
    df["group"] = df["taxon_id"].apply(lambda tid: derive_group(mapping.get(int(tid)) if pd.notna(tid) else None))

    df.to_csv(out, index=False)
    return out


def main():
    parser = argparse.ArgumentParser(description="Enrich observations CSV with iNaturalist taxonomic info (iconic taxon).")
    parser.add_argument("--in", dest="inp", required=True, help="Input CSV with a 'taxon_id' column.")
    parser.add_argument("--out", dest="out", required=True, help="Output CSV path.")
    parser.add_argument("--batch-size", type=int, default=MAX_IDS_PER_CALL, help="IDs per API call (<=200 recommended).")
    parser.add_argument("--delay", type=float, default=0.3, help="Delay in seconds between API calls.")
    args = parser.parse_args()

    out_path = os.path.abspath(args.out)
    try:
        produced = enrich_csv(args.inp, out_path, delay=args.delay, batch_size=args.batch_size)
        print(produced)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
