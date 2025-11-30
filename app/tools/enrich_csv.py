#!/usr/bin/env python3
"""
Outil unique pour enrichir un CSV :
- mode 'taxa'       : ajoute iconic_taxon_name / common_name / group via iNaturalist
- mode 'elevation'  : ajoute la colonne elevation_m via les tuiles swissALTI3D

Usage (depuis eco_app) :
  python3 eco_app.py enrich_csv taxa --in <fichier> --out <fichier>
  python3 eco_app.py enrich_csv elevation --in <fichier> --out <fichier>
"""
import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Iterable, Dict, Any, List

import pandas as pd

from tools.utils import Utils


# ----------------------------- TAXA MODE ---------------------------------
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


def fetch_taxa(ids: Iterable[int], delay: float = 0.3, retries: int = 3) -> Dict[int, Dict[str, Any]]:
    """Fetch taxon metadata for a list of numeric taxon IDs."""
    results = {}
    ids = list(ids)

    for batch in Utils.chunks(ids, MAX_IDS_PER_CALL):
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


def derive_group(meta: Dict[str, Any]) -> str:
    iconic = (meta or {}).get("iconic_taxon_name") or ""
    iconic_low = iconic.lower()
    if iconic_low == "plantae":
        return "flora"
    if iconic_low in ICONIC_ANIMALS:
        return "fauna"
    return "other" if iconic else "unknown"


def run_taxa_mode(args: argparse.Namespace) -> str:
    out_path = args.out 
    inp = args.inp
    base = os.path.splitext(os.path.basename(inp))[0] 
    suffix = "_enriched_taxa.csv" if "enriched" not in base else "_taxa.csv"
    if not args.out:
        raise ValueError("--out est requis pour le mode taxa.")
    out_path = os.path.abspath(args.out)

    df = pd.read_csv(inp)
    if "taxon_id" not in df.columns:
        raise ValueError("Input CSV must contain a 'taxon_id' column.")

    unique_ids = sorted({int(t) for t in pd.to_numeric(df["taxon_id"], errors="coerce").dropna().unique()})
    if not unique_ids:
        raise ValueError("No valid taxon_id values found in the input CSV.")

    mapping = {}
    processed_ids = 0
    for batch in Utils.chunks(unique_ids, args.batch_size):
        fetched = fetch_taxa(batch, delay=args.delay)
        mapping.update(fetched)
        processed_ids += len(batch)
        Utils.print_progress(min(processed_ids, len(unique_ids)), len(unique_ids), prefix="Fetch taxa ")

    df["iconic_taxon_name"] = df["taxon_id"].apply(
        lambda tid: mapping.get(int(tid), {}).get("iconic_taxon_name") if pd.notna(tid) else None
    )
    df["common_name"] = df["taxon_id"].apply(
        lambda tid: mapping.get(int(tid), {}).get("common_name") if pd.notna(tid) else None
    )
    df["group"] = df["taxon_id"].apply(lambda tid: derive_group(mapping.get(int(tid)) if pd.notna(tid) else None))

    df.to_csv(out_path, index=False)
    return out_path


# -------------------------- ELEVATION MODE -------------------------------
# helpers defined at top-level so Pool can pickle them
_GDAL = None  # set at runtime inside run_elevation_mode

def e_n_to_tilekey(e, n):
    return f"{int(e//1000)}-{int(n//1000)}"

def build_tile_index(tif_dir):
    idx = {}
    for root, _, files in os.walk(tif_dir):
        for fn in files:
            if not fn.lower().endswith(".tif"):
                continue
            parts = fn.split("_")
            key = None
            for p in parts:
                if "-" in p and p.replace("-", "").isdigit():
                    key = p
                    break
            if key:
                idx[key] = os.path.join(root, fn)
    if not idx:
        raise RuntimeError(f"Aucune tuile trouvee sous {tif_dir}")
    return idx

def process_tile(args_inner):
    # uses the global _GDAL set inside run_elevation_mode
    if _GDAL is None:
        raise RuntimeError("GDAL module non initialisé.")
    tile_path, rows = args_inner  # rows: [(row_idx, E, N)]
    ds = _GDAL.Open(tile_path, _GDAL.GA_ReadOnly)
    gt = ds.GetGeoTransform()
    band = ds.GetRasterBand(1)
    out = {}
    for row_idx, e, n in rows:
        px = int((e - gt[0]) / gt[1])
        py = int((n - gt[3]) / gt[5])
        if 0 <= px < ds.RasterXSize and 0 <= py < ds.RasterYSize:
            val = band.ReadAsArray(px, py, 1, 1)[0, 0]
            nd = band.GetNoDataValue()
            if nd is not None and float(val) == float(nd):
                out[row_idx] = ""
            else:
                out[row_idx] = f"{float(val):.3f}"
        else:
            out[row_idx] = ""
    return out

