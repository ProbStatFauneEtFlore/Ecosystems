#!/usr/bin/env python3
import csv, os, sys, math, argparse, json
from collections import defaultdict

import pandas as pd
import numpy as np
from sklearn.cluster import DBSCAN

try:
    from shapely.geometry import Point, mapping
    from shapely.ops import unary_union
except ImportError:
    print("Ce script nécessite shapely (`pip install shapely`).", file=sys.stderr)
    sys.exit(1)

# ------------------ conversions ------------------
def wgs84_to_lv95(lon_deg, lat_deg):
    # Formule officielle swisstopo WGS84 -> CH1903+ / LV95
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

# ------------------ barre de progression simple ------------------
def print_progress(current, total, prefix=""):
    pct = current / total if total else 1
    bar_len = 40
    filled = int(bar_len * pct)
    bar = "#" * filled + "-" * (bar_len - filled)
    sys.stdout.write(f"\r{prefix}[{bar}] {int(pct*100):3d}% ({current}/{total})")
    sys.stdout.flush()
    if current >= total:
        sys.stdout.write("\n")

def main():
    ap = argparse.ArgumentParser(description="Clustering d'observations faune/flore en écosystèmes")
    ap.add_argument("--in-csv", required=True, help="CSV d'entrée (avec longitude, latitude, elevation_m)")
    ap.add_argument("--out-csv", required=True, help="CSV de sortie avec colonne cluster_id")
    ap.add_argument("--out-geojson", required=True, help="GeoJSON de sortie avec un polygone par cluster")
    ap.add_argument("--eps", type=float, default=80.0,
                    help="Distance max (en mètres) pour DBSCAN (dans le plan E/N). Défaut=80 m")
    ap.add_argument("--min-samples", type=int, default=10,
                    help="Nombre minimal de points pour former un cluster. Défaut=10")
    ap.add_argument("--alt-scale", type=float, default=50.0,
                    help="Facteur de normalisation de l'altitude (z = elevation_m / alt-scale)")
    ap.add_argument("--lon-field", default="longitude")
    ap.add_argument("--lat-field", default="latitude")
    ap.add_argument("--elev-field", default="elevation_m")
    args = ap.parse_args()

    # 1) lecture
    print("Lecture du CSV...")
    df = pd.read_csv(args.in_csv)
    n = len(df)
    if n == 0:
        print("CSV vide.")
        return

    # 2) convertir en LV95
    print("Conversion WGS84 -> LV95...")
    E_list = []
    N_list = []
    for i, row in df.iterrows():
        lon = row[args.lon_field]
        lat = row[args.lat_field]
        E, N = wgs84_to_lv95(lon, lat)
        E_list.append(E)
        N_list.append(N)
        if (i+1) % 20000 == 0:
            print_progress(i+1, n, prefix="conversion ")

    df["E_lv95"] = E_list
    df["N_lv95"] = N_list
    print_progress(n, n, prefix="conversion ")

    # 3) préparer les features pour DBSCAN
    print("Préparation des données pour DBSCAN...")
    # altitude: on la normalise pour qu'elle pèse moins que 1 m horizontal
    elev = df[args.elev_field].fillna(0).to_numpy(dtype=float)
    z = elev / args.alt_scale
    X = np.vstack([df["E_lv95"].to_numpy(dtype=float),
                   df["N_lv95"].to_numpy(dtype=float),
                   z]).T

    # 4) DBSCAN
    print(f"Lancement de DBSCAN (eps={args.eps} m, min_samples={args.min_samples}) ...")
    # eps s'applique à toutes les dimensions -> comme z est petit, l'horiz. domine
    db = DBSCAN(eps=args.eps, min_samples=args.min_samples).fit(X)
    labels = db.labels_   # -1 = bruit
    df["cluster_id"] = labels

    print("Clusters trouvés :")
    print(df["cluster_id"].value_counts().head(20))

    # 5) écrire le CSV de sortie
    print(f"Écriture du CSV {args.out_csv} ...")
    df.to_csv(args.out_csv, index=False)

    # 6) construire un polygone par cluster (hors bruit)
    print("Construction des polygones d'écosystèmes...")
    features = []
    clustered = df[df["cluster_id"] != -1]

    # groupby sans recalculer tout
    for cid, sub in clustered.groupby("cluster_id"):
        if len(sub) == 0:
            continue

        radius = args.eps

        buffers = [Point(x, y).buffer(radius) for x, y in zip(sub["E_lv95"], sub["N_lv95"])]
        union_geom = unary_union(buffers).buffer(0)

        # OPTION 1 : enveloppe très simple
        # poly = union_geom.convex_hull

        # OPTION 2 : forme un peu affinée mais légère
        poly = union_geom.simplify(tolerance=radius * 0.2, preserve_topology=True)

        feat = {
            "type": "Feature",
            "properties": {
                "cluster_id": int(cid),
                "n_points": int(len(sub)),
                "alt_mean": float(sub[args.elev_field].mean())
            },
            "geometry": mapping(poly)
        }
        features.append(feat)

    geojson = {
        "type": "FeatureCollection",
        "name": "ecosystemes",
        "crs": {
            "type": "name",
            "properties": {"name": "EPSG:2056"}
        },
        "features": features
    }

    print(f"Écriture du GeoJSON {args.out_geojson} ...")
    with open(args.out_geojson, "w", encoding="utf-8") as f:
        json.dump(geojson, f)

    print("Terminé ✅")

if __name__ == "__main__":
    main()
