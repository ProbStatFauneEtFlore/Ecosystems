#!/usr/bin/env python3
import argparse
import os
import pandas as pd


def _output_path(csv_path, suffix):
    base, ext = os.path.splitext(csv_path)
    ext = ext or ".csv"
    return f"{base}_{suffix}{ext}"


def filter_for_positional_treatment(csv_path):
    """
    Filter rows that lack positional_accuracy or exceed 100 meters.
    Returns the path to the newly written filtered CSV.
    """
    df = pd.read_csv(csv_path)
    if "positional_accuracy" not in df.columns:
        raise ValueError("CSV must contain 'positional_accuracy' column")

    positional_accuracy = pd.to_numeric(df["positional_accuracy"], errors="coerce")
    filtered = df[positional_accuracy.notna() & (positional_accuracy <= 100)]

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

    out_path = _output_path(csv_path, "filtered")
    filtered.to_csv(out_path, index=False)
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Filter CSV rows for positional accuracy or elevation presence.")
    parser.add_argument("mode", choices=["position", "elevation"], help="Filtering mode to apply.")
    parser.add_argument("--in", dest="inp", help="Input CSV path.", default=None)
    parser.add_argument("--out", dest="out", help="Output CSV path (optional).")
    args = parser.parse_args()

    in_path = args.inp if args.inp is not None else "data/observations_swiss.csv" \
        if args.mode == "position" else "data/observations_with_elevation.csv"
    print(in_path)
    if args.mode == "position":
        produced = filter_for_positional_treatment(in_path)
    else:
        produced = filter_for_clustering(in_path)

    out_path = args.out or produced
    if produced != out_path:
        os.replace(produced, out_path)

    print(out_path)


if __name__ == "__main__":
    main()
