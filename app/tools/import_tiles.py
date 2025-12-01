#!/usr/bin/env python3
import argparse
import csv
import os
import sys
import tempfile
import subprocess
from utils import Utils

URLS_IN = os.path.join(Utils.DATA_DIR, "swissalti3d_urls.txt")
URLS_OUT = os.path.join(Utils.DATA_DIR, "swissalti3d_urls_filtered.txt")

# -------------------------------------------------
# utils
# -------------------------------------------------
def print_progress(current, total, prefix="", bar_len=40):
    if total == 0:
        total = 1
    frac = current / total
    filled = int(bar_len * frac)
    bar = "#" * filled + "-" * (bar_len - filled)
    pct = int(frac * 100)
    sys.stdout.write(f"\r{prefix}[{bar}] {pct:3d}% ({current}/{total})")
    sys.stdout.flush()
    if current >= total:
        sys.stdout.write("\n")

# -------------------------------------------------
# conversion WGS84 -> LV95
# -------------------------------------------------
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
    return f"{int(e // 1000)}-{int(n // 1000)}"

def generate_filtered_urls(data_raw_path: str) -> int:
    """
    Build the filtered URLs file based on observations; returns number of URLs kept.
    """
    with open(data_raw_path, "r", encoding="utf-8", newline="") as f:
        total_obs = sum(1 for _ in f) - 1  # -1 pour l'entete

    needed_tiles = set()
    with open(data_raw_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=1):
            try:
                lon = float(row["longitude"])
                lat = float(row["latitude"])
            except (KeyError, ValueError):
                print_progress(i, total_obs, prefix="Obs -> tuiles ")
                continue
            E, N = wgs84_to_lv95(lon, lat)
            tile_key = e_n_to_tilekey(E, N)
            needed_tiles.add(tile_key)
            if i % 1000 == 0 or i == total_obs:
                print_progress(i, total_obs, prefix="Obs -> tuiles ")

    print(f"{len(needed_tiles)} tuiles necessaires d'apres les observations.")

    with open(URLS_IN, "r", encoding="utf-8") as fin:
        all_urls = [line.strip() for line in fin if line.strip()]

    total_urls = len(all_urls)
    kept = []

    for idx, url in enumerate(all_urls, start=1):
        name = os.path.basename(url)
        for tk in needed_tiles:
            if f"_{tk}_" in name:
                kept.append(url)
                break
        if idx % 200 == 0 or idx == total_urls:
            print_progress(idx, total_urls, prefix="Filtrage URLs  ")

    with open(URLS_OUT, "w", encoding="utf-8") as fout:
        fout.write("\n".join(kept))

    print(f"\nTermine. {len(kept)} URLs gardees dans {URLS_OUT}")
    return len(kept)

def import_tiles(force=False):
    """
    Filter tile URLs and download tiles.
    - force=False: generate URL list if absent; download only tiles not yet present.
    - force=True: regenerate URL list and download all listed tiles (even if already present).
    """
    from app.tools.utils import Utils

    tiles_dir = Utils.TILES_DIR.rstrip("/\\")

    regenerate = force or (not os.path.exists(URLS_OUT))
    if regenerate:
        print("Generation de la liste filtree des URLs...")
        generate_filtered_urls(Utils.DATA_DIR)
    else:
        print(f"Liste filtree deja presente ({URLS_OUT}), utilisation de l'existant (ajoutez --force pour regenir).")

    with open(URLS_OUT, "r", encoding="utf-8") as fin:
        url_list = [line.strip() for line in fin if line.strip()]

    if not url_list:
        print("Aucune URL a telecharger. Verifiez vos donnees.")
        return

    os.makedirs(tiles_dir, exist_ok=True)

    if not force:
        missing = []
        for url in url_list:
            fname = os.path.basename(url)
            target_path = os.path.join(tiles_dir, fname)
            if not os.path.exists(target_path):
                missing.append(url)
        if not missing:
            print("Toutes les tuiles sont deja presentes, rien a telecharger.")
            return
        url_list = missing
        print(f"{len(url_list)} tuiles manquantes seront telechargees (skip deja presentes).")

    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", suffix=".txt") as tmp:
        tmp.write("\n".join(url_list))
        tmp_path = tmp.name

    print(f"Debut du telechargement des tuiles avec aria2c ({len(url_list)} fichiers)...")
    try:
        subprocess.run(["bash", "tools/import_tiles.sh", tmp_path, tiles_dir], check=True)
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
    print("Telechargement termine.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", dest="force", default=False, help="Re-generate and re-download everything", action="store_true")
    args = ap.parse_args()

    import_tiles(force=args.force)


if __name__ == "__main__":
    main()
