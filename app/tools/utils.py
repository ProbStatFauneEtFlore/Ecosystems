import os
from dataclasses import dataclass
from typing import Optional, Sequence, Iterable



@dataclass
class Utils:

    DATA_DIR = "data/"
    DATA_RAW_DIR = os.path.join(DATA_DIR, "raw/")
    DATA_NEW_DIR = os.path.join(DATA_DIR, "new/")

    DATA_RAW = os.path.join(DATA_RAW_DIR, "observations_swiss.csv")
    TILES_DIR = os.path.join(DATA_DIR, "swissALTI3D_tiles/")

    @classmethod
    def get_data_filtered_path(cls, filter_types: Sequence[str]) -> str:
        """
        Return the pre-process CSV path matching all requested filter keywords.
        Ex: filter_types=["position", "elevation"] will look for a file that contains
        "filtered", "position" and "elevation" in its filename.
        Raises FileNotFoundError if no exact match is found.
        """
        import os

        if not filter_types:
            raise ValueError("filter_types must contain at least one filter keyword.")

        try:
            csv_files = os.listdir(cls.DATA_NEW_DIR)
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"Pre-process directory not found: {cls.DATA_NEW_DIR}") from exc

        target_filters = [f.lower() for f in filter_types]

        for fname in csv_files:
            name_lower = fname.lower()
            if "filtered" not in name_lower or not fname.endswith(".csv"):
                continue
            if all(ft in name_lower for ft in target_filters):
                return os.path.join(cls.DATA_NEW_DIR, fname)

        raise FileNotFoundError(
            f"Aucun fichier 'filtered' avec filtres {filter_types} n'a ete trouve dans {cls.DATA_NEW_DIR}."
        )
    
    @classmethod
    def get_data_most_filtered_path(cls, exclude: Optional[Sequence[str]] = None) -> str:
        """
        Return the pre-process CSV path that contains 'filtered' and the most other filters,
        excluding any filters in the exclude list.
        Ex: exclude=["grade"] will ignore files that contain "grade" in their filename.
        Raises FileNotFoundError if no suitable file is found.
        """
        import os

        exclude = exclude or []
        exclude = [e.lower() for e in exclude]

        try:
            csv_files = os.listdir(cls.DATA_NEW_DIR)
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"Pre-process directory not found: {cls.DATA_NEW_DIR}") from exc

        best_file = None
        best_filter_count = -1

        for fname in csv_files:
            name_lower = fname.lower()
            if "filtered" not in name_lower or not fname.endswith(".csv"):
                continue
            if any(ex in name_lower for ex in exclude):
                continue

            filter_count = name_lower.count("_")  # crude way to estimate number of filters
            if filter_count > best_filter_count:
                best_filter_count = filter_count
                best_file = fname

        if best_file is None:
            return cls.DATA_RAW

        return os.path.join(cls.DATA_NEW_DIR, best_file)
    
    
    @staticmethod
    def chunks(iterable: Iterable, size: int):
        import itertools
        it = iter(iterable)
        while True:
            batch = list(itertools.islice(it, size))
            if not batch:
                break
            yield batch

    @staticmethod
    def print_progress(current, total, prefix="", bar_len=40):
        import sys

        if total <= 0:
            return
        frac = current / total
        filled = int(bar_len * frac)
        bar = "#" * filled + "-" * (bar_len - filled)
        sys.stdout.write(f"\r{prefix}[{bar}] {int(frac*100):3d}% ({current}/{total})")
        sys.stdout.flush()
        if current >= total:
            sys.stdout.write("\n")

    # ------ geo helpers ------
    @staticmethod
    def wgs84_to_lv95(lon_deg: float, lat_deg: float) -> tuple[float, float]:
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

    @staticmethod
    def tiles_available(tif_dir: str) -> bool:
        """Return True if at least one .tif tile exists under tif_dir."""
        if not os.path.isdir(tif_dir):
            return False
        for _root, _dirs, files in os.walk(tif_dir):
            if any(fn.lower().endswith(".tif") for fn in files):
                return True
        return False

    @staticmethod
    def name_file(base: str, kind: str, tags: Sequence[str], ext: str = ".csv") -> str:
        """
        Build a file name with a single 'enriched' or 'filtered' marker and ordered tags.
        - base: base path or file name (with or without extension)
        - kind: 'enriched' or 'filtered'
        - tags: sequence like ['elevation', 'taxa'] or ['position', 'grade']
        Example: Utils.name_file("data/observations_swiss.csv", "enriched", ["elevation", "taxa"])
                 -> data/observations_swiss_enriched_elevation_taxa.csv
        """
        kind_l = kind.lower().strip()
        if kind_l not in {"enriched", "filtered"}:
            raise ValueError("kind must be 'enriched' or 'filtered'")

        # Normalize tags (lower, unique order, non-empty)
        seen = set()
        norm_tags = []
        for t in tags:
            if not t:
                continue
            tl = str(t).lower().strip()
            if tl and tl not in seen:
                seen.add(tl)
                norm_tags.append(tl)

        base_root, base_ext = os.path.splitext(base)
        use_ext = base_ext or ext

        # Split dir and file name to avoid mangling directories
        dir_path, fname_root = os.path.split(base_root)
        fname_parts = [p for p in fname_root.split("_") if p]

        # Remove existing occurrences of kind/tags to avoid duplicates
        skip = {kind_l, *norm_tags}
        cleaned_parts = [p for p in fname_parts if p.lower() not in skip]

        final_parts = cleaned_parts + [kind_l] + norm_tags
        final_name = "_".join(final_parts) + use_ext

        return os.path.join(dir_path, final_name) if dir_path else final_name
