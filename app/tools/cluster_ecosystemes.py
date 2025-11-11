#!/usr/bin/env python3
import os
import sys
import json
import argparse
import pandas as pd
import numpy as np
from sklearn.cluster import DBSCAN
from shapely.geometry import Point, mapping
from shapely.ops import unary_union
import subprocess

def wgs84_to_lv95(lon_deg, lat_deg):
    # Formule swisstopo WGS84 -> CH1903+ / LV95
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

def print_progress(current, total, prefix=""):
    if total == 0:
        return
    frac = current / total
    bar_len = 40
    filled = int(bar_len * frac)
    bar = "#" * filled + "-" * (bar_len - filled)
    sys.stdout.write(f"\r{prefix}[{bar}] {int(frac*100):3d}% ({current}/{total})")
    sys.stdout.flush()
    if current == total:
        sys.stdout.write("\n")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-csv", default="data/observations_with_elevation.csv")
    ap.add_argument("--out-csv", default="data/observations_with_clusters.csv")
    ap.add_argument("--out-geojson-2056", default="data/ecosystemes_2056.geojson")
    ap.add_argument("--out-geojson-4326", default="data/ecosystemes_4326.geojson")
    ap.add_argument("--eps", type=float, default=120.0)
    ap.add_argument("--min-samples", type=int, default=5)
    ap.add_argument("--alt-scale", type=float, default=50.0)
    ap.add_argument("--lon-field", default="longitude")
    ap.add_argument("--lat-field", default="latitude")
    ap.add_argument("--elev-field", default="elevation_m")
    args = ap.parse_args()

    # 1) lire le CSV
    print("Lecture du CSV ...")
    df = pd.read_csv(args.in_csv)
    n = len(df)
    if n == 0:
        print("CSV vide, rien à faire.")
        return

    # 2) reprojeter en LV95
    print("Conversion WGS84 -> LV95 ...")
    E_list, N_list = [], []
    for i, row in df.iterrows():
        E, N = wgs84_to_lv95(row[args.lon_field], row[args.lat_field])
        E_list.append(E)
        N_list.append(N)
        if (i+1) % 20000 == 0:
            print_progress(i+1, n, prefix="conversion ")
    df["E_lv95"] = E_list
    df["N_lv95"] = N_list
    print_progress(n, n, prefix="conversion ")

    # 3) préparer les données pour DBSCAN
    elev = df[args.elev_field].fillna(0).to_numpy(dtype=float)
    z = elev / args.alt_scale
    X = np.vstack([
        df["E_lv95"].to_numpy(dtype=float),
        df["N_lv95"].to_numpy(dtype=float),
        z
    ]).T

    print(f"Clustering DBSCAN (eps={args.eps}, min_samples={args.min_samples}) ...")
    db = DBSCAN(eps=args.eps, min_samples=args.min_samples).fit(X)
    df["cluster_id"] = db.labels_

    # 4) écrire le CSV annoté
    print(f"Écriture CSV : {args.out_csv}")
    df.to_csv(args.out_csv, index=False)

    # 5) construire le GeoJSON en 2056
    print("Construction des géométries d'écosystèmes (2056) ...")
    features_2056 = []
    clustered = df[df["cluster_id"] != -1]

    for cid, sub in clustered.groupby("cluster_id"):
        radius = args.eps
        buffers = [Point(x, y).buffer(radius) for x, y in zip(sub["E_lv95"], sub["N_lv95"])]
        union_geom = unary_union(buffers).buffer(0)
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
        features_2056.append(feat)

    geojson_2056 = {
        "type": "FeatureCollection",
        "name": "ecosystemes_2056",
        "crs": {
            "type": "name",
            "properties": {"name": "EPSG:2056"}
        },
        "features": features_2056
    }

    print(f"Écriture GeoJSON 2056 : {args.out_geojson_2056}")
    with open(args.out_geojson_2056, "w", encoding="utf-8") as f:
        json.dump(geojson_2056, f)

    # 6) appeler ogr2ogr pour créer la version 4326
    print("Reprojection via ogr2ogr vers EPSG:4326 ...")
    try:
        subprocess.run([
            "ogr2ogr",
            "-s_srs", "EPSG:2056",
            "-t_srs", "EPSG:4326",
            args.out_geojson_4326,
            args.out_geojson_2056
        ], check=True)
        print(f"Écriture GeoJSON 4326 : {args.out_geojson_4326}")
    except FileNotFoundError:
        print("ERREUR : ogr2ogr introuvable dans le conteneur. Vérifie que gdal/ogr est installé.", file=sys.stderr)
    except subprocess.CalledProcessError as e:
        print("ERREUR : ogr2ogr a échoué :", e, file=sys.stderr)

    print("Terminé ✅")

if __name__ == "__main__":
    main()