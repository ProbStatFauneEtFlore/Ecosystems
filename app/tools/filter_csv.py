#!/usr/bin/env python3
import argparse
import os
import pandas as pd


def _output_path(csv_path, suffix):
    base, ext = os.path.splitext(csv_path)
    ext = ext or ".csv"
    return f"{base}_{suffix}{ext}"


def filter_for_positional_treatment(csv_path, eps=100):
    """
    Filter rows that lack positional_accuracy or exceed esp=100 meters.
    Returns the path to the newly written filtered CSV.
    """
    df = pd.read_csv(csv_path)
    if "positional_accuracy" not in df.columns:
        raise ValueError("CSV must contain 'positional_accuracy' column")

    positional_accuracy = pd.to_numeric(df["positional_accuracy"], errors="coerce")
    filtered = df[positional_accuracy.notna() & (positional_accuracy <= eps)]

    out_path = _output_path(csv_path, "positional_filtered")
    filtered.to_csv(out_path, index=False)
    return out_path


def filter_for_clustering(csv_path):
    """
    Remove rows missing elevation_m values so clustering only uses entries with altitude.
    Returns the path to the newly written filtered CSV.
    """
    df = pd.read_csv(csv_path)
    if "elevation_m" not in df.columns:
        raise ValueError("CSV must contain 'elevation_m' column")

    elevation = pd.to_numeric(df["elevation_m"], errors="coerce")
    filtered = df[elevation.notna()]

    out_path = _output_path(csv_path, "el_filtered")
    filtered.to_csv(out_path, index=False)
    return out_path

def filter_for_quality_grade(csv_path, types):
    df = pd.read_csv(csv_path)
    if "quality_grade" not in df.columns:
        raise ValueError("CSV must contain 'quality_grade' column")

    filtered = df[df["quality_grade"].notna() & df["quality_grade"].isin(types)]

    out_path = _output_path(csv_path, "grade_filtered")
    filtered.to_csv(out_path, index=False)
    return out_path


def main():
    from tools.utils import Utils
    parser = argparse.ArgumentParser(description="Filter CSV rows for positional accuracy or elevation presence.")
    parser.add_argument("mode", choices=["position", "elevation", "grade"], help="Filtering mode to apply.")
    parser.add_argument("--in", dest="inp", default=None, help="Input CSV path.")
    parser.add_argument("--out", dest="out", help="Output CSV path (optional).")
    parser.add_argument("--exclude-filter", action="append", nargs="+", default=[], help="Exclure certains filtres")
    parser.add_argument("--include-filter", action="append", nargs="+", default=[], help="Inclure certains filtres")
    parser.add_argument("--exclude-enrich", action="append", nargs="+", default=[], help="Exclure certains enrichissements")
    parser.add_argument("--include-enrich", action="append", nargs="+", default=[], help="Inclure seulement certains enrichissements")
    parser.add_argument("--eps", type=float, default=100.0, help="Seuil positional_accuracy maximum (mode position)")
    parser.add_argument("--types", nargs="+", default=None, help="Valeurs de quality_grade (mode grade uniquement).")
    args = parser.parse_args()

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

    in_path = args.inp if args.inp is not None \
                        else Utils.get_data_most_filtered_path(include_enrich=["elevation"] + args.include_enrich, 
                                                               exclude_enrich=args.exclude_enrich, 
                                                               include_filter=args.include_filter, 
                                                               exclude_filter=[args.mode] + args.exclude_filter) \
                        if args.mode == "elevation" else Utils.get_data_most_filtered_path(
                                                               include_enrich=args.include_enrich, 
                                                               exclude_enrich=args.exclude_enrich, 
                                                               include_filter=args.include_filter, 
                                                               exclude_filter=[args.mode] + args.exclude_filter)
    if args.out is None:
        extra_tags = []
        if args.types:
            extra_tags.extend(args.types)
        args.out = Utils.name_file(in_path, "filtered", [args.mode] + extra_tags)
        args.out = os.path.join(Utils.DATA_PROCESSED_DIR, os.path.basename(args.out))

    if args.mode == "position":
        produced = filter_for_positional_treatment(in_path, eps=args.eps)
    elif args.mode == "elevation":
        produced = filter_for_clustering(in_path)
    elif args.mode == "grade":
        if not args.types:
            raise ValueError("Le mode grade requiert au moins une valeur via --types.")
        produced = filter_for_quality_grade(in_path, args.types)
    else:
        raise ValueError(f"Unknown mode: {args.mode}")

    out_path = args.out or produced
    if produced != out_path:
        os.replace(produced, out_path)

    print(out_path)


if __name__ == "__main__":
    main()
