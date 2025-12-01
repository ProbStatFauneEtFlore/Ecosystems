import os
from dataclasses import dataclass
from typing import Optional, Sequence, Iterable



@dataclass
class Utils:

    DATA_DIR = "data/"
    DATA_CLUSTERS_DIR = os.path.join(DATA_DIR, "clusters/")
    DATA_PROCESSED_DIR = os.path.join(DATA_DIR, "processed/")
    DATA_RAW = os.path.join(DATA_DIR, "observations_swiss.csv")
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
            csv_files = os.listdir(cls.DATA_PROCESSED_DIR)
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"Pre-process directory not found: {cls.DATA_PROCESSED_DIR}") from exc

        target_filters = [f.lower() for f in filter_types]

        for fname in csv_files:
            name_lower = fname.lower()
            if "filtered" not in name_lower or not fname.endswith(".csv"):
                continue
            if all(ft in name_lower for ft in target_filters):
                return os.path.join(cls.DATA_PROCESSED_DIR, fname)

        raise FileNotFoundError(
            f"Aucun fichier 'filtered' avec filtres {filter_types} n'a ete trouve dans {cls.DATA_PROCESSED_DIR}."
        )
    
    @classmethod
    def get_data_most_filtered_path(
        cls,
        exclude_filter: Optional[Sequence[str]] = None,
        include_filter: Optional[Sequence[str]] = None,
        exclude_enrich: Optional[Sequence[str]] = None,
        include_enrich: Optional[Sequence[str]] = None,
    ) -> str:
        """
        Return the CSV path contenant le plus de filtres (et enrichissements) compatibles
        avec les contraintes include/exclude.
        - exclude_filter / include_filter agissent sur les tags apres 'filtered'
        - exclude_enrich / include_enrich agissent sur les tags apres 'enriched'
        Si aucun fichier ne correspond, on retombe sur DATA_RAW.
        """
        import os

        exclude_filter = [e.lower() for e in (exclude_filter or [])]
        include_filter = [i.lower() for i in (include_filter or [])]
        exclude_enrich = [e.lower() for e in (exclude_enrich or [])]
        include_enrich = [i.lower() for i in (include_enrich or [])]

        try:
            csv_files = os.listdir(cls.DATA_PROCESSED_DIR)
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"Pre-process directory not found: {cls.DATA_PROCESSED_DIR}") from exc

        def _extract_tags(filename: str) -> tuple[list[str], list[str]]:
            parts = os.path.splitext(filename)[0].lower().split("_")
            filters: list[str] = []
            enrichments: list[str] = []
            if "filtered" in parts:
                idx_filtered = parts.index("filtered")
                after_filtered = parts[idx_filtered + 1 :]
                if "enriched" in after_filtered:
                    idx_enriched = after_filtered.index("enriched")
                    filters = [p for p in after_filtered[:idx_enriched] if p]
                    enrichments = [p for p in after_filtered[idx_enriched + 1 :] if p]
                else:
                    filters = [p for p in after_filtered if p]
            elif "enriched" in parts:
                idx_enriched = parts.index("enriched")
                enrichments = [p for p in parts[idx_enriched + 1 :] if p]
            return filters, enrichments

        candidates: list[tuple[str, int, int]] = []  # (fname, nb_filters, nb_enrich)

        for fname in csv_files:
            name_lower = fname.lower()
            if not fname.endswith(".csv"):
                continue

            filters, enrichments = _extract_tags(name_lower)

            if any(ex in filters for ex in exclude_filter):
                continue
            if any(ex in enrichments for ex in exclude_enrich):
                continue
            if include_filter and not all(req in filters for req in include_filter):
                continue
            if include_enrich and not all(req in enrichments for req in include_enrich):
                continue

            candidates.append((fname, len(filters), len(enrichments)))

        if not candidates:
            return cls.DATA_RAW

        # Priorité : nb de filtres puis nb d'enrichissements
        candidates.sort(key=lambda x: (x[1], x[2]), reverse=True)
        best_file = candidates[0][0]
        return os.path.join(cls.DATA_PROCESSED_DIR, best_file)
    
    
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
        Construit un nom conforme a la nomenclature
        <nom>_filtered_<[filters]>_enriched_<[enrichments]>.csv en preservant
        l'ordre existant et en ajoutant uniquement les tags manquants.
        """
        kind_l = kind.lower().strip()
        if kind_l not in {"enriched", "filtered"}:
            raise ValueError("kind must be 'enriched' or 'filtered'")

        def _normalize(seq: Sequence[str]) -> list[str]:
            seen: set[str] = set()
            out: list[str] = []
            for val in seq:
                if not val:
                    continue
                v = str(val).lower().strip()
                if v and v not in seen:
                    seen.add(v)
                    out.append(v)
            return out

        def _merge(base_list: list[str], to_add: list[str]) -> list[str]:
            merged = list(base_list)
            for item in to_add:
                if item not in merged:
                    merged.append(item)
            return merged

        norm_tags = _normalize(tags)

        base_root, base_ext = os.path.splitext(base)
        use_ext = base_ext or ext

        dir_path, fname_root = os.path.split(base_root)
        parts = [p for p in fname_root.split("_") if p]

        prefix: list[str] = []
        filters: list[str] = []
        enrichments: list[str] = []

        i = 0
        while i < len(parts):
            token = parts[i].lower()
            if token == "filtered":
                i += 1
                while i < len(parts) and parts[i].lower() not in {"filtered", "enriched"}:
                    filters.append(parts[i].lower())
                    i += 1
                continue
            if token == "enriched":
                i += 1
                while i < len(parts) and parts[i].lower() not in {"filtered", "enriched"}:
                    enrichments.append(parts[i].lower())
                    i += 1
                continue
            prefix.append(parts[i])
            i += 1

        if kind_l == "filtered":
            filters = _merge(filters, norm_tags)
        else:
            enrichments = _merge(enrichments, norm_tags)

        # Re-dedupe existing sections to avoid weird duplicates from multiple markers
        filters = _normalize(filters)
        enrichments = _normalize(enrichments)

        final_parts: list[str] = []
        final_parts.extend(prefix)
        if filters:
            final_parts.append("filtered")
            final_parts.extend(filters)
        if enrichments:
            final_parts.append("enriched")
            final_parts.extend(enrichments)

        final_name = "_".join(final_parts) + use_ext
        return os.path.join(dir_path, final_name) if dir_path else final_name