def run_elevation_mode(args: argparse.Namespace) -> str:
    # Lazy imports to keep taxa-only usage light
    from multiprocessing import Pool, cpu_count
    import_types = (ImportError, ModuleNotFoundError)
    try:
        from osgeo import gdal
    except import_types as exc:  # type: ignore
        print("GDAL (osgeo) est requis pour le mode elevation.", file=sys.stderr)
        raise

    global _GDAL
    _GDAL = gdal

    inp = args.inp or Utils.get_data_most_filtered_path(["elevation"])
    if args.out is None:
        in_file_name, ext = os.path.splitext(os.path.basename(inp))
        args.out = Utils.name_file(inp, "enriched", ["elevation"])
    out_path = args.out

    # Verifier et importer les tuiles si necessaire
    if not Utils.tiles_available(args.tif_dir):
        print(f"Aucune tuile trouvee dans {args.tif_dir}.")
        choice = input("Voulez-vous lancer l'import des tuiles maintenant ? [y/n]: ").strip().lower()
        if choice.startswith("y"):
            try:
                from import_tiles import import_tiles
            except Exception as exc:
                print(f"Impossible d'importer le module import_tiles: {exc}", file=sys.stderr)
                sys.exit(1)
            import_tiles(force=False)
            if not Utils.tiles_available(args.tif_dir):
                print("Aucune tuile n'a ete trouvee apres l'import. Telechargez-les manuellement ou via import_tiles.py.", file=sys.stderr)
                sys.exit(1)
        else:
            print("Veuillez telecharger les tuiles manuellement ou via import_tiles.py puis relancer.", file=sys.stderr)
            sys.exit(1)

    print("Indexation des tuiles...")
    tile_index = build_tile_index(args.tif_dir)
    print(f"{len(tile_index)} tuiles indexees.")

    # 1) lire CSV
    print("Lecture du CSV source...")
    with open(inp, "r", encoding="utf-8", newline="") as fin:
        reader = csv.DictReader(fin)
        fields = reader.fieldnames
        if not fields:
            raise RuntimeError("CSV vide")
        # detecter colonnes lon/lat
        if args.lon_field and args.lat_field:
            lon_field, lat_field = args.lon_field, args.lat_field
        else:
            lower = [f.lower() for f in fields]
            if "longitude" in lower and "latitude" in lower:
                lon_field = fields[lower.index("longitude")]
                lat_field = fields[lower.index("latitude")]
            elif "lon" in lower and "lat" in lower:
                lon_field = fields[lower.index("lon")]
                lat_field = fields[lower.index("lat")]
            else:
                raise RuntimeError("Colonnes lon/lat introuvables")
        rows_data = list(reader)

    total_rows = len(rows_data)
    print(f"{total_rows} lignes a traiter.")

    # 2) projeter & grouper
    print("Projection et groupement par tuile...")
    from collections import defaultdict
    by_tile = defaultdict(list)
    for i, row in enumerate(rows_data):
        row["elevation_m"] = ""

    for i, row in enumerate(rows_data):
        try:
            lon = float(row[lon_field]); lat = float(row[lat_field])
        except Exception:
            continue
        E, N = Utils.wgs84_to_lv95(lon, lat)
        tile_key = e_n_to_tilekey(E, N)
        tif_path = tile_index.get(tile_key)
        if not tif_path:
            continue
        by_tile[tif_path].append((i, E, N))

    print(f"{len(by_tile)} tuiles reellement utilisees (ayant au moins un point).")

    # 3) traitement parallele
    workers = args.workers or cpu_count()
    tasks = list(by_tile.items())
    print(f"Traitement en parallele avec {workers} worker(s)...")

    results = {}
    done_tiles = 0
    total_tiles = len(tasks)

    def _update_progress():
        Utils.print_progress(done_tiles, total_tiles if total_tiles else 1, prefix="", bar_len=30)

    with Pool(processes=workers) as pool:
        for partial in pool.imap_unordered(process_tile, tasks):
            results.update(partial)
            done_tiles += 1
            _update_progress()

    print("Ecriture du CSV de sortie...")
    out_fields = fields + (["elevation_m"] if "elevation_m" not in fields else [])
    with open(out_path, "w", encoding="utf-8", newline="") as fout:
        writer = csv.DictWriter(fout, fieldnames=out_fields)
        writer.writeheader()
        for i, row in enumerate(rows_data, start=1):
            if i-1 in results:
                row["elevation_m"] = results[i-1]
            writer.writerow(row)
            if i % 1000 == 0 or i == total_rows:
                Utils.print_progress(i, total_rows)

    print("Termine.")
    return out_path


# ------------------------------ MAIN -------------------------------------
def build_parser():
    parser = argparse.ArgumentParser(description="Enrichir un CSV (taxa ou elevation).")
    subparsers = parser.add_subparsers(dest="mode", required=True, help="Mode d'enrichissement")

    p_taxa = subparsers.add_parser("taxa", help="Enrichir avec les infos iNaturalist (iconic/common/group).")
    p_taxa.add_argument("--in", dest="inp", default=None, help="Input CSV avec colonne 'taxon_id'.")
    p_taxa.add_argument("--out", dest="out", required=True, help="CSV de sortie.")
    p_taxa.add_argument("--batch-size", type=int, default=MAX_IDS_PER_CALL, help="IDs par appel API (<=200).")
    p_taxa.add_argument("--delay", type=float, default=0.3, help="Pause entre appels API.")

    p_elev = subparsers.add_parser("elevation", help="Enrichir avec l'altitude swissALTI3D.")
    p_elev.add_argument("--in", dest="inp", default=None, help="Input CSV.")
    p_elev.add_argument("--out", dest="out", default=None, help="CSV de sortie (defaut: <in>_elevation.csv).")
    p_elev.add_argument("--tif-dir", dest="tif_dir", default=Utils.TILES_DIR, help="Dossier des tuiles swissALTI3D.")
    p_elev.add_argument("--lon-field", dest="lon_field", help="Nom de la colonne longitude.")
    p_elev.add_argument("--lat-field", dest="lat_field", help="Nom de la colonne latitude.")
    p_elev.add_argument("--workers", type=int, default=0, help="Nb de processus (0 = nb CPU).")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.inp is None:
        args.inp = Utils.get_data_most_filtered_path([args.mode])

    if args.out is None:
        args.out = Utils.name_file(args.inp, "enriched", [args.mode])

    try:
        if args.mode == "taxa":
            out = run_taxa_mode(args)
        elif args.mode == "elevation":
            out = run_elevation_mode(args)
        else:
            parser.error("Mode inconnu.")
            return
        print(out)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
