#!/usr/bin/env python3
import csv, os, sys, argparse
from osgeo import gdal
from multiprocessing import Pool, cpu_count

# ---------- utils progression ----------
def print_progress(current, total, bar_len=40):
    frac = current / total if total else 1
    filled = int(bar_len * frac)
    bar = "#" * filled + "-" * (bar_len - filled)
    percent = int(frac * 100)
    # \r pour réécrire la même ligne
    sys.stdout.write(f"\r[{bar}] {percent:3d}% ({current}/{total})")
    sys.stdout.flush()
    if current >= total:
        sys.stdout.write("\n")

# ---------- conversions ----------
def wgs84_to_lv95(lon_deg, lat_deg):
    lat_sec = lat_deg * 3600.0
    lon_sec = lon_deg * 3600.0
    lat_aux = (lat_sec - 169028.66) / 10000.0
    lon_aux = (lon_sec - 26782.5) / 10000.0
    E = (2600072.37
         + 211455.93 * lon_aux
         - 10938.51 * lon_aux * lat_aux
         - 0.36 * lon_aux * (lat_aux ** 2)
         - 44.54 * (lon_aux ** 3))
    N = (1200147.07
         + 308807.95 * lat_aux
         + 3745.25 * (lon_aux ** 2)
         + 76.63 * (lat_aux ** 2)
         - 194.56 * (lon_aux ** 2) * lat_aux
         + 119.79 * (lat_aux ** 3))
    return E, N

def e_n_to_tilekey(e, n):
    return f"{int(e//1000)}-{int(n//1000)}"

# ---------- index tuiles ----------
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
        raise RuntimeError(f"Aucune tuile trouvée sous {tif_dir}")
    return idx

# ---------- worker ----------
def process_tile(args):
    tile_path, rows = args  # rows: [(row_idx, E, N)]
    ds = gdal.Open(tile_path, gdal.GA_ReadOnly)
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

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default="/data/observations_swiss.csv")
    ap.add_argument("--out", dest="out", default="data/observations_with_elevation.csv")
    ap.add_argument("--tif-dir", dest="tif_dir", default="/data/swissALTI3D_tiles")
    ap.add_argument("--lon-field", dest="lon_field")
    ap.add_argument("--lat-field", dest="lat_field")
    ap.add_argument("--workers", type=int, default=0, help="nb de processus (0 = nb CPU)")
    args = ap.parse_args()

    print("Indexation des tuiles...")
    tile_index = build_tile_index(args.tif_dir)
    print(f"{len(tile_index)} tuiles indexées.")

    # 1) lire CSV
    print("Lecture du CSV source...")
    with open(args.inp, "r", encoding="utf-8", newline="") as fin:
        reader = csv.DictReader(fin)
        fields = reader.fieldnames
        if not fields:
            raise RuntimeError("CSV vide")
        # détecter colonnes lon/lat
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
    print(f"{total_rows} lignes à traiter.")

    # 2) projeter & grouper
    print("Projection et groupement par tuile...")
    from collections import defaultdict
    by_tile = defaultdict(list)
    # on pré-remplit elevation_m vide
    for i, row in enumerate(rows_data):
        row["elevation_m"] = ""

    for i, row in enumerate(rows_data):
        try:
            lon = float(row[lon_field]); lat = float(row[lat_field])
        except Exception:
            continue
        E, N = wgs84_to_lv95(lon, lat)
        tile_key = e_n_to_tilekey(E, N)
        tif_path = tile_index.get(tile_key)
        if not tif_path:
            continue
        by_tile[tif_path].append((i, E, N))

    print(f"{len(by_tile)} tuiles réellement utilisées (ayant au moins un point).")

    # 3) traitement parallèle
    workers = args.workers or cpu_count()
    tasks = list(by_tile.items())
    print(f"Traitement en parallèle avec {workers} worker(s)...")

    results = {}
    done_tiles = 0
    total_tiles = len(tasks)

    def _update_progress():
        # petite progression sur tuiles
        print_progress(done_tiles, total_tiles if total_tiles else 1, bar_len=30)

    with Pool(processes=workers) as pool:
        for partial in pool.imap_unordered(process_tile, tasks):
            results.update(partial)
            done_tiles += 1
            _update_progress()

    print("Écriture du CSV de sortie...")
    out_fields = fields + (["elevation_m"] if "elevation_m" not in fields else [])
    with open(args.out, "w", encoding="utf-8", newline="") as fout:
        writer = csv.DictWriter(fout, fieldnames=out_fields)
        writer.writeheader()
        # ici on met une barre de progression sur les lignes écrites
        for i, row in enumerate(rows_data, start=1):
            if i-1 in results:
                row["elevation_m"] = results[i-1]
            writer.writerow(row)
            if i % 1000 == 0 or i == total_rows:
                print_progress(i, total_rows)

    print("Terminé.")

if __name__ == "__main__":
    gdal.UseExceptions()
    main()
