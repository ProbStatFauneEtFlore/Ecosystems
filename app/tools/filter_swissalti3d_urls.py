#!/usr/bin/env python3
import csv
import os
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OBS_CSV = os.path.join(ROOT_DIR, "app/data", "observations_swiss.csv")
URLS_IN = os.path.join(ROOT_DIR, "app/data", "swissalti3d_urls.txt")
URLS_OUT = os.path.join(ROOT_DIR, "app/data", "swissalti3d_urls_filtered.txt")

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

# -------------------------------------------------
# 1) lire les observations et déterminer les tuiles
# -------------------------------------------------
# on compte d'abord les lignes pour la barre
with open(OBS_CSV, "r", encoding="utf-8", newline="") as f:
    total_obs = sum(1 for _ in f) - 1  # -1 pour l'entête

needed_tiles = set()
with open(OBS_CSV, "r", encoding="utf-8", newline="") as f:
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

print(f"{len(needed_tiles)} tuiles nécessaires d'après les observations.")

# -------------------------------------------------
# 2) filtrer la liste d'URLs avec une barre
# -------------------------------------------------
with open(URLS_IN, "r", encoding="utf-8") as fin:
    all_urls = [line.strip() for line in fin if line.strip()]

total_urls = len(all_urls)
kept = []

for idx, url in enumerate(all_urls, start=1):
    name = os.path.basename(url)
    # test rapide: les noms de swissALTI3D contiennent _Ekm-Nkm_
    matched = False
    for tk in needed_tiles:
        if f"_{tk}_" in name:
            kept.append(url)
            matched = True
            break
    # progression
    if idx % 200 == 0 or idx == total_urls:
        print_progress(idx, total_urls, prefix="Filtrage URLs  ")

# -------------------------------------------------
# 3) écrire le fichier filtré
# -------------------------------------------------
with open(URLS_OUT, "w", encoding="utf-8") as fout:
    fout.write("\n".join(kept))

print(f"\nTerminé ✅ {len(kept)} URLs gardées dans {URLS_OUT}")