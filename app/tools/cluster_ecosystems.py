#!/usr/bin/env python3
import sys
import os
import json
import argparse
import datetime
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


def extract_year_series(df, year_field):
    """
    Returns a pandas Series (Int64) with the observation year for each row.
    Falls back to parsing 'observed_on' when the requested field is absent.
    """
    if year_field in df.columns:
        years = pd.to_numeric(df[year_field], errors="coerce")
        source = year_field
    elif "observed_on" in df.columns:
        years = pd.to_datetime(df["observed_on"], errors="coerce").dt.year
        source = "observed_on"
        print(f"Champ '{year_field}' introuvable, annee derivee depuis 'observed_on'.")
    else:
        raise ValueError(
            f"Impossible d'extraire l'annee : colonne '{year_field}' absente et pas de champ 'observed_on'."
        )

    missing = years.isna().sum()
    if missing > 0:
        print(f"Attention : {missing} lignes sans annee seront ignorees pour le clustering.")

    print(f"Utilisation du champ '{source}' pour determiner l'annee.")
    return years.astype("Int64")


def main():
    from tools.utils import Utils
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=None, help="Input CSV path.")
    ap.add_argument("--out", dest="out", default=None, help="Output CSV path (default: dossier horodaté sous data/clusters).")
    ap.add_argument("--out-geojson-2056", default=None, help="GeoJSON 2056 path (default: base du CSV).")
    ap.add_argument("--out-geojson-4326", default=None, help="GeoJSON 4326 path (default: base du CSV).")
    ap.add_argument("--eps", type=float, default=500.0)
    ap.add_argument("--min-samples", type=int, default=10)
    ap.add_argument("--alt-scale", type=float, default=1.0)
    ap.add_argument("--lon-field", default="longitude")
    ap.add_argument("--lat-field", default="latitude")
    ap.add_argument("--elev-field", default="elevation_m")
    ap.add_argument("--year-field", default="year")
    ap.add_argument("--exclude-filter", action="append", nargs="+", default=[], help="Exclure certains filtres")
    ap.add_argument("--include-filter", action="append", nargs="+", default=[], help="Inclure certains filtres")
    ap.add_argument("--exclude-enrich", action="append", nargs="+", default=[], help="Exclure certains enrichissements")
    ap.add_argument("--include-enrich", action="append", nargs="+", default=[], help="Inclure seulement certains enrichissements")

    args = ap.parse_args()

    def _flatten(val):
        out = []
        for item in val:
            if isinstance(item, (list, tuple)):
                out.extend(item)
            else:
                out.append(item)
        return out

    args.exclude_filter = _flatten(args.exclude_filter)
    args.include_filter = _flatten(args.include_filter)
    args.exclude_enrich = _flatten(args.exclude_enrich)
    args.include_enrich = _flatten(args.include_enrich)


    def _cluster_output_dir(base_dir: str | None = None) -> str:
        if base_dir:
            os.makedirs(base_dir, exist_ok=True)
            return base_dir
        ts = datetime.datetime.now().strftime("%Y_%m_%d-%H_%M")
        out_dir = os.path.join(Utils.DATA_CLUSTERS_DIR, f"clusters-{ts}")
        os.makedirs(out_dir, exist_ok=True)
        return out_dir

    def _derive_out_csv(in_path: str, out_dir: str) -> str:
        base_root = os.path.splitext(os.path.basename(in_path))[0]
        parts = [p for p in base_root.split("_") if p]

        filters = []
        enrichments = []
        if "filtered" in parts:
            idx_f = parts.index("filtered")
            after_f = parts[idx_f + 1 :]
            if "enriched" in after_f:
                idx_e = after_f.index("enriched")
                filters = [p for p in after_f[:idx_e] if p]
                enrichments = [p for p in after_f[idx_e + 1 :] if p]
            else:
                filters = [p for p in after_f if p]
        elif "enriched" in parts:
            idx_e = parts.index("enriched")
            enrichments = [p for p in parts[idx_e + 1 :] if p]

        prefix_base = parts[0] if parts else "observations"

        def abbr(seq):
            return [s[0].lower() for s in seq if s]

        final_parts = [prefix_base, "clusters"]
        filt_abbr = abbr(filters)
        enr_abbr = abbr(enrichments)
        if filt_abbr:
            final_parts.append("filtered")
            final_parts.extend(filt_abbr)
        if enr_abbr:
            final_parts.append("enriched")
            final_parts.extend(enr_abbr)

        out_name = "_".join(final_parts) + ".csv"
        return os.path.join(out_dir, out_name) if out_dir else out_name

    def _ensure_dir(path: str):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    def _update_manifest(out_csv_path: str):
        rel = os.path.relpath(out_csv_path, Utils.DATA_CLUSTERS_DIR).replace("\\", "/")
        manifest_path = os.path.join(Utils.DATA_CLUSTERS_DIR, "manifest.json")
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                entries = json.load(f)
                if not isinstance(entries, list):
                    entries = []
        except FileNotFoundError:
            entries = []
        if rel not in entries:
            entries.append(rel)
            try:
                with open(manifest_path, "w", encoding="utf-8") as f:
                    json.dump(entries, f, ensure_ascii=False, indent=2)
                print(f"Manifest clusters mis a jour : {manifest_path}")
            except Exception as exc:  # pragma: no cover
                print(f"Impossible d'ecrire le manifest {manifest_path}: {exc}", file=sys.stderr)

    if args.inp is None:
        args.inp = Utils.get_data_most_filtered_path(exclude_filter=args.exclude_filter,
                                                       include_filter=args.include_filter,
                                                       exclude_enrich=args.exclude_enrich,
                                                       include_enrich=args.include_enrich)
        print(f"Aucun CSV d'entree fourni, utilisation de : {args.inp}")

    if args.out is None:
        target_dir = _cluster_output_dir()
        args.out = _derive_out_csv(args.inp, target_dir)
        print(f"Nom du CSV de sortie derive : {args.out}")
    else:
        target_dir = os.path.dirname(args.out) or "."
        _ensure_dir(args.out)

    base_root = os.path.splitext(os.path.basename(args.out))[0]
    if args.out_geojson_2056 is None:
        args.out_geojson_2056 = os.path.join(target_dir, f"{base_root}.geojson")
    else:
        _ensure_dir(args.out_geojson_2056)
    if args.out_geojson_4326 is None:
        args.out_geojson_4326 = os.path.join(target_dir, f"{base_root}_4326.geojson")
    else:
        _ensure_dir(args.out_geojson_4326)

    # mettre a jour le manifest pour le front
    _update_manifest(args.out)

    # 1) lire le CSV
    print("Lecture du CSV ...")
    df = pd.read_csv(args.inp)
    n = len(df)
    if n == 0:
        print("CSV vide, rien a faire.")
        return

    # 1bis) annee a extraire pour le clustering annuel
    df["cluster_year"] = extract_year_series(df, args.year_field)
    valid_year_mask = df["cluster_year"].notna()
    if not valid_year_mask.any():
        print("Aucune annee valide trouvee : clustering impossible.", file=sys.stderr)
        return

    # 2) reprojeter en LV95
    print("Conversion WGS84 -> LV95 ...")
    E_list, N_list = [], []
    for i, row in df.iterrows():
        E, N = wgs84_to_lv95(row[args.lon_field], row[args.lat_field])
        E_list.append(E)
        N_list.append(N)
        if (i + 1) % 20000 == 0:
            print_progress(i + 1, n, prefix="conversion ")
    df["E_lv95"] = E_list
    df["N_lv95"] = N_list
    print_progress(n, n, prefix="conversion ")

    # 2bis) determiner si on utilise la hauteur
    use_altitude = False
    elev_present = args.elev_field in df.columns
    name_lower = os.path.basename(args.inp).lower()
    if elev_present and "elevation" in name_lower:
        # utiliser altitude si la colonne est presente ET si le nom mentionne le filtre elevation
        if df[args.elev_field].notna().all():
            use_altitude = True
        else:
            print("Elevation partiellement manquante : z sera ignore pour DBSCAN.")
    else:
        if elev_present:
            print("Elevation ignoree (fichier non filtre elevation).")
        else:
            print("Colonne elevation absente : clustering 2D.")

    # 3) clustering DBSCAN par annee
    df["cluster_local_id"] = -1
    df["cluster_id"] = -1
    global_cluster_counter = 0

    years = sorted(df.loc[valid_year_mask, "cluster_year"].dropna().unique())
    for year in years:
        year_mask = df["cluster_year"] == year
        sub = df.loc[year_mask]
        print(f"Clustering DBSCAN pour l'annee {year} (n={len(sub)}) ...")

        if use_altitude:
            elev = sub[args.elev_field].fillna(0).to_numpy(dtype=float)
            z = elev / args.alt_scale
            X = np.vstack([
                sub["E_lv95"].to_numpy(dtype=float),
                sub["N_lv95"].to_numpy(dtype=float),
                z
            ]).T
        else:
            X = np.vstack([
                sub["E_lv95"].to_numpy(dtype=float),
                sub["N_lv95"].to_numpy(dtype=float),
                np.zeros(len(sub), dtype=float)
            ]).T

        db = DBSCAN(eps=args.eps, min_samples=args.min_samples).fit(X)
        local_labels = db.labels_

        # Map local labels (per year) to unique global cluster ids
        local_to_global = {}
        for lbl in np.unique(local_labels):
            if lbl == -1:
                continue
            local_to_global[int(lbl)] = global_cluster_counter
            global_cluster_counter += 1

        global_labels = np.array([
            local_to_global.get(int(lbl), -1)
            for lbl in local_labels
        ], dtype=int)

        df.loc[year_mask, "cluster_local_id"] = local_labels
        df.loc[year_mask, "cluster_id"] = global_labels

    # 4) ecrire le CSV annote
    print(f"Ecriture CSV : {args.out}")
    df.to_csv(args.out, index=False)

    # 5) construire le GeoJSON en 2056, en gardant la separation par annee
    print("Construction des geometries d'ecosystemes (2056) par annee ...")
    features_2056 = []
    clustered = df[df["cluster_id"] != -1]

    for (year, cid), sub in clustered.groupby(["cluster_year", "cluster_id"]):
        radius = args.eps
        buffers = [Point(x, y).buffer(radius) for x, y in zip(sub["E_lv95"], sub["N_lv95"])]
        union_geom = unary_union(buffers).buffer(0)
        poly = union_geom.simplify(tolerance=radius * 0.2, preserve_topology=True)

        feat = {
            "type": "Feature",
            "properties": {
                "cluster_id": int(cid),
                "cluster_local_id": int(sub["cluster_local_id"].iloc[0]),
                "year": int(year),
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

    print(f"Ecriture GeoJSON 2056 : {args.out_geojson_2056}")
    with open(args.out_geojson_2056, "w", encoding="utf-8") as f:
        json.dump(geojson_2056, f)

    # 6) appeler ogr2ogr pour creer la version 4326
    print("Reprojection via ogr2ogr vers EPSG:4326 ...")
    try:
        subprocess.run([
            "ogr2ogr",
            "-s_srs", "EPSG:2056",
            "-t_srs", "EPSG:4326",
            args.out_geojson_4326,
            args.out_geojson_2056
        ], check=True)
        print(f"Ecriture GeoJSON 4326 : {args.out_geojson_4326}")
    except FileNotFoundError:
        print("ERREUR : ogr2ogr introuvable dans le conteneur. Verifie que gdal/ogr est installe.", file=sys.stderr)
    except subprocess.CalledProcessError as e:
        print("ERREUR : ogr2ogr a echoue :", e, file=sys.stderr)

    print("Termine.")


if __name__ == "__main__":
    main()
